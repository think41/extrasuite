"""Token exchange API for CLI authentication flow.

This module implements the ExtraSuite Token Exchange flow:
1. CLI opens browser to /api/token/auth?port=<port>
2. User authenticates via Google OAuth (cloud-platform scope)
3. ExtraSuite stores OAuth credentials in Firestore
4. ExtraSuite looks up or creates user's service account
5. ExtraSuite impersonates SA to get short-lived token
6. Browser redirects to localhost:{port}/on-authentication with token

Note: The actual OAuth callback is handled by /api/auth/callback.
This module provides the /api/token/auth entry point.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from google.auth.exceptions import RefreshError
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from loguru import logger

from extrasuite_server.config import Settings, get_settings
from extrasuite_server.database import Database, get_database
from extrasuite_server.oauth import CLI_SCOPES, create_cli_auth_state, create_oauth_flow
from extrasuite_server.rate_limit import limiter
from extrasuite_server.service_account import impersonate_service_account

router = APIRouter(prefix="/token", tags=["token-exchange"])

# Valid port range for CLI callback
MIN_PORT = 1024
MAX_PORT = 65535


def build_cli_redirect_url(port: int) -> str:
    """Build CLI redirect URL from port - always localhost."""
    return f"http://localhost:{port}/on-authentication"


async def _get_session_email_if_valid(request: Request, db: Database) -> str | None:
    """Get email from session if user has valid credentials in Firestore.

    Returns None if no session exists, user has no credentials, or refresh token is missing.
    """
    email = request.session.get("email")
    if not email:
        return None

    user_creds = await db.get_user_credentials(email)
    if not user_creds or not user_creds.refresh_token:
        return None

    return email


@router.get("/auth")
@limiter.limit("10/minute")
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
    The callback is handled by /api/auth/callback.
    """
    # Build the redirect URL - always localhost with fixed path
    cli_redirect = build_cli_redirect_url(port)

    # Check if user has a valid session with stored credentials
    email = await _get_session_email_if_valid(request, db)
    if email:
        logger.info("Attempting token refresh", extra={"email": email, "cli_port": port})

        redirect_response = await _try_refresh_token(db, email, cli_redirect, settings)
        if redirect_response:
            return redirect_response

        # Refresh failed, fall through to OAuth flow
        logger.info("Token refresh failed, starting OAuth flow", extra={"email": email})

    # No valid session or refresh failed, start OAuth flow
    logger.info("Starting OAuth flow", extra={"cli_port": port})

    # Create state token with CLI redirect info (stored in Firestore)
    state = await create_cli_auth_state(db, cli_redirect=cli_redirect)

    # Create OAuth flow with CLI scopes
    flow = create_oauth_flow(settings, CLI_SCOPES)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


async def _try_refresh_token(
    db: Database, email: str, cli_redirect: str, settings: Settings
) -> RedirectResponse | None:
    """Try to refresh the token using stored OAuth credentials.

    Returns a RedirectResponse with the new token if successful, None otherwise.
    """
    # Get stored credentials
    user_creds = await db.get_user_credentials(email)
    if not user_creds or not user_creds.refresh_token:
        logger.warning("No stored credentials", extra={"email": email})
        return None

    # Get service account email
    sa_email = user_creds.service_account_email
    if not sa_email:
        logger.warning("No service account for user", extra={"email": email})
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
    try:
        if credentials.expired or not credentials.valid:
            credentials.refresh(google_requests.Request())
            # Update stored credentials with new access token
            # Use original refresh_token since it's already validated above
            await db.store_user_credentials(
                email=email,
                access_token=credentials.token,
                refresh_token=user_creds.refresh_token,
                scopes=user_creds.scopes,
                service_account_email=sa_email,
            )
    except RefreshError as e:
        # Token was revoked or expired - user needs to re-authenticate
        logger.warning(
            "OAuth refresh token revoked or expired",
            extra={"email": email, "error": str(e)},
        )
        return None
    except Exception:
        logger.exception(
            "Failed to refresh OAuth credentials",
            extra={"email": email},
        )
        return None

    # Impersonate SA to get short-lived token
    try:
        sa_token, expires_in = impersonate_service_account(credentials, sa_email)
    except RefreshError as e:
        logger.exception(
            "Impersonation failed - credentials may be revoked or IAM denied",
            extra={"email": email, "service_account": sa_email, "error": str(e)},
        )
        return None
    except Exception:
        logger.exception(
            "Failed to impersonate service account",
            extra={"email": email, "service_account": sa_email},
        )
        return None

    # Redirect to CLI with token
    params = {
        "token": sa_token,
        "expires_in": str(expires_in),
        "service_account": sa_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"

    logger.info("Token refreshed", extra={"email": email, "service_account": sa_email})
    return RedirectResponse(url=redirect_url)
