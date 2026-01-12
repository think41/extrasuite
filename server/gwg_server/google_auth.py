"""Google OAuth authentication API endpoints.

Handles CLI authentication flow via token exchange.
Entry point: /api/token/auth redirects here after Google OAuth.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.auth.exceptions import RefreshError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from gwg_server.config import Settings, get_settings
from gwg_server.database import Database, get_database
from gwg_server.logging import (
    audit_auth_failed,
    audit_auth_success,
    audit_oauth_state_invalid,
    audit_service_account_created,
    logger,
)
from gwg_server.oauth import CLI_SCOPES, create_oauth_flow
from gwg_server.rate_limit import limiter
from gwg_server.service_account import get_or_create_service_account, impersonate_service_account

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_email_domain_allowed(email: str, settings: Settings) -> bool:
    """Check if email domain is allowed."""
    return settings.is_email_domain_allowed(email)


@router.get("/callback", response_model=None)
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
):
    """Handle Google OAuth callback for CLI flow."""
    # Verify state token from Firestore
    oauth_state = await db.get_oauth_state(state)
    if not oauth_state:
        audit_oauth_state_invalid(state, "not_found_or_expired")
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    # Consume the state token (one-time use)
    await db.delete_oauth_state(state)

    cli_redirect = oauth_state.cli_redirect
    if not cli_redirect:
        audit_oauth_state_invalid(state, "missing_redirect")
        raise HTTPException(status_code=400, detail="Invalid state: missing redirect")

    # Create OAuth flow with CLI scopes
    flow = create_oauth_flow(settings, CLI_SCOPES)

    # Exchange code for tokens
    try:
        flow.fetch_token(code=code)
    except Exception:
        logger.exception("Failed to exchange OAuth code for token")
        audit_auth_failed(None, "token_exchange_failed")
        return _cli_error_response(cli_redirect)

    # Get credentials and verify ID token
    credentials = flow.credentials
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception:
        logger.exception("Failed to verify OAuth ID token")
        audit_auth_failed(None, "token_verification_failed")
        return _cli_error_response(cli_redirect)

    user_email = id_info.get("email", "")
    user_name = id_info.get("name", "")

    # Validate email domain against allowlist
    if not _is_email_domain_allowed(user_email, settings):
        logger.warning(
            "Email domain not allowed",
            extra={"email": user_email, "allowed_domains": settings.get_allowed_domains()},
        )
        audit_auth_failed(user_email, "domain_not_allowed")
        return _cli_error_response(cli_redirect)

    logger.info("OAuth callback successful", extra={"email": user_email})

    # Handle CLI flow - token exchange
    return await _handle_cli_callback(
        request, credentials, user_email, user_name, cli_redirect, settings, db
    )


async def _handle_cli_callback(
    request: Request,
    credentials,
    user_email: str,
    user_name: str,
    cli_redirect: str,
    settings: Settings,
    db: Database,
) -> RedirectResponse | HTMLResponse:
    """Handle CLI OAuth callback - exchange for SA token and redirect to localhost."""
    # Store OAuth credentials in Firestore
    try:
        scopes = list(credentials.scopes) if credentials.scopes else CLI_SCOPES
        await db.store_user_credentials(
            email=user_email,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            scopes=scopes,
        )
    except Exception:
        logger.exception("Failed to store OAuth credentials")
        audit_auth_failed(user_email, "credential_storage_failed")
        return _cli_error_response(cli_redirect)

    # Look up or create service account
    try:
        sa_email, created = get_or_create_service_account(settings, user_email, user_name)
        if created:
            audit_service_account_created(user_email, sa_email)
        logger.info("Service account ready", extra={"email": user_email, "sa": sa_email})
    except Exception:
        logger.exception("Failed to setup service account")
        audit_auth_failed(user_email, "service_account_setup_failed")
        return _cli_error_response(cli_redirect)

    # Update SA email in Firestore
    try:
        await db.update_service_account_email(user_email, sa_email)
    except Exception:
        # Log but continue - non-critical, we can update next time
        logger.warning(
            "Failed to update service account email in database",
            extra={"email": user_email, "sa": sa_email},
        )

    # Impersonate SA to get short-lived token
    try:
        sa_token, expires_in = impersonate_service_account(credentials, sa_email)
    except RefreshError:
        logger.exception("OAuth credentials expired or revoked during impersonation")
        audit_auth_failed(user_email, "credentials_revoked")
        return _cli_error_response(cli_redirect)
    except Exception:
        logger.exception("Failed to impersonate service account")
        audit_auth_failed(user_email, "impersonation_failed")
        return _cli_error_response(cli_redirect)

    # Create redirect response with token
    params = {
        "token": sa_token,
        "expires_in": str(expires_in),
        "service_account": sa_email,
    }
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    response = RedirectResponse(url=redirect_url)

    # Set session cookie so user doesn't need to re-authenticate
    request.session["email"] = user_email

    audit_auth_success(user_email, sa_email)
    return response


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
