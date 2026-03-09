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
import base64
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import google.auth
from google.api_core.exceptions import NotFound
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
from google.auth.transport.requests import AuthorizedSession
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


class DelegationError(TokenGeneratorError):
    """Raised when domain-wide delegation token generation fails."""

    def __init__(self, message: str, user_email: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.user_email = user_email
        self.cause = cause


class OAuthTokenError(TokenGeneratorError):
    """Raised when exchanging an OAuth refresh token for an access token fails."""

    def __init__(self, message: str, user_email: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.user_email = user_email
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

    async def set_refresh_token(self, email: str, encrypted: str, scopes: str) -> None: ...


class SettingsProtocol(Protocol):
    """Protocol for settings needed by TokenGenerator."""

    google_cloud_project: str
    token_expiry_minutes: int
    google_client_id: str
    google_client_secret: str

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
        encryptor: Any = None,  # RefreshTokenEncryptor | None — avoid circular import
    ) -> None:
        """Initialize TokenGenerator.

        Args:
            database: Database instance for user/SA lookups
            settings: Settings instance for project ID and domain abbreviations
            iam_client: Optional IAM client instance (injectable for testing).
                If not provided, a real client will be created.
            impersonated_credentials_class: Class for creating impersonated credentials
                (injectable for testing)
            encryptor: RefreshTokenEncryptor instance required for OAuth mode.
                If None, generate_oauth_token() will raise OAuthTokenError.
        """
        self._db = database
        self._settings = settings
        self._iam_client = iam_client if iam_client is not None else IAMAsyncClient()
        self._impersonated_credentials_class = impersonated_credentials_class
        self._admin_creds: Any = None
        self._encryptor = encryptor  # RefreshTokenEncryptor | None

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

    async def generate_delegated_token(self, user_email: str, scopes: list[str]) -> GeneratedToken:
        """Generate a delegated access token for a user via domain-wide delegation.

        Uses IAM signBlob to sign a JWT asserting the user's identity,
        then exchanges it for an access token at Google's token endpoint.

        Args:
            user_email: Email of the user to impersonate
            scopes: List of OAuth scope URLs to request

        Returns:
            GeneratedToken with token, expires_at, and service_account_email (the SA used)

        Raises:
            DelegationError: If token generation fails
        """
        try:
            # Check SA exists first: ensure_service_account() is called during session
            # establishment, so this should always succeed. A missing SA here indicates a
            # logic error (e.g. session issued without going through Phase 1). Checking
            # before the expensive delegation call avoids a wasted network round-trip.
            sa_email = await self._db.get_service_account_email(user_email)
            if not sa_email:
                raise DelegationError(
                    f"Service account not found for {user_email}. "
                    "Session may have been issued before service account was provisioned.",
                    user_email,
                )

            token, expires_at = await asyncio.to_thread(self._do_delegation, user_email, scopes)

            logger.info(
                "Delegated token generated",
                extra={"user_email": user_email, "scopes": scopes},
            )

            return GeneratedToken(
                token=token,
                expires_at=expires_at,
                service_account_email=sa_email,
            )
        except DelegationError:
            raise
        except Exception as e:
            raise DelegationError(f"Domain-wide delegation failed: {e}", user_email, e) from e

    def _do_delegation(self, user_email: str, scopes: list[str]) -> tuple[str, datetime]:
        """Perform domain-wide delegation token generation (blocking, runs in thread pool).

        1. Get server SA email from ADC
        2. Build JWT with sub=user_email
        3. Sign JWT using IAM signBlob API
        4. Exchange signed JWT for access token
        """
        source_credentials = self._get_admin_credentials()
        source_credentials.refresh(google_requests.Request())

        # Get server SA email
        sa_email = getattr(source_credentials, "service_account_email", None)
        if not sa_email:
            # On Cloud Run, credentials are Compute metadata-based
            sa_email = getattr(source_credentials, "_service_account_email", None)
        if not sa_email:
            # Fall back to metadata server
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                sa_email = resp.read().decode()

        now = int(time.time())
        exp = now + self._token_lifetime_seconds

        # Build JWT payload
        payload = {
            "iss": sa_email,
            "sub": user_email,
            "scope": " ".join(scopes),
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": exp,
        }

        # Build unsigned JWT
        header = {"alg": "RS256", "typ": "JWT"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
        unsigned_jwt = header_b64 + b"." + payload_b64

        # Sign using IAM signBlob API
        authed_session = AuthorizedSession(source_credentials)
        sign_url = f"https://iam.googleapis.com/v1/projects/-/serviceAccounts/{sa_email}:signBlob"
        sign_response = authed_session.post(
            sign_url,
            json={"bytesToSign": base64.b64encode(unsigned_jwt).decode()},
        )
        sign_response.raise_for_status()
        signed_bytes = base64.b64decode(sign_response.json()["signature"])

        # Build signed JWT
        signature_b64 = base64.urlsafe_b64encode(signed_bytes).rstrip(b"=")
        signed_jwt = unsigned_jwt + b"." + signature_b64

        # Exchange JWT for access token
        token_request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": signed_jwt.decode(),
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(token_request, timeout=30) as resp:
            token_data = json.loads(resp.read().decode())

        expires_at = datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 3600))

        return token_data["access_token"], expires_at

    async def generate_oauth_token(
        self, user_email: str, encrypted_token: str, scopes: list[str]
    ) -> GeneratedToken:
        """Exchange a stored encrypted refresh token for a scoped access token.

        Args:
            user_email: Authenticated user email (for audit/errors).
            encrypted_token: AES-256-GCM encrypted refresh token from Firestore.
            scopes: Minimum scope URLs for this command (subset of consented scopes).

        Returns:
            GeneratedToken with token, expires_at, and service_account_email="".

        Raises:
            OAuthTokenError: On missing encryptor, decryption failure,
                invalid_grant (expired/revoked token), or network error.
        """
        if self._encryptor is None:
            raise OAuthTokenError(
                "OAuth encryptor not configured — server is not in OAuth mode",
                user_email,
            )

        try:
            plaintext_token = self._encryptor.decrypt(encrypted_token)
        except ValueError as e:
            raise OAuthTokenError(
                f"Failed to decrypt refresh token for {user_email}: {e}",
                user_email,
                e,
            ) from e

        try:
            token_data = await asyncio.to_thread(
                self._do_oauth_exchange, user_email, plaintext_token, scopes
            )
        except OAuthTokenError:
            raise
        except Exception as e:
            raise OAuthTokenError(
                f"OAuth token exchange failed for {user_email}: {e}", user_email, e
            ) from e

        # Handle refresh token rotation: if Google issues a new refresh_token, store it.
        new_refresh_token = token_data.get("refresh_token")
        if new_refresh_token:
            try:
                new_encrypted = self._encryptor.encrypt(new_refresh_token)
                await self._db.set_refresh_token(user_email, new_encrypted, " ".join(scopes))
                logger.info(
                    "Google issued new refresh_token; updated in Firestore",
                    extra={"user_email": user_email},
                )
            except Exception as e:
                # Log but do not block the token response — the old token may still be valid
                logger.error(
                    "Failed to persist rotated refresh_token",
                    extra={"user_email": user_email, "error": str(e)},
                )

        expires_at = datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 3600))

        logger.info(
            "OAuth access token generated",
            extra={"user_email": user_email, "scopes": scopes},
        )

        return GeneratedToken(
            token=token_data["access_token"],
            expires_at=expires_at,
            service_account_email="",
        )

    def _do_oauth_exchange(
        self, user_email: str, plaintext_token: str, scopes: list[str]
    ) -> dict:
        """Exchange refresh token for access token (blocking, runs in thread pool).

        Args:
            user_email: Used only for error messages.
            plaintext_token: The decrypted refresh token.
            scopes: Minimum OAuth scope URLs to request.

        Returns:
            Parsed JSON response from Google's token endpoint.

        Raises:
            OAuthTokenError: On invalid_grant or other Google errors.
        """
        import json as _json  # noqa: PLC0415 — local import to keep module-level clean

        data = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": plaintext_token,
                "scope": " ".join(scopes),
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
            }
        ).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return _json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                error_body = _json.loads(e.read().decode())
                error_code = error_body.get("error", "")
            except Exception:
                error_code = ""

            if error_code == "invalid_grant":
                raise OAuthTokenError(
                    "OAuth credentials expired or revoked — "
                    "run 'extrasuite auth login' to re-authenticate",
                    user_email,
                    e,
                ) from e
            raise OAuthTokenError(
                f"Google token endpoint returned HTTP {e.code}: {error_code or str(e)}",
                user_email,
                e,
            ) from e
        except Exception as e:
            raise OAuthTokenError(
                f"Network error during OAuth token exchange: {e}", user_email, e
            ) from e

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
