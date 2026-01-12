"""Google OAuth authentication API endpoints.

Handles both web login (session cookie) and CLI login (token exchange) flows
using a unified callback endpoint.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fabric.config import Settings, get_settings
from fabric.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class UserInfo(BaseModel):
    """User information from Google OAuth."""

    email: str
    name: str
    picture: str | None = None
    hd: str | None = None  # Hosted domain (for Workspace accounts)


class SessionData(BaseModel):
    """Session data stored in signed cookie."""

    email: str
    name: str
    picture: str | None = None
    hd: str | None = None
    created_at: str


# OAuth scopes for web login (basic profile)
WEB_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# OAuth scopes for CLI login (includes cloud-platform for SA impersonation)
CLI_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cloud-platform",
]

# In-memory state storage for OAuth flow (use Redis in production)
# Format: {state: {"created_at": datetime, "flow_type": "web"|"cli", "cli_redirect": str|None}}
_oauth_states: dict[str, dict] = {}


def get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Get serializer for signing session cookies."""
    return URLSafeTimedSerializer(settings.secret_key)


def create_oauth_flow(settings: Settings, scopes: list[str]) -> Flow:
    """Create Google OAuth flow with specified scopes."""
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
            "redirect_uris": [settings.google_redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=scopes,
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


def get_current_user(
    session: Annotated[str | None, Cookie(alias="fabric_session")] = None,
    settings: Settings = Depends(get_settings),
) -> SessionData:
    """Get current user from session cookie."""
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    serializer = get_serializer(settings)
    try:
        # Session expires after 24 hours
        data = serializer.loads(session, max_age=86400)
        return SessionData(**data)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Session expired") from None
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session") from None


def get_optional_user(
    session: Annotated[str | None, Cookie(alias="fabric_session")] = None,
    settings: Settings = Depends(get_settings),
) -> SessionData | None:
    """Get current user if authenticated, None otherwise."""
    if not session:
        return None

    serializer = get_serializer(settings)
    try:
        data = serializer.loads(session, max_age=86400)
        return SessionData(**data)
    except (SignatureExpired, BadSignature):
        return None


def _cleanup_old_states() -> None:
    """Remove expired states (older than 10 minutes)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    for old_state in list(_oauth_states.keys()):
        if _oauth_states[old_state]["created_at"] < cutoff:
            del _oauth_states[old_state]


def _create_state(flow_type: str, cli_redirect: str | None = None) -> str:
    """Create and store a new OAuth state token."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "created_at": datetime.now(UTC),
        "flow_type": flow_type,
        "cli_redirect": cli_redirect,
    }
    _cleanup_old_states()
    return state


@router.get("/google")
async def google_login(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    """Initiate Google OAuth login flow for web."""
    flow = create_oauth_flow(settings, WEB_SCOPES)
    state = _create_state(flow_type="web")

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


@router.get("/callback", response_model=None)
async def google_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback for both web and CLI flows."""
    from fabric.logging import logger

    # Verify state token
    if state not in _oauth_states:
        logger.warning("Invalid state token received")
        raise HTTPException(status_code=400, detail="Invalid state token")

    state_data = _oauth_states.pop(state)

    # Check state expiry (10 minutes)
    if datetime.now(UTC) - state_data["created_at"] > timedelta(minutes=10):
        logger.warning("Expired state token received")
        raise HTTPException(status_code=400, detail="State token expired")

    flow_type = state_data.get("flow_type", "web")
    cli_redirect = state_data.get("cli_redirect")

    # Use appropriate scopes based on flow type
    scopes = CLI_SCOPES if flow_type == "cli" else WEB_SCOPES
    flow = create_oauth_flow(settings, scopes)

    # Exchange code for tokens
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error(f"Failed to fetch token: {e}")
        if flow_type == "cli" and cli_redirect:
            return _cli_error_response(f"Failed to fetch token: {e}", cli_redirect)
        raise HTTPException(status_code=400, detail=f"Failed to fetch token: {e}") from None

    # Get credentials and verify ID token
    credentials = flow.credentials
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as e:
        logger.error(f"Failed to verify token: {e}")
        if flow_type == "cli" and cli_redirect:
            return _cli_error_response(f"Failed to verify token: {e}", cli_redirect)
        raise HTTPException(status_code=400, detail=f"Failed to verify token: {e}") from None

    user_email = id_info.get("email", "")
    user_name = id_info.get("name", "")

    logger.info(f"OAuth callback successful for user: {user_email}, flow: {flow_type}")

    # Handle CLI flow - token exchange
    if flow_type == "cli":
        return await _handle_cli_callback(
            credentials, user_email, user_name, cli_redirect, settings, db
        )

    # Handle web flow - session cookie
    return _handle_web_callback(id_info, settings)


def _handle_web_callback(id_info: dict, settings: Settings) -> RedirectResponse:
    """Handle web OAuth callback - create session and redirect to frontend."""
    session_data = SessionData(
        email=id_info.get("email", ""),
        name=id_info.get("name", ""),
        picture=id_info.get("picture"),
        hd=id_info.get("hd"),
        created_at=datetime.now(UTC).isoformat(),
    )

    # Sign session data
    serializer = get_serializer(settings)
    signed_session = serializer.dumps(session_data.model_dump())

    # Redirect to frontend with session cookie
    frontend_url = settings.allowed_origins_list[0] if settings.allowed_origins_list else "/"
    response = RedirectResponse(url=frontend_url)
    response.set_cookie(
        key="fabric_session",
        value=signed_session,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=86400,  # 24 hours
    )

    return response


async def _handle_cli_callback(
    credentials,
    user_email: str,
    user_name: str,
    cli_redirect: str,
    settings: Settings,
    db: Session,
) -> RedirectResponse | HTMLResponse:
    """Handle CLI OAuth callback - exchange for SA token and redirect to localhost."""
    from fabric.logging import logger
    from fabric.token_exchange.api import (
        _get_or_create_service_account,
        _impersonate_service_account,
        _store_oauth_credentials,
    )

    # Store OAuth credentials in database
    try:
        _store_oauth_credentials(db, user_email, credentials)
    except Exception as e:
        logger.error(f"Failed to store credentials: {e}")
        return _cli_error_response(f"Failed to store credentials: {e}", cli_redirect)

    # Look up or create service account
    try:
        sa_email = _get_or_create_service_account(settings, user_email, user_name)
        logger.info(f"Service account for {user_email}: {sa_email}")
    except Exception as e:
        logger.error(f"Failed to setup service account: {e}")
        return _cli_error_response(f"Failed to setup service account: {e}", cli_redirect)

    # Update SA email in database
    try:
        from fabric.database import UserOAuthCredential

        oauth_record = (
            db.query(UserOAuthCredential).filter(UserOAuthCredential.email == user_email).first()
        )
        if oauth_record:
            oauth_record.service_account_email = sa_email
            db.commit()
    except Exception:
        pass  # Non-critical, continue

    # Impersonate SA to get short-lived token
    try:
        sa_token, expires_in = _impersonate_service_account(credentials, sa_email)
        logger.info(f"Successfully impersonated SA {sa_email}")
    except Exception as e:
        logger.error(f"Failed to get SA token: {e}")
        return _cli_error_response(f"Failed to get SA token: {e}", cli_redirect)

    # Redirect to CLI with token
    params = {
        "token": sa_token,
        "expires_in": str(expires_in),
        "service_account": sa_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    return RedirectResponse(url=redirect_url)


def _cli_error_response(error: str, redirect: str | None) -> RedirectResponse | HTMLResponse:
    """Create error response for CLI flow."""
    from fabric.token_exchange.api import validate_redirect_uri

    if redirect and validate_redirect_uri(redirect):
        params = {"error": error}
        return RedirectResponse(url=f"{redirect}?{urlencode(params)}")
    else:
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


# Export for use by token_exchange module
def create_cli_auth_state(cli_redirect: str) -> str:
    """Create OAuth state for CLI flow (used by token_exchange module)."""
    return _create_state(flow_type="cli", cli_redirect=cli_redirect)


@router.get("/me")
async def get_me(user: SessionData = Depends(get_current_user)) -> UserInfo:
    """Get current authenticated user info."""
    return UserInfo(
        email=user.email,
        name=user.name,
        picture=user.picture,
        hd=user.hd,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Logout current user by clearing session cookie."""
    response.delete_cookie(key="fabric_session")
    return {"status": "logged_out"}
