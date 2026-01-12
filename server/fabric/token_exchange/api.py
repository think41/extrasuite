"""Token exchange API for CLI authentication flow.

This module implements the Fabric Token Exchange flow:
1. CLI opens browser to /api/token/auth?redirect=http://localhost:<port>/callback
2. User authenticates via Google OAuth (cloud-platform scope)
3. Fabric stores OAuth credentials server-side
4. Fabric looks up or creates user's service account
5. Fabric impersonates SA to get short-lived token
6. Browser redirects to CLI localhost with token
"""

import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fabric.config import Settings, get_settings
from fabric.database import UserOAuthCredential, get_db

router = APIRouter(prefix="/token", tags=["token-exchange"])

# Scopes needed for impersonation
OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cloud-platform",
]

# Scopes for the impersonated SA token (what the CLI can do)
SA_TOKEN_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]

# In-memory state storage for OAuth flow (use Redis in production)
_oauth_states: dict[str, dict] = {}


class TokenResponse(BaseModel):
    """Response containing the short-lived SA token."""

    access_token: str
    expires_in: int
    token_type: str = "Bearer"
    service_account_email: str


def create_token_oauth_flow(settings: Settings, redirect_uri: str) -> Flow:
    """Create Google OAuth flow for token exchange."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow


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
    """
    # Validate redirect URI (must be localhost for CLI)
    if not validate_redirect_uri(redirect):
        raise HTTPException(
            status_code=400,
            detail="Invalid redirect URI. Must be a localhost URL.",
        )

    # Create OAuth flow with our callback
    callback_uri = f"{settings.google_redirect_uri.rsplit('/', 1)[0]}/token/callback"
    flow = create_token_oauth_flow(settings, callback_uri)

    # Generate state token with redirect info
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "redirect": redirect,
        "created_at": datetime.now(UTC),
    }

    # Clean up old states (older than 10 minutes)
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    for old_state in list(_oauth_states.keys()):
        if _oauth_states[old_state]["created_at"] < cutoff:
            del _oauth_states[old_state]

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def token_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle OAuth callback and redirect to CLI with token.

    This endpoint:
    1. Exchanges the auth code for tokens
    2. Stores OAuth credentials in database
    3. Looks up or creates user's service account
    4. Impersonates SA to get short-lived token
    5. Redirects to CLI localhost with token
    """
    # Verify state token
    if state not in _oauth_states:
        return _error_response("Invalid state token", None)

    state_data = _oauth_states.pop(state)

    # Check state expiry
    if datetime.now(UTC) - state_data["created_at"] > timedelta(minutes=10):
        return _error_response("State token expired", state_data["redirect"])

    cli_redirect = state_data["redirect"]

    # Exchange code for tokens
    callback_uri = f"{settings.google_redirect_uri.rsplit('/', 1)[0]}/token/callback"
    flow = create_token_oauth_flow(settings, callback_uri)
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        return _error_response(f"Failed to fetch token: {e}", cli_redirect)

    credentials = flow.credentials

    # Verify ID token and get user info
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as e:
        return _error_response(f"Failed to verify token: {e}", cli_redirect)

    user_email = id_info.get("email", "")
    if not user_email:
        return _error_response("No email in token", cli_redirect)

    # Store OAuth credentials in database
    try:
        _store_oauth_credentials(db, user_email, credentials)
    except Exception as e:
        return _error_response(f"Failed to store credentials: {e}", cli_redirect)

    # Look up or create service account
    try:
        sa_email = _get_or_create_service_account(
            settings, user_email, id_info.get("name", user_email)
        )
    except Exception as e:
        return _error_response(f"Failed to setup service account: {e}", cli_redirect)

    # Update SA email in database
    try:
        oauth_record = db.query(UserOAuthCredential).filter(
            UserOAuthCredential.email == user_email
        ).first()
        if oauth_record:
            oauth_record.service_account_email = sa_email
            db.commit()
    except Exception:
        pass  # Non-critical, continue

    # Impersonate SA to get short-lived token
    try:
        sa_token, expires_in = _impersonate_service_account(credentials, sa_email)
    except Exception as e:
        return _error_response(f"Failed to get SA token: {e}", cli_redirect)

    # Redirect to CLI with token
    params = {
        "token": sa_token,
        "expires_in": str(expires_in),
        "service_account": sa_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    return RedirectResponse(url=redirect_url)


def _error_response(error: str, redirect: str | None) -> RedirectResponse | HTMLResponse:
    """Create error response - redirect with error or HTML page."""
    if redirect and validate_redirect_uri(redirect):
        params = {"error": error}
        return RedirectResponse(url=f"{redirect}?{urlencode(params)}")
    else:
        # Show error page if no valid redirect
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: sans-serif; padding: 40px;">
                <h1>Authentication Error</h1>
                <p style="color: red;">{error}</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """,
            status_code=400,
        )


def _store_oauth_credentials(db: Session, email: str, credentials: Credentials) -> None:
    """Store or update OAuth credentials in database."""
    oauth_record = db.query(UserOAuthCredential).filter(UserOAuthCredential.email == email).first()

    scopes_json = json.dumps(list(credentials.scopes) if credentials.scopes else OAUTH_SCOPES)

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


def _get_or_create_service_account(
    settings: Settings, user_email: str, user_name: str
) -> str:
    """Look up or create service account for user."""
    if not settings.google_cloud_project:
        raise HTTPException(
            status_code=500,
            detail="Google Cloud project not configured.",
        )

    project_id = settings.google_cloud_project
    account_id = sanitize_email_for_account_id(user_email)
    sa_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

    # Use admin credentials to manage service accounts
    from google.oauth2 import service_account as sa_module

    try:
        admin_creds = sa_module.Credentials.from_service_account_file(
            "credentials/admin-service-account.json",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
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
            "description": f"Owner: {user_email} | Created: {created_at} | Via: Fabric Portal"[
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
