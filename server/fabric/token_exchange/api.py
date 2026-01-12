"""Token exchange API for CLI authentication flow.

This module implements the Fabric Token Exchange flow:
1. CLI opens browser to /api/token/auth?redirect=http://localhost:<port>/callback
2. User authenticates via Google OAuth (cloud-platform scope)
3. Fabric stores OAuth credentials server-side
4. Fabric looks up or creates user's service account
5. Fabric impersonates SA to get short-lived token
6. Browser redirects to CLI localhost with token

Note: The actual OAuth callback is handled by /api/auth/callback (unified endpoint).
This module provides the /api/token/auth entry point and helper functions.
"""

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fabric.config import Settings, get_settings
from fabric.database import UserOAuthCredential

router = APIRouter(prefix="/token", tags=["token-exchange"])

# Scopes for the impersonated SA token (what the CLI can do)
SA_TOKEN_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]


class TokenResponse(BaseModel):
    """Response containing the short-lived SA token."""

    access_token: str
    expires_in: int
    token_type: str = "Bearer"
    service_account_email: str


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


def validate_redirect_uri(redirect_uri: str) -> bool:
    """Validate that redirect URI is a localhost URL (for CLI security)."""
    try:
        parsed = urlparse(redirect_uri)
        # Only allow localhost redirects for CLI
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            return False
        return parsed.scheme in ("http", "https")
    except Exception:
        return False


@router.get("/auth")
async def start_token_auth(
    redirect: str = Query(..., description="CLI localhost callback URL"),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Start OAuth flow for CLI token exchange.

    The CLI should call this with a redirect parameter pointing to its localhost server.
    Example: /api/token/auth?redirect=http://localhost:8085/on-authentication

    This endpoint creates a state token and redirects to Google OAuth.
    The callback is handled by /api/auth/callback (unified for web and CLI).
    """
    from fabric.auth.api import CLI_SCOPES, create_cli_auth_state, create_oauth_flow

    # Validate redirect URI (must be localhost for CLI)
    if not validate_redirect_uri(redirect):
        raise HTTPException(
            status_code=400,
            detail="Invalid redirect URI. Must be a localhost URL.",
        )

    # Create state token with CLI redirect info
    state = create_cli_auth_state(cli_redirect=redirect)

    # Create OAuth flow with CLI scopes, using the unified callback
    flow = create_oauth_flow(settings, CLI_SCOPES)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


def _store_oauth_credentials(db: Session, email: str, credentials: Credentials) -> None:
    """Store or update OAuth credentials in database."""
    from fabric.auth.api import CLI_SCOPES

    oauth_record = db.query(UserOAuthCredential).filter(UserOAuthCredential.email == email).first()

    scopes_json = json.dumps(list(credentials.scopes) if credentials.scopes else CLI_SCOPES)

    if oauth_record:
        # Update existing
        oauth_record.access_token = credentials.token
        oauth_record.refresh_token = credentials.refresh_token
        oauth_record.scopes = scopes_json
        oauth_record.updated_at = datetime.now(UTC)
    else:
        # Create new
        oauth_record = UserOAuthCredential(
            email=email,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            scopes=scopes_json,
        )
        db.add(oauth_record)

    db.commit()


def _get_or_create_service_account(settings: Settings, user_email: str, user_name: str) -> str:
    """Look up or create service account for user."""
    if not settings.google_cloud_project:
        raise HTTPException(
            status_code=500,
            detail="Google Cloud project not configured.",
        )

    project_id = settings.google_cloud_project
    account_id = sanitize_email_for_account_id(user_email)
    sa_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

    # Use Application Default Credentials to manage service accounts
    import google.auth

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
        return sa_email
    except HttpError as e:
        if e.resp.status != 404:
            raise

    # Create new service account with metadata
    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    service_account_body = {
        "accountId": account_id,
        "serviceAccount": {
            "displayName": f"AI EA for {user_name}"[:100],
            "description": f"Owner: {user_email} | Created: {created_at} | Via: Fabric"[
                :256
            ],
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
    # This enables the user to use the SA even without going through Fabric
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
        # Non-critical - user can still use Fabric to get tokens
        pass

    return sa_email


def _impersonate_service_account(
    source_credentials: Credentials, target_sa_email: str
) -> tuple[str, int]:
    """Impersonate service account and return short-lived access token."""
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

    # Calculate expires_in (token is valid for 1 hour)
    expires_in = 3600

    return target_credentials.token, expires_in
