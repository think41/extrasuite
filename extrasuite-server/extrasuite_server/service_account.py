"""Service account management.

This module handles GCP service account creation and impersonation.
"""

import re
import time
from datetime import UTC, datetime

import google.auth
from google.auth import impersonated_credentials
from google.auth.exceptions import RefreshError
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger

from extrasuite_server.config import Settings
from extrasuite_server.oauth import SA_TOKEN_SCOPES

# Delay after SA creation to allow GCP propagation (seconds)
SA_PROPAGATION_DELAY = 3.0

# Retry settings for IAM operations
IAM_RETRY_ATTEMPTS = 3
IAM_RETRY_BASE_DELAY = 1.0  # seconds


def sanitize_email_for_account_id(email: str) -> str:
    """Convert email to valid service account ID.

    Service account IDs must:
    - Be 6-30 characters
    - Start with a letter
    - Contain only lowercase letters, numbers, and hyphens
    """
    # Take part before @
    local_part = email.split("@")[0].lower()

    # Replace invalid characters with hyphens
    account_id = re.sub(r"[^a-z0-9]", "-", local_part)

    # Remove consecutive hyphens
    account_id = re.sub(r"-+", "-", account_id)

    # Remove leading/trailing hyphens
    account_id = account_id.strip("-")

    # Ensure it starts with a letter
    if account_id and not account_id[0].isalpha():
        account_id = "ea-" + account_id

    # Prefix with ea- (executive assistant) for clarity
    if not account_id.startswith("ea-"):
        account_id = "ea-" + account_id

    # Truncate to 30 characters max
    account_id = account_id[:30].rstrip("-")

    # Ensure minimum length of 6
    if len(account_id) < 6:
        account_id = account_id + "-user"

    return account_id


def get_or_create_service_account(
    settings: Settings, user_email: str, user_name: str
) -> tuple[str, bool]:
    """Look up or create service account for user.

    Returns:
        Tuple of (service_account_email, was_created)

    Raises:
        ValueError: If Google Cloud project is not configured
        google.auth.exceptions.DefaultCredentialsError: If ADC not available
        googleapiclient.errors.HttpError: If IAM API calls fail
    """
    if not settings.google_cloud_project:
        raise ValueError("Google Cloud project not configured")

    project_id = settings.google_cloud_project
    account_id = sanitize_email_for_account_id(user_email)
    sa_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

    # Use Application Default Credentials to manage service accounts
    admin_creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    iam_service = build("iam", "v1", credentials=admin_creds)

    # Check if SA exists
    try:
        iam_service.projects().serviceAccounts().get(
            name=f"projects/{project_id}/serviceAccounts/{sa_email}"
        ).execute()
        # SA exists
        _grant_impersonation_permission(iam_service, project_id, sa_email, user_email)
        return sa_email, False
    except HttpError as e:
        if e.resp.status != 404:
            raise

    # Create new service account with metadata
    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    service_account_body = {
        "accountId": account_id,
        "serviceAccount": {
            "displayName": f"AI EA for {user_name}"[:100],
            "description": f"Owner: {user_email} | Created: {created_at} | Via: ExtraSuite"[:256],
        },
    }

    created = (
        iam_service.projects()
        .serviceAccounts()
        .create(name=f"projects/{project_id}", body=service_account_body)
        .execute()
    )
    sa_email = created["email"]

    # Wait for SA to propagate across GCP systems before setting IAM policy
    # Without this delay, IAM operations fail with 404 errors
    logger.info(
        "Waiting for SA propagation",
        extra={"sa_email": sa_email, "delay_seconds": SA_PROPAGATION_DELAY},
    )
    time.sleep(SA_PROPAGATION_DELAY)

    # Grant user permission to impersonate this SA (for future use)
    # This enables the user to use the SA even without going through ExtraSuite
    _grant_impersonation_permission(iam_service, project_id, sa_email, user_email)

    return sa_email, True


def _grant_impersonation_permission(
    iam_service, project_id: str, sa_email: str, user_email: str
) -> None:
    """Grant user permission to impersonate the service account.

    Retries with exponential backoff to handle GCP propagation delays.
    Raises exception if all retries fail - caller should handle appropriately.
    """
    member = f"user:{user_email}"
    role = "roles/iam.serviceAccountTokenCreator"
    resource = f"projects/{project_id}/serviceAccounts/{sa_email}"
    last_exception: Exception | None = None

    for attempt in range(IAM_RETRY_ATTEMPTS):
        try:
            policy = (
                iam_service.projects().serviceAccounts().getIamPolicy(resource=resource).execute()
            )

            if "bindings" not in policy:
                policy["bindings"] = []

            # Reuse existing binding if present; otherwise add one.
            binding = next((b for b in policy["bindings"] if b.get("role") == role), None)
            if binding:
                members = set(binding.get("members", []))
                if member in members:
                    logger.info(
                        "Impersonation permission already granted",
                        extra={"user_email": user_email, "sa_email": sa_email},
                    )
                    return
                members.add(member)
                binding["members"] = sorted(members)
            else:
                policy["bindings"].append({"role": role, "members": [member]})

            iam_service.projects().serviceAccounts().setIamPolicy(
                resource=resource,
                body={"policy": policy},
            ).execute()
            logger.info(
                "Granted impersonation permission",
                extra={"user_email": user_email, "sa_email": sa_email},
            )
            return

        except HttpError as e:
            last_exception = e
            # Retry on 404 (SA not yet propagated) or 409 (concurrent modification)
            if e.resp.status in (404, 409) and attempt < IAM_RETRY_ATTEMPTS - 1:
                delay = IAM_RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "IAM operation failed, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": IAM_RETRY_ATTEMPTS,
                        "delay_seconds": delay,
                        "status": e.resp.status,
                        "sa_email": sa_email,
                    },
                )
                time.sleep(delay)
                continue
            # Don't retry other errors
            raise

        except Exception as e:
            last_exception = e
            raise

    # All retries exhausted
    if last_exception:
        logger.exception(
            "Failed to grant impersonation permission after retries",
            extra={
                "user_email": user_email,
                "sa_email": sa_email,
                "attempts": IAM_RETRY_ATTEMPTS,
            },
        )
        raise last_exception


def impersonate_service_account(
    source_credentials: Credentials,
    target_sa_email: str,
    retry_on_permission_denied: bool = False,
) -> tuple[str, int]:
    """Impersonate service account and return short-lived access token.

    Args:
        source_credentials: OAuth credentials to use for impersonation
        target_sa_email: Service account email to impersonate
        retry_on_permission_denied: If True, retry on 403/404 errors (use when SA
            was just created and IAM permissions may not have propagated yet)

    Returns:
        Tuple of (access_token, expires_in_seconds)

    Raises:
        RefreshError: If the source credentials are expired or revoked
        ValueError: If the impersonation fails
    """
    max_attempts = IAM_RETRY_ATTEMPTS if retry_on_permission_denied else 1
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            # Create impersonated credentials
            target_credentials = impersonated_credentials.Credentials(
                source_credentials=source_credentials,
                target_principal=target_sa_email,
                target_scopes=SA_TOKEN_SCOPES,
                lifetime=3600,  # 1 hour
            )

            # Refresh to get the token
            target_credentials.refresh(google_requests.Request())

            if not target_credentials.token:
                raise ValueError("Failed to get impersonated token")

            # Token is valid for 1 hour
            expires_in = 3600

            return target_credentials.token, expires_in

        except RefreshError as e:
            last_exception = e
            error_str = str(e)
            # Check if this is a retryable error (permission not propagated yet)
            is_permission_error = "403" in error_str or "404" in error_str
            if retry_on_permission_denied and is_permission_error and attempt < max_attempts - 1:
                delay = IAM_RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Impersonation failed, retrying (IAM may still be propagating)",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "delay_seconds": delay,
                        "sa_email": target_sa_email,
                    },
                )
                time.sleep(delay)
                continue
            raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise ValueError("Impersonation failed after retries")
