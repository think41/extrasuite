"""Google OAuth authentication API endpoints.

Handles CLI authentication flow via token exchange.
Entry point: /api/token/auth redirects here after Google OAuth.
"""

import contextlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

from gwg_server.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


# OAuth scopes for CLI login (includes cloud-platform for SA impersonation)
CLI_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cloud-platform",
]

# In-memory state storage for OAuth flow
# Note: State tokens are short-lived (10 min) and only used during OAuth redirect
_oauth_states: dict[str, dict] = {}


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


def _cleanup_old_states() -> None:
    """Remove expired states (older than 10 minutes)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    for old_state in list(_oauth_states.keys()):
        if _oauth_states[old_state]["created_at"] < cutoff:
            del _oauth_states[old_state]


def create_cli_auth_state(cli_redirect: str) -> str:
    """Create and store a new OAuth state token for CLI flow."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "created_at": datetime.now(UTC),
        "cli_redirect": cli_redirect,
    }
    _cleanup_old_states()
    return state


@router.get("/callback", response_model=None)
async def google_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
):
    """Handle Google OAuth callback for CLI flow."""
    from gwg_server.logging import logger

    # Verify state token
    if state not in _oauth_states:
        logger.warning("Invalid state token received")
        raise HTTPException(status_code=400, detail="Invalid state token")

    state_data = _oauth_states.pop(state)

    # Check state expiry (10 minutes)
    if datetime.now(UTC) - state_data["created_at"] > timedelta(minutes=10):
        logger.warning("Expired state token received")
        raise HTTPException(status_code=400, detail="State token expired")

    cli_redirect = state_data.get("cli_redirect")
    if not cli_redirect:
        raise HTTPException(status_code=400, detail="Missing CLI redirect")

    # Create OAuth flow with CLI scopes
    flow = create_oauth_flow(settings, CLI_SCOPES)

    # Exchange code for tokens
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error(f"Failed to fetch token: {e}")
        return _cli_error_response(f"Failed to fetch token: {e}", cli_redirect)

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
        return _cli_error_response(f"Failed to verify token: {e}", cli_redirect)

    user_email = id_info.get("email", "")
    user_name = id_info.get("name", "")

    logger.info(f"OAuth callback successful for user: {user_email}")

    # Handle CLI flow - token exchange
    return await _handle_cli_callback(credentials, user_email, user_name, cli_redirect, settings)


async def _handle_cli_callback(
    credentials,
    user_email: str,
    user_name: str,
    cli_redirect: str,
    settings: Settings,
) -> RedirectResponse | HTMLResponse:
    """Handle CLI OAuth callback - exchange for SA token and redirect to localhost."""
    from gwg_server.database import update_service_account_email
    from gwg_server.logging import logger
    from gwg_server.session import create_user_session
    from gwg_server.token_exchange.api import (
        _get_or_create_service_account,
        _impersonate_service_account,
        _store_oauth_credentials,
    )

    # Store OAuth credentials in Firestore
    try:
        _store_oauth_credentials(user_email, credentials)
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

    # Update SA email in Firestore
    with contextlib.suppress(Exception):
        update_service_account_email(user_email, sa_email)

    # Impersonate SA to get short-lived token
    try:
        sa_token, expires_in = _impersonate_service_account(credentials, sa_email)
        logger.info(f"Successfully impersonated SA {sa_email}")
    except Exception as e:
        logger.error(f"Failed to get SA token: {e}")
        return _cli_error_response(f"Failed to get SA token: {e}", cli_redirect)

    # Create redirect response with token
    params = {
        "token": sa_token,
        "expires_in": str(expires_in),
        "service_account": sa_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    response = RedirectResponse(url=redirect_url)

    # Create a session for the user so they don't need to re-authenticate
    try:
        create_user_session(response, user_email)
        logger.info(f"Created session for {user_email}")
    except Exception as e:
        logger.warning(f"Failed to create session: {e}")
        # Non-critical, continue without session

    return response


def _cli_error_response(error: str, redirect: str | None) -> RedirectResponse | HTMLResponse:
    """Create error response for CLI flow.

    The redirect URL was already validated when the state was created,
    so we can trust it here. It will always be a localhost URL.
    """
    if redirect:
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
