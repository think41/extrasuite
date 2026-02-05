"""Token generation using service account impersonation.

This module provides the TokenGenerator class which:
1. Looks up or creates a service account for a user
2. Uses server's ADC to impersonate the service account
3. Returns a short-lived access token

Key design decisions:
- All IAM operations are async using IAMAsyncClient
- Domain abbreviations prevent SA name collisions across email domains
- Dependencies are injected via constructor for testability
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import google.auth
from google.api_core.exceptions import NotFound
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
from google.cloud.iam_admin_v1 import IAMAsyncClient
from google.cloud.iam_admin_v1.types import (
    CreateServiceAccountRequest,
    GetServiceAccountRequest,
    ServiceAccount,
)
from loguru import logger

# Scopes granted to the generated token
# Read/write for sheets, docs, slides, drive, calendar, forms
TOKEN_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/forms.body",
]

# Delay after SA creation to allow GCP propagation (seconds)
# Required because impersonation may fail if SA hasn't propagated yet
SA_PROPAGATION_DELAY = 3.0


class TokenGeneratorError(Exception):
    """Base exception for TokenGenerator errors."""

    pass


class ServiceAccountCreationError(TokenGeneratorError):
    """Raised when service account creation fails."""

    def __init__(self, message: str, user_email: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.user_email = user_email
        self.cause = cause


class ImpersonationError(TokenGeneratorError):
    """Raised when service account impersonation fails."""

    def __init__(self, message: str, sa_email: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.sa_email = sa_email
        self.cause = cause


@dataclass
class GeneratedToken:
    """Result of token generation."""

    token: str
    expires_at: datetime
    service_account_email: str


class DatabaseProtocol(Protocol):
    """Protocol for database operations needed by TokenGenerator."""

    async def get_service_account_email(self, email: str) -> str | None: ...

    async def set_service_account_email(self, email: str, service_account_email: str) -> None: ...


class SettingsProtocol(Protocol):
    """Protocol for settings needed by TokenGenerator."""

    google_cloud_project: str
    token_expiry_minutes: int

    def get_domain_abbreviation(self, domain: str) -> str: ...


def sanitize_email_for_account_id(email: str, domain_abbrev: str) -> str:
    """Convert email to valid service account ID.

    Service account IDs must:
    - Be 6-30 characters
    - Start with a letter
    - Contain only lowercase letters, numbers, and hyphens

    Includes domain abbreviation to prevent collisions across domains.
    Example: sripathi@recruit41.com with abbrev "r41" → sripathi-r41
    """
    # Take part before @
    local_part = email.split("@")[0].lower()

    # Replace invalid characters with hyphens
    account_id = re.sub(r"[^a-z0-9]", "-", local_part)

    # Remove consecutive hyphens
    account_id = re.sub(r"-+", "-", account_id)

    # Remove leading/trailing hyphens
    account_id = account_id.strip("-")

    # Ensure it starts with a letter (prefix with 'u' if starts with number)
    if account_id and not account_id[0].isalpha():
        account_id = "u" + account_id

    # Truncate to leave room for domain suffix (30 - len(abbrev) - 1 for hyphen)
    max_prefix_len = 30 - len(domain_abbrev) - 1
    account_id = account_id[:max_prefix_len].rstrip("-")

    # Add domain abbreviation (lowercase for consistency)
    account_id = f"{account_id}-{domain_abbrev.lower()}"

    # Ensure minimum length of 6
    if len(account_id) < 6:
        account_id = account_id + "-sa"

    return account_id


class TokenGenerator:
    """Generates short-lived service account tokens for authenticated users.

    This class handles:
    1. Looking up or creating a service account for a user
    2. Using server ADC to impersonate the user's service account
    3. Returning a short-lived access token

    Key design decisions:
    - Uses async IAMAsyncClient for non-blocking IAM operations
    - Uses server's Application Default Credentials (not user OAuth credentials)
    - Dependencies injected via constructor for testability
    """

    def __init__(
        self,
        database: DatabaseProtocol,
        settings: SettingsProtocol,
        iam_client: IAMAsyncClient | None = None,
        impersonated_credentials_class: type = impersonated_credentials.Credentials,
    ) -> None:
        """Initialize TokenGenerator.

        Args:
            database: Database instance for user/SA lookups
            settings: Settings instance for project ID and domain abbreviations
            iam_client: Optional IAM client instance (injectable for testing).
                If not provided, a real client will be created.
            impersonated_credentials_class: Class for creating impersonated credentials
                (injectable for testing)
        """
        self._db = database
        self._settings = settings
        self._iam_client = iam_client if iam_client is not None else IAMAsyncClient()
        self._impersonated_credentials_class = impersonated_credentials_class
        self._admin_creds: Any = None

    @property
    def _project_id(self) -> str:
        """Get project ID from settings."""
        return self._settings.google_cloud_project

    @property
    def _token_lifetime_seconds(self) -> int:
        """Get token lifetime in seconds from settings."""
        return self._settings.token_expiry_minutes * 60

    def _get_admin_credentials(self) -> Any:
        """Get server's Application Default Credentials (cached)."""
        if self._admin_creds is None:
            self._admin_creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        return self._admin_creds

    async def ensure_service_account(self, user_email: str, user_name: str = "") -> str:
        """Ensure a service account exists for the user, creating one if needed.

        This method:
        1. Looks up user's service account in database
        2. Creates one if it doesn't exist (using server ADC)
        3. Returns the service account email

        Args:
            user_email: Verified email of the authenticated user
            user_name: Display name for SA description (optional)

        Returns:
            Service account email

        Raises:
            ServiceAccountCreationError: If SA creation fails
        """
        # Look up existing SA from database
        sa_email = await self._db.get_service_account_email(user_email)

        # Create SA if not found
        if not sa_email:
            sa_email, _ = await self._get_or_create_service_account(user_email, user_name)
            # Store mapping in database
            await self._db.set_service_account_email(user_email, sa_email)

        return sa_email

    async def generate_token_for_service_account(self, sa_email: str) -> GeneratedToken:
        """Generate a short-lived token for a service account.

        This method impersonates the given service account using server ADC
        and returns a short-lived access token.

        Args:
            sa_email: Service account email to impersonate

        Returns:
            GeneratedToken with token, expires_at, and service_account_email

        Raises:
            ImpersonationError: If token generation fails
        """
        token, expires_at = await self._impersonate_service_account(sa_email)

        logger.info(
            "Token generated for service account",
            extra={"service_account": sa_email},
        )

        return GeneratedToken(
            token=token,
            expires_at=expires_at,
            service_account_email=sa_email,
        )

    async def generate_token(self, user_email: str, user_name: str = "") -> GeneratedToken:
        """Generate a short-lived service account token for a user.

        This method:
        1. Ensures service account exists (creates if needed)
        2. Impersonates the SA using server ADC
        3. Returns a short-lived access token

        Args:
            user_email: Verified email of the authenticated user
            user_name: Display name for SA description (optional)

        Returns:
            GeneratedToken with token, expires_at, and service_account_email

        Raises:
            ServiceAccountCreationError: If SA creation fails
            ImpersonationError: If token generation fails
        """
        sa_email = await self.ensure_service_account(user_email, user_name)
        return await self.generate_token_for_service_account(sa_email)

    async def _get_or_create_service_account(
        self, user_email: str, user_name: str
    ) -> tuple[str, bool]:
        """Look up or create service account for user.

        Returns:
            Tuple of (service_account_email, was_created)

        Raises:
            ServiceAccountCreationError: If SA creation fails
        """
        # Get domain abbreviation for this email
        domain = user_email.split("@")[-1] if "@" in user_email else ""
        domain_abbrev = self._settings.get_domain_abbreviation(domain)

        account_id = sanitize_email_for_account_id(user_email, domain_abbrev)
        sa_email = f"{account_id}@{self._project_id}.iam.gserviceaccount.com"

        # Check if SA exists
        try:
            request = GetServiceAccountRequest(
                name=f"projects/{self._project_id}/serviceAccounts/{sa_email}"
            )
            await self._iam_client.get_service_account(request=request)
            return sa_email, False
        except NotFound:
            logger.info("SA not found, creating new one", extra={"sa_email": sa_email})
        except Exception as e:
            raise ServiceAccountCreationError(
                f"Failed to check service account: {e}", user_email, e
            ) from e

        # Create new service account with metadata
        created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        display_name = (
            f"AI EA for {user_name}"[:100] if user_name else f"AI EA for {user_email}"[:100]
        )
        description = f"Owner: {user_email} | Created: {created_at} | Via: ExtraSuite"[:256]

        try:
            request = CreateServiceAccountRequest(
                name=f"projects/{self._project_id}",
                account_id=account_id,
                service_account=ServiceAccount(
                    display_name=display_name,
                    description=description,
                ),
            )
            result = await self._iam_client.create_service_account(request=request)
            sa_email = result.email
        except Exception as e:
            raise ServiceAccountCreationError(
                f"Failed to create service account: {e}", user_email, e
            ) from e

        logger.info(
            "Service account created",
            extra={"user_email": user_email, "sa_email": sa_email},
        )

        # Wait for SA to propagate across GCP systems before impersonation
        await asyncio.sleep(SA_PROPAGATION_DELAY)

        return sa_email, True

    async def _impersonate_service_account(self, sa_email: str) -> tuple[str, datetime]:
        """Impersonate service account using server ADC and return token.

        Note: This uses the sync google-auth library wrapped in asyncio.to_thread
        because there's no async version of impersonated_credentials.

        Args:
            sa_email: Service account email to impersonate

        Returns:
            Tuple of (access_token, expires_at)

        Raises:
            ImpersonationError: If impersonation fails
        """
        try:
            token = await asyncio.to_thread(self._do_impersonation, sa_email)
            expires_at = datetime.now(UTC) + timedelta(seconds=self._token_lifetime_seconds)
            return token, expires_at
        except Exception as e:
            raise ImpersonationError(f"Impersonation failed: {e}", sa_email, e) from e

    def _do_impersonation(self, sa_email: str) -> str:
        """Perform the actual impersonation (blocking, runs in thread pool)."""
        source_credentials = self._get_admin_credentials()

        target_credentials = self._impersonated_credentials_class(
            source_credentials=source_credentials,
            target_principal=sa_email,
            target_scopes=TOKEN_SCOPES,
            lifetime=self._token_lifetime_seconds,
        )

        target_credentials.refresh(google_requests.Request())

        if not target_credentials.token:
            raise ImpersonationError("Failed to get impersonated token", sa_email)

        return target_credentials.token
