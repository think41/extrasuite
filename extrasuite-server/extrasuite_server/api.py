"""REST API endpoints for ExtraSuite.

This module contains all HTTP endpoints. Business logic is delegated to:
- TokenGenerator: Service account token generation
- Database: Credential storage and OAuth state management

Endpoints:
- GET /api/token/auth     - CLI entry point, starts OAuth or refreshes token
- GET /api/auth/callback  - OAuth callback, exchanges code for token
- GET /api/health         - Health check
- GET /api/health/ready   - Readiness check
"""

import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from loguru import logger
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from slowapi import Limiter
from slowapi.util import get_remote_address

from extrasuite_server.config import Settings, get_settings
from extrasuite_server.database import Database, get_database
from extrasuite_server.token_generator import (
    ImpersonationError,
    ServiceAccountCreationError,
    TokenGenerator,
)

# Reduced OAuth scopes - only what we need to identify the user
# We use server's ADC for SA impersonation, NOT user's OAuth credentials
CLI_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Rate limiter instance - will be configured by main.py
limiter = Limiter(key_func=get_remote_address)

# Valid port range for CLI callback
MIN_PORT = 1024
MAX_PORT = 65535

router = APIRouter()


# =============================================================================
# Health Endpoints
# =============================================================================


@router.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "extrasuite-server"}


@router.get("/health/ready")
async def readiness_check() -> dict:
    """Readiness check for Kubernetes/Cloud Run."""
    settings = get_settings()
    return {
        "status": "ready",
        "service": "extrasuite-server",
        "environment": settings.environment,
    }


# =============================================================================
# User Info Endpoints
# =============================================================================


@router.get("/users/me")
async def get_current_user(
    request: Request,
    db: Database = Depends(get_database),
) -> dict:
    """Get current user's info.

    Returns the user's email and service account email.
    Requires authentication - returns 403 if not logged in.
    """
    email = request.session.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="Authentication required")

    user_creds = await db.get_user_credentials(email)
    if not user_creds:
        raise HTTPException(status_code=403, detail="Authentication required")

    return {
        "email": email,
        "service_account_email": user_creds.service_account_email,
    }


@router.get("/users")
async def list_users(
    request: Request,
    db: Database = Depends(get_database),
) -> dict:
    """List all users and their service account emails.

    Requires authentication - returns 403 if not logged in.
    This endpoint enables transparency - users can see which
    service account belongs to which employee.
    """
    email = request.session.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="Authentication required")

    user_creds = await db.get_user_credentials(email)
    if not user_creds:
        raise HTTPException(status_code=403, detail="Authentication required")

    users = await db.list_users_with_service_accounts()
    return {"users": users}


# =============================================================================
# Token Exchange Endpoints
# =============================================================================


@router.get("/token/auth")
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

    If the user has a valid session with stored credentials and service account,
    a new token will be generated without requiring re-authentication.

    Otherwise, this endpoint creates a state token and redirects to Google OAuth.
    The callback is handled by /api/auth/callback.
    """
    # Build the redirect URL - always localhost with fixed path
    cli_redirect = _build_cli_redirect_url(port)

    # Check if user has a valid session with stored SA
    email = request.session.get("email")
    if email:
        user_creds = await db.get_user_credentials(email)
        if user_creds and user_creds.service_account_email:
            logger.info("Session found, generating token", extra={"email": email, "cli_port": port})
            redirect_response = await _try_generate_token(db, email, cli_redirect, settings)
            if redirect_response:
                return redirect_response
            # Token generation failed, fall through to OAuth flow
            logger.info("Token generation failed, starting OAuth flow", extra={"email": email})

    # No valid session or token generation failed, start OAuth flow
    logger.info("Starting OAuth flow", extra={"cli_port": port})

    # Create state token with CLI redirect info (stored in Firestore)
    state = secrets.token_urlsafe(32)
    await db.save_state(state, cli_redirect)

    # Create OAuth flow with minimal scopes
    flow = _create_oauth_flow(settings)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


@router.get("/auth/callback", response_model=None)
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
) -> RedirectResponse | HTMLResponse:
    """Handle Google OAuth callback for CLI flow."""
    # Retrieve and consume state token from Firestore (one-time use)
    cli_redirect = await db.retrieve_state(state)
    if not cli_redirect:
        logger.warning(
            "Invalid OAuth state",
            extra={"state_prefix": state[:8], "reason": "not_found_or_expired"},
        )
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    # Create OAuth flow with minimal scopes
    flow = _create_oauth_flow(settings)

    # Exchange code for tokens
    try:
        flow.fetch_token(code=code)
    except OAuth2Error as e:
        logger.warning("OAuth token exchange failed", extra={"error": str(e)})
        return _cli_error_response(cli_redirect)

    # Get credentials and verify ID token
    credentials = flow.credentials
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,  # type: ignore[union-attr]
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as e:
        logger.warning("ID token verification failed", extra={"error": str(e)})
        return _cli_error_response(cli_redirect)

    user_email = id_info.get("email", "")
    user_name = id_info.get("name", "")

    # Validate email domain against allowlist
    if not settings.is_email_domain_allowed(user_email):
        logger.warning(
            "Email domain not allowed",
            extra={"email": user_email, "allowed_domains": settings.get_allowed_domains()},
        )
        return _cli_error_response(cli_redirect)

    logger.info("OAuth callback successful", extra={"email": user_email})

    # Generate token using TokenGenerator (uses server ADC for impersonation)
    token_generator = TokenGenerator(
        database=db,
        settings=settings,
    )

    try:
        result = await token_generator.generate_token(user_email, user_name)
    except ServiceAccountCreationError as e:
        logger.error(
            "Service account creation failed",
            extra={"email": e.user_email, "error": str(e.cause) if e.cause else str(e)},
        )
        return _cli_error_response(cli_redirect)
    except ImpersonationError as e:
        logger.error(
            "Token generation failed",
            extra={"sa_email": e.sa_email, "error": str(e.cause) if e.cause else str(e)},
        )
        return _cli_error_response(cli_redirect)

    # Calculate expires_in from expires_at for the CLI
    expires_in = int((result.expires_at - datetime.now(UTC)).total_seconds())
    if expires_in < 0:
        expires_in = 3600  # Fallback to 1 hour

    # Create redirect response with token
    params = {
        "token": result.token,
        "expires_in": str(expires_in),
        "service_account": result.service_account_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    response = RedirectResponse(url=redirect_url)

    # Set session cookie so user doesn't need to re-authenticate
    request.session["email"] = user_email

    logger.info(
        "Auth successful",
        extra={"email": user_email, "service_account": result.service_account_email},
    )
    return response


# =============================================================================
# Private Helpers
# =============================================================================


def _build_cli_redirect_url(port: int) -> str:
    """Build CLI redirect URL from port - always localhost."""
    return f"http://localhost:{port}/on-authentication"


def _create_oauth_flow(settings: Settings) -> Flow:
    """Create Google OAuth flow with CLI scopes."""
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
        scopes=CLI_SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


async def _try_generate_token(
    db: Database, email: str, cli_redirect: str, settings: Settings
) -> RedirectResponse | None:
    """Try to generate a token for an existing session.

    Returns a RedirectResponse with the new token if successful, None otherwise.
    """
    token_generator = TokenGenerator(
        database=db,
        settings=settings,
    )

    try:
        result = await token_generator.generate_token(email)
    except (ServiceAccountCreationError, ImpersonationError) as e:
        logger.warning(
            "Token generation failed for session", extra={"email": email, "error": str(e)}
        )
        return None

    # Calculate expires_in from expires_at for the CLI
    expires_in = int((result.expires_at - datetime.now(UTC)).total_seconds())
    if expires_in < 0:
        expires_in = 3600

    # Redirect to CLI with token
    params = {
        "token": result.token,
        "expires_in": str(expires_in),
        "service_account": result.service_account_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"

    logger.info(
        "Token generated from session",
        extra={"email": email, "service_account": result.service_account_email},
    )
    return RedirectResponse(url=redirect_url)


def _cli_error_response(redirect: str) -> RedirectResponse | HTMLResponse:
    """Create error response for CLI flow.

    Security: Does not include internal error details in the response.
    Errors are logged server-side for debugging.
    """
    if redirect:
        # Redirect to CLI with generic error
        params = {"error": "authentication_failed"}
        return RedirectResponse(url=f"{redirect}?{urlencode(params)}")
    else:
        return HTMLResponse(
            content="""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: sans-serif; padding: 40px;">
                <h1>Authentication Error</h1>
                <p>Authentication failed. Please close this window and try again.</p>
                <p>If the problem persists, contact support.</p>
            </body>
            </html>
            """,
            status_code=400,
        )
