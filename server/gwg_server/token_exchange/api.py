"""Token exchange API for CLI authentication flow.

This module implements the Google Workspace Gateway Token Exchange flow:
1. CLI opens browser to /api/token/auth?port=<port>
2. User authenticates via Google OAuth (cloud-platform scope)
3. GWG stores OAuth credentials in Firestore
4. GWG looks up or creates user's service account
5. GWG impersonates SA to get short-lived token
6. Browser redirects to localhost:{port}/on-authentication with token

Note: The actual OAuth callback is handled by /api/auth/callback (unified endpoint).
This module provides the /api/token/auth entry point and helper functions.
"""

import re
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gwg_server.config import Settings, get_settings
from gwg_server.database import Database, get_database

router = APIRouter(prefix="/token", tags=["token-exchange"])

# Scopes for the impersonated SA token (what the CLI can do)
SA_TOKEN_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]

# Valid port range for CLI callback
MIN_PORT = 1024
MAX_PORT = 65535


def build_cli_redirect_url(port: int) -> str:
    """Build CLI redirect URL from port - always localhost."""
    return f"http://localhost:{port}/on-authentication"


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


@router.get("/auth")
async def start_token_auth(
    request: Request,
    port: int = Query(..., description="CLI localhost callback port", ge=MIN_PORT, le=MAX_PORT),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
) -> RedirectResponse:
    """Start OAuth flow for CLI token exchange.

    The CLI should call this with a port parameter for its localhost server.
    Example: /api/token/auth?port=8085

    The server will always redirect to http://localhost:{port}/on-authentication
    to prevent open redirect vulnerabilities.

    If the user has a valid session with stored OAuth credentials, the token
    will be refreshed without requiring re-authentication.

    Otherwise, this endpoint creates a state token and redirects to Google OAuth.
    The callback is handled by /api/auth/callback (unified for web and CLI).
    """
    from gwg_server.logging import logger
    from gwg_server.session import get_session_email

    # Build the redirect URL - always localhost with fixed path
    cli_redirect = build_cli_redirect_url(port)

    # Check if user has a valid session with stored credentials
    email = get_session_email(request, db)
    if email:
        logger.info(f"Found existing session for {email}, attempting token refresh")
        try:
            redirect_response = _try_refresh_token(db, email, cli_redirect, settings)
            if redirect_response:
                logger.info(f"Successfully refreshed token for {email}")
                return redirect_response
        except Exception as e:
            logger.warning(f"Token refresh failed for {email}: {e}, falling back to OAuth")

    # No valid session or refresh failed, start OAuth flow
    from gwg_server.auth.api import CLI_SCOPES, create_cli_auth_state, create_oauth_flow

    # Create state token with CLI redirect info
    state = create_cli_auth_state(cli_redirect=cli_redirect)

    # Create OAuth flow with CLI scopes, using the unified callback
    flow = create_oauth_flow(settings, CLI_SCOPES)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


def _try_refresh_token(
    db: Database, email: str, cli_redirect: str, settings: Settings
) -> RedirectResponse | None:
    """Try to refresh the token using stored OAuth credentials.

    Returns a RedirectResponse with the new token if successful, None otherwise.
    """
    # Get stored credentials
    user_creds = db.get_user_credentials(email)
    if not user_creds or not user_creds.refresh_token:
        return None

    # Get service account email
    sa_email = user_creds.service_account_email
    if not sa_email:
        return None

    # Create OAuth credentials from stored tokens
    credentials = Credentials(
        token=user_creds.access_token,
        refresh_token=user_creds.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=user_creds.scopes,
    )

    # Refresh the credentials if needed
    if credentials.expired:
        credentials.refresh(google_requests.Request())
        # Update stored credentials with new access token
        db.store_user_credentials(
            email=email,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            scopes=user_creds.scopes,
            service_account_email=sa_email,
        )

    # Impersonate SA to get short-lived token
    sa_token, expires_in = _impersonate_service_account(credentials, sa_email)

    # Redirect to CLI with token
    params = {
        "token": sa_token,
        "expires_in": str(expires_in),
        "service_account": sa_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    return RedirectResponse(url=redirect_url)


def _store_oauth_credentials(db: Database, email: str, credentials: Credentials) -> None:
    """Store or update OAuth credentials in Firestore."""
    from gwg_server.auth.api import CLI_SCOPES

    scopes = list(credentials.scopes) if credentials.scopes else CLI_SCOPES
    db.store_user_credentials(
        email=email,
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        scopes=scopes,
    )


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
