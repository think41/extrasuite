"""Service account management.

This module handles GCP service account creation and impersonation.
"""

import re
from datetime import UTC, datetime

import google.auth
from fastapi import HTTPException
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gwg_server.config import Settings
from gwg_server.logging import logger
from gwg_server.oauth import SA_TOKEN_SCOPES


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
    """
    if not settings.google_cloud_project:
        raise HTTPException(
            status_code=500,
            detail="Google Cloud project not configured.",
        )

    project_id = settings.google_cloud_project
    account_id = sanitize_email_for_account_id(user_email)
    sa_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

    # Use Application Default Credentials to manage service accounts
    try:
        admin_creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        iam_service = build("iam", "v1", credentials=admin_creds)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize IAM service: {e}",
        ) from None

    # Check if SA exists
    try:
        iam_service.projects().serviceAccounts().get(
            name=f"projects/{project_id}/serviceAccounts/{sa_email}"
        ).execute()
        # SA exists
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
            "description": f"Owner: {user_email} | Created: {created_at} | Via: GWG"[:256],
        },
    }

    try:
        created = (
            iam_service.projects()
            .serviceAccounts()
            .create(name=f"projects/{project_id}", body=service_account_body)
            .execute()
        )
        sa_email = created["email"]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create service account: {e}",
        ) from None

    # Grant user permission to impersonate this SA (for future use)
    # This enables the user to use the SA even without going through GWG
    _grant_impersonation_permission(iam_service, project_id, sa_email, user_email)

    return sa_email, True


def _grant_impersonation_permission(
    iam_service, project_id: str, sa_email: str, user_email: str
) -> None:
    """Grant user permission to impersonate the service account.

    Non-critical operation - logs warning on failure but doesn't raise.
    """
    try:
        policy = (
            iam_service.projects()
            .serviceAccounts()
            .getIamPolicy(resource=f"projects/{project_id}/serviceAccounts/{sa_email}")
            .execute()
        )

        # Add serviceAccountTokenCreator role for the user
        binding = {
            "role": "roles/iam.serviceAccountTokenCreator",
            "members": [f"user:{user_email}"],
        }

        if "bindings" not in policy:
            policy["bindings"] = []
        policy["bindings"].append(binding)

        iam_service.projects().serviceAccounts().setIamPolicy(
            resource=f"projects/{project_id}/serviceAccounts/{sa_email}",
            body={"policy": policy},
        ).execute()
    except Exception:
        # Non-critical - user can still use GWG to get tokens
        logger.warning(
            "Failed to grant impersonation permission",
            extra={"user_email": user_email, "sa_email": sa_email},
        )


def impersonate_service_account(
    source_credentials: Credentials, target_sa_email: str
) -> tuple[str, int]:
    """Impersonate service account and return short-lived access token.

    Returns:
        Tuple of (access_token, expires_in_seconds)

    Raises:
        RefreshError: If the source credentials are expired or revoked
        ValueError: If the impersonation fails
    """
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
