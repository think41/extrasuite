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
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from loguru import logger
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from extrasuite_server.config import Settings, get_settings
from extrasuite_server.database import Database, get_database
from extrasuite_server.token_generator import TokenGenerator

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

    sa_email = await db.get_service_account_email(email)
    return {
        "email": email,
        "service_account_email": sa_email,
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

    users = await db.list_users_with_service_accounts()
    return {"users": users}


# =============================================================================
# Token Exchange Endpoints
# =============================================================================


class TokenExchangeRequest(BaseModel):
    """Request body for auth code exchange."""

    code: str = Field(..., min_length=1, description="Auth code received from redirect")


class TokenExchangeResponse(BaseModel):
    """Response body for auth code exchange."""

    token: str
    expires_at: str
    service_account: str


@router.post("/token/exchange", response_model=TokenExchangeResponse)
@limiter.limit("20/minute")
async def exchange_auth_code(
    request: Request,  # noqa: ARG001 - Required for rate limiter
    body: TokenExchangeRequest,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> TokenExchangeResponse:
    """Exchange auth code for token.

    No authentication required - the auth code is the proof of authentication.
    Auth codes are single-use and expire after AUTH_CODE_TTL.

    The token is generated on-demand via SA impersonation.
    The service account MUST already exist - this endpoint does not create SAs.
    """
    service_account_email = await db.retrieve_auth_code(body.code)

    if not service_account_email:
        logger.warning("Invalid or expired auth code", extra={"code_prefix": body.code[:8]})
        raise HTTPException(status_code=400, detail="Invalid or expired auth code")

    # Generate token via impersonation - SA must exist, errors propagate to global handler
    token_generator = TokenGenerator(database=db, settings=settings)
    result = await token_generator.generate_token_for_service_account(service_account_email)

    logger.info(
        "Auth code exchanged for token",
        extra={"service_account": service_account_email},
    )

    return TokenExchangeResponse(
        token=result.token,
        expires_at=result.expires_at.isoformat(),
        service_account=result.service_account_email,
    )


@router.get("/token/auth", response_model=None)
@limiter.limit("10/minute")
async def start_token_auth(
    request: Request,
    port: int = Query(..., description="CLI localhost callback port", ge=MIN_PORT, le=MAX_PORT),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
) -> RedirectResponse | HTMLResponse:
    """Start OAuth flow for CLI token exchange.

    The CLI should call this with a port parameter for its localhost server.
    Example: /api/token/auth?port=8085

    Flow:
    1. If user has valid session → generate token and redirect to CLI
    2. Otherwise → redirect to Google OAuth (callback handles token generation)
    """
    cli_redirect = _build_cli_redirect_url(port)

    # If user has a valid session, generate token directly
    email = request.session.get("email")
    if email:
        logger.info("Session found, generating token", extra={"email": email, "cli_port": port})
        return await _generate_token_and_redirect(db, settings, email, cli_redirect)

    # No session - start OAuth flow
    logger.info("No session, starting OAuth flow", extra={"cli_port": port})
    state = secrets.token_urlsafe(32)
    await db.save_state(state, cli_redirect)

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
    """Handle Google OAuth callback for CLI flow.

    Verifies OAuth, sets session, then generates token and redirects to CLI.
    """
    # Retrieve and consume state token from Firestore (one-time use)
    cli_redirect = await db.retrieve_state(state)
    if not cli_redirect:
        logger.warning(
            "Invalid OAuth state",
            extra={"state_prefix": state[:8], "reason": "not_found_or_expired"},
        )
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    # Exchange code for tokens
    flow = _create_oauth_flow(settings)
    try:
        flow.fetch_token(code=code)
    except OAuth2Error as e:
        logger.warning("OAuth token exchange failed", extra={"error": str(e)})
        return _cli_error_response(cli_redirect)

    # Verify ID token
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

    # Validate email domain against allowlist
    if not settings.is_email_domain_allowed(user_email):
        logger.warning(
            "Email domain not allowed",
            extra={"email": user_email, "allowed_domains": settings.get_allowed_domains()},
        )
        return _cli_error_response(cli_redirect)

    logger.info("OAuth successful", extra={"email": user_email})

    # Set session cookie so user doesn't need to re-authenticate
    request.session["email"] = user_email

    # Generate token and redirect to CLI
    return await _generate_token_and_redirect(db, settings, user_email, cli_redirect)


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


async def _generate_token_and_redirect(
    db: Database, settings: Settings, email: str, cli_redirect: str
) -> RedirectResponse | HTMLResponse:
    """Ensure service account exists and redirect to CLI with auth code.

    Creates service account if needed. Does NOT generate token here.
    Stores auth code with service account email in Firestore.
    CLI then exchanges auth code for token via POST to /api/token/exchange.
    Token is generated on-demand during exchange for security.
    """
    token_generator = TokenGenerator(database=db, settings=settings)

    try:
        service_account_email = await token_generator.ensure_service_account(email)
    except Exception as e:
        logger.exception("Service account setup failed", extra={"email": email, "error": str(e)})
        return _cli_error_response(cli_redirect)

    logger.info(
        "Service account ready",
        extra={"email": email, "service_account": service_account_email},
    )

    # Generate auth code and store SA email for later token generation
    auth_code = secrets.token_urlsafe(32)
    await db.save_auth_code(auth_code, service_account_email)

    # Redirect with auth code only
    params = {"code": auth_code}
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
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
