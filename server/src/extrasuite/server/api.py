"""REST API endpoints for ExtraSuite.

This module contains all HTTP endpoints. Business logic is delegated to:
- TokenGenerator: Service account token generation and domain-wide delegation
- Database: Credential storage and OAuth state management

Endpoints:
- GET  /api/token/auth             - Phase 1 browser entry point (port= for callback; omit for headless)
- GET  /api/auth/callback          - OAuth callback
- POST /api/auth/session/exchange  - Exchange auth code for 30-day session token
- POST /api/auth/token             - Exchange session token for credential(s) via typed Command
- GET  /api/admin/sessions         - List sessions for email (self-service or admin)
- DELETE /api/admin/sessions/{hash} - Revoke a session
- POST /api/admin/sessions/revoke-all - Revoke all sessions for email
- GET  /api/health                 - Health check
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from loguru import logger
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from extrasuite.server.command_registry import Credential
from extrasuite.server.commands import Command
from extrasuite.server.config import Settings, get_settings
from extrasuite.server.credential_router import CommandCredentialRouter
from extrasuite.server.database import Database, get_database

# Base scopes always requested: identify the user via ID token
_IDENTITY_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Rate limiter instance - will be configured by main.py
limiter = Limiter(key_func=get_remote_address)

# Valid port range for CLI callback
MIN_PORT = 1024
MAX_PORT = 65535


def _auth_rate_limit() -> str:
    return get_settings().rate_limit_auth


def _token_rate_limit() -> str:
    return get_settings().rate_limit_token


def _admin_rate_limit() -> str:
    return get_settings().rate_limit_admin

router = APIRouter()


def get_credential_router(request: Request) -> CommandCredentialRouter:
    """FastAPI dependency to get the credential router from app.state."""
    return request.app.state.credential_router

# =============================================================================
# Health Endpoints
# =============================================================================


@router.get("/health")
async def health_check(_request: Request, db: Database = Depends(get_database)) -> JSONResponse:
    """Health check endpoint. Returns 503 if Firestore is unreachable."""
    db_ok = await db.ping()
    if not db_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "service": "extrasuite-server", "firestore": "unreachable"},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "service": "extrasuite-server", "firestore": "ok"},
    )


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


@router.post("/users/logout")
async def logout(request: Request) -> dict:
    """Log out the current user by clearing the session.

    Clears the session cookie. Returns success even if not logged in.
    """
    request.session.clear()
    return {"status": "logged_out"}


# =============================================================================
# Token Exchange Endpoints
# =============================================================================


@router.get("/token/auth", response_model=None)
@limiter.limit(_auth_rate_limit)
async def start_token_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
    port: int | None = Query(None, description="CLI localhost callback port", ge=MIN_PORT, le=MAX_PORT),
) -> RedirectResponse | HTMLResponse:
    """Start the Phase 1 browser flow for CLI session establishment.

    With ?port=N (interactive): after OAuth, redirects to localhost:{port} where
    the CLI's local callback server picks up the auth code.

    Without port (headless): after OAuth, displays the auth code on an HTML page
    so the user can copy-paste it into the CLI.

    Flow:
    1. If user has valid browser session → generate auth code and redirect/show immediately
    2. Otherwise → redirect to Google OAuth (callback handles token generation)
    """
    headless = port is None
    cli_redirect = "headless" if headless else _build_cli_redirect_url(port)  # type: ignore[arg-type]

    email = request.session.get("email")
    if email:
        if headless:
            logger.info("Headless: session found, generating code", extra={"email": email})
            return await _generate_auth_code_and_show_html(db, email)
        logger.info("Session found, generating token", extra={"email": email, "cli_port": port})
        return await _generate_auth_code_and_redirect(db, email, cli_redirect)

    logger.info("No session, starting OAuth flow", extra={"headless": headless, "cli_port": port})
    state = secrets.token_urlsafe(32)
    await db.save_state(state, cli_redirect)

    flow = _create_oauth_flow(settings)
    auth_kwargs: dict = {"state": state}
    if settings.uses_oauth:
        # OAuth mode: request offline access and workspace scopes at consent time
        auth_kwargs["access_type"] = "offline"
        auth_kwargs["prompt"] = "consent"
    authorization_url, _ = flow.authorization_url(**auth_kwargs)

    return RedirectResponse(url=authorization_url)


@router.get("/auth/login", response_model=None)
@limiter.limit(_auth_rate_limit)
async def start_ui_login(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
) -> RedirectResponse:
    """Start OAuth flow for UI login.

    Unlike /token/auth, this endpoint is for browser-based login from the UI.
    On success, redirects back to the home page instead of a CLI callback.
    """
    # If user already has a valid session, redirect to home
    email = request.session.get("email")
    if email:
        logger.info("Session found, redirecting to home", extra={"email": email})
        return RedirectResponse(url="/")

    # No session - start OAuth flow with "/" as redirect target
    logger.info("No session, starting OAuth flow for UI login")
    state = secrets.token_urlsafe(32)
    await db.save_state(state, "/")  # Use "/" to indicate UI flow

    flow = _create_oauth_flow(settings)
    auth_kwargs: dict = {"state": state}
    if settings.uses_oauth:
        auth_kwargs["access_type"] = "offline"
        auth_kwargs["prompt"] = "consent"
    authorization_url, _ = flow.authorization_url(**auth_kwargs)

    return RedirectResponse(url=authorization_url)


@router.get("/auth/callback", response_model=None)
@limiter.limit(_auth_rate_limit)
async def google_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
    credential_router: CommandCredentialRouter = Depends(get_credential_router),
) -> RedirectResponse | HTMLResponse:
    """Handle Google OAuth callback for CLI flow.

    Verifies OAuth, sets session, then generates token and redirects to CLI.
    """
    # Retrieve and consume state token from Firestore (one-time use)
    state_data = await db.retrieve_state(state)
    if not state_data:
        logger.warning(
            "Invalid OAuth state",
            extra={"state_prefix": state[:8], "reason": "not_found_or_expired"},
        )
        return _cli_error_response("", "invalid_state")

    cli_redirect = str(state_data["redirect_url"])

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

    # Notify all providers of the callback (OAuth mode: store refresh token; others: no-op)
    try:
        await credential_router.on_google_auth_callback(user_email, credentials)
    except Exception as e:
        logger.exception(
            "Credential provider callback failed",
            extra={"email": user_email, "error": str(e)},
        )
        return _cli_error_response(cli_redirect)

    # Dispatch based on redirect target
    if cli_redirect == "/":
        # UI login: redirect home (SA provisioning happens at session establishment)
        logger.info("UI login complete", extra={"email": user_email})
        return RedirectResponse(url="/")

    if cli_redirect == "headless":
        # Headless CLI login: show auth code on page instead of redirecting
        return await _generate_auth_code_and_show_html(db, user_email)

    return await _generate_auth_code_and_redirect(db, user_email, cli_redirect)


# =============================================================================
# New Auth Endpoints (v2 Session Token Protocol)
# =============================================================================


class SessionExchangeRequest(BaseModel):
    """Request body for session token exchange (Phase 1)."""

    code: str = Field(..., min_length=1, description="Auth code received from redirect")
    device_mac: str = Field("", max_length=64, description="Device MAC address")
    device_hostname: str = Field("", max_length=253, description="Device hostname")
    device_os: str = Field("", max_length=64, description="Device OS (e.g., Darwin, Linux, Windows)")
    device_platform: str = Field("", max_length=256, description="Device platform string")


class SessionExchangeResponse(BaseModel):
    """Response body for session token exchange."""

    session_token: str
    expires_at: str  # ISO 8601
    email: str


class TokenRequest(BaseModel):
    """Request body for access token exchange (Phase 2).

    The session token is passed in the Authorization: Bearer header, not in the body,
    to avoid it appearing in server access logs.

    ``command`` is a typed discriminated union — the ``type`` field identifies the
    operation and carries exactly the context fields relevant for that operation.
    ``reason`` is agent-supplied user intent (not a hardcoded code description).
    """

    command: Command = Field(..., description="Typed command describing the operation")
    reason: str = Field(..., min_length=1, description="Agent-supplied user intent")


class TokenResponse(BaseModel):
    """Response body for access token exchange.

    ``credentials`` is a list so that future multi-provider operations can return
    tokens for several services in a single round-trip.  Today it always contains
    exactly one Google credential.
    """

    credentials: list[Credential]
    command_type: str  # echo of command.type — useful as a client-side cache key


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers or connection.

    Uses the rightmost (last) IP in X-Forwarded-For because Cloud Run
    appends the real client IP at the end of the chain, and earlier entries
    can be spoofed by the caller. Falls back to the direct connection IP.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.client.host if request.client else ""


async def _validate_bearer_session(request: Request, db: Database) -> dict:
    """Extract and validate Bearer session token from Authorization header.

    Returns {"email": str, "token_hash": str} dict or raises HTTPException(401).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    raw_token = auth_header[len("Bearer ") :]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    session_data = await db.validate_session_token(token_hash)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Session expired or revoked. Run: extrasuite auth login",
        )
    return {"email": session_data["email"], "token_hash": token_hash}


@router.post("/auth/session/exchange", response_model=SessionExchangeResponse)
@limiter.limit(_auth_rate_limit)
async def exchange_auth_code_for_session(
    request: Request,
    body: SessionExchangeRequest,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
    credential_router: CommandCredentialRouter = Depends(get_credential_router),
) -> SessionExchangeResponse:
    """Exchange a short-lived auth code for a 30-day session token (Phase 1).

    The auth code must have been obtained via GET /api/token/auth (existing flow).
    On success, returns a session token that can be used with POST /api/auth/token
    to obtain short-lived access tokens without browser interaction.
    """
    # Auth codes are single-use and represent successful Phase 1 login.
    auth_code_data = await db.retrieve_auth_code(body.code)
    if not auth_code_data:
        raise HTTPException(status_code=400, detail="Invalid or expired auth code")

    email = auth_code_data["user_email"]
    if not email:
        raise HTTPException(status_code=400, detail="Invalid auth code: missing user_email")

    # Validate email domain
    if not settings.is_email_domain_allowed(email):
        raise HTTPException(status_code=403, detail="Email domain not allowed")

    # Run session-establishment hooks (SA+DWD: provision service account; OAuth: no-op).
    # After this point, get_service_account_email() will always return a non-None value
    # for SA/DWD modes, so downstream delegation code never receives None.
    try:
        await credential_router.on_session_establishment(email)
    except Exception as e:
        logger.exception(
            "Session establishment hook failed",
            extra={"email": email, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to provision credentials") from e

    # Generate session token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    client_ip = _get_client_ip(request)
    expires_at = datetime.now(UTC) + timedelta(days=settings.session_token_expiry_days)

    try:
        await db.save_session_token(
            token_hash=token_hash,
            email=email,
            device_ip=client_ip,
            device_mac=body.device_mac,
            device_hostname=body.device_hostname,
            device_os=body.device_os,
            device_platform=body.device_platform,
            expiry_days=settings.session_token_expiry_days,
        )
    except Exception as e:
        logger.exception(
            "Failed to persist session token",
            extra={"email": email, "error": str(e)},
        )
        raise HTTPException(
            status_code=500, detail="Failed to provision session — please retry"
        ) from e

    logger.info(
        "Session token issued", extra={"email": email, "device_hostname": body.device_hostname}
    )

    return SessionExchangeResponse(
        session_token=raw_token,
        expires_at=expires_at.isoformat(),
        email=email,
    )


@router.post("/auth/token", response_model=TokenResponse)
@limiter.limit(_token_rate_limit)
async def exchange_session_for_access_token(
    request: Request,
    body: TokenRequest,
    db: Database = Depends(get_database),
    credential_router: CommandCredentialRouter = Depends(get_credential_router),
) -> TokenResponse:
    """Exchange a session token for a short-lived access token (Phase 2).

    This is the headless path: no browser required. The session token is passed
    in the Authorization: Bearer header (not the body) to prevent it from being
    recorded in server access logs.

    The ``command`` field is a typed discriminated union. The server resolves the
    command type to the appropriate credential(s) and performs allowlist checks.
    """
    # Validate session token from Authorization: Bearer header
    caller = await _validate_bearer_session(request, db)
    email = caller["email"]
    token_hash = caller["token_hash"]

    cmd_type = body.command.type
    client_ip = _get_client_ip(request)

    # Resolve credentials — routing, allowlist checks, and token generation
    credentials = await credential_router.resolve(body.command, email)

    # Log access after credential resolution so credential_kind is known
    credential_kind = credentials[0].kind if credentials else ""
    try:
        await db.log_access_token_request(
            email=email,
            session_hash_prefix=token_hash[:16],
            command_type=cmd_type,
            command_context=body.command.model_dump(exclude={"type"}),
            reason=body.reason,
            ip=client_ip,
            credential_kind=credential_kind,
        )
    except Exception as e:
        logger.warning("Failed to log access token request", extra={"error": str(e)})

    logger.info(
        "Access token issued",
        extra={"email": email, "command_type": cmd_type, "credential_kind": credential_kind},
    )

    return TokenResponse(credentials=credentials, command_type=cmd_type)


# =============================================================================
# Admin Session Management Endpoints
# =============================================================================


def _assert_session_authorized(
    caller_email: str, target_email: str, settings: Settings, action: str
) -> None:
    """Raise 403 if caller is neither the owner nor an admin.

    All email comparisons are case-insensitive. Settings.get_admin_emails()
    must return lowercase-normalised addresses to make this work correctly.
    """
    if (
        caller_email.lower() != target_email.lower()
        and caller_email.lower() not in settings.get_admin_emails()
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to {action}",
        )


@router.post("/auth/oauth/revoke")
@limiter.limit(_auth_rate_limit)
async def revoke_oauth_token(
    request: Request,
    db: Database = Depends(get_database),
    credential_router: CommandCredentialRouter = Depends(get_credential_router),
) -> dict:
    """Revoke the stored OAuth refresh token and delete it from Firestore.

    Called by ``extrasuite auth logout`` in OAuth credential modes.
    Google revocation invalidates all access tokens derived from this refresh token.
    Network failure on revocation is logged but does NOT block the response —
    the Firestore deletion still prevents future use from ExtraSuite's server.

    Requires a valid session token in Authorization: Bearer header.
    """
    caller = await _validate_bearer_session(request, db)
    email = caller["email"]

    await credential_router.on_logout(email)
    logger.info("OAuth token revoked on logout", extra={"email": email})
    return {"status": "revoked"}


@router.get("/admin/sessions")
@limiter.limit(_admin_rate_limit)
async def list_sessions(
    request: Request,
    email: str = Query(..., description="Email address to list sessions for"),
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """List active sessions for an email address.

    Self-service: any authenticated user can list their own sessions.
    Admin: users in ADMIN_EMAILS can list sessions for any email.
    """
    caller = await _validate_bearer_session(request, db)
    caller_email = caller["email"]
    _assert_session_authorized(caller_email, email, settings, "view sessions for this email")

    sessions = await db.list_session_tokens(email)

    # Redact full session_hash when an admin is listing another user's sessions.
    # The full hash is the revocation key; self-service callers need it to build
    # DELETE URLs for their own sessions. Admins listing other users get only the
    # prefix (sufficient for audit display) and should use revoke-all if needed.
    if caller_email.lower() != email.lower():
        for s in sessions:
            s.pop("session_hash", None)

    return sessions


@router.delete("/admin/sessions/{session_hash}", status_code=204)
@limiter.limit(_admin_rate_limit)
async def revoke_session(
    request: Request,
    session_hash: str,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Revoke a session by its hash.

    Self-service: users can revoke their own sessions.
    Admin: users in ADMIN_EMAILS can revoke any session.
    """
    caller = await _validate_bearer_session(request, db)
    caller_email = caller["email"]
    is_admin = caller_email.lower() in settings.get_admin_emails()

    # Pass expected_email to make ownership validation atomic in the DB layer.
    # Admins pass "" to skip the email check (they can revoke any session).
    # Non-admins pass their own email; the DB will reject a hash that belongs to
    # a different user, eliminating the TOCTOU window of the list+check approach.
    expected_email = "" if is_admin else caller_email
    found = await db.revoke_session_token(session_hash, expected_email=expected_email)
    if not found:
        status = 404 if is_admin else 403
        detail = "Session not found" if is_admin else "Not authorized to revoke this session"
        raise HTTPException(status_code=status, detail=detail)

    logger.info(
        "Session revoked", extra={"session_hash_prefix": session_hash[:16], "by": caller_email}
    )
    return Response(status_code=204)


@router.post("/admin/sessions/revoke-all")
@limiter.limit(_admin_rate_limit)
async def revoke_all_sessions(
    request: Request,
    email: str = Query(..., description="Email address to revoke all sessions for"),
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Revoke all active sessions for an email address.

    Self-service: users can revoke all their own sessions.
    Admin: users in ADMIN_EMAILS can revoke sessions for any email.
    """
    caller = await _validate_bearer_session(request, db)
    caller_email = caller["email"]
    _assert_session_authorized(caller_email, email, settings, "revoke sessions for this email")

    count = await db.revoke_all_session_tokens(email)
    logger.info("All sessions revoked", extra={"email": email, "count": count, "by": caller_email})
    return {"revoked_count": count}


# =============================================================================
# Private Helpers
# =============================================================================


async def _generate_auth_code_and_show_html(
    db: Database, email: str
) -> HTMLResponse:
    """Generate an auth code and display it on an HTML page (headless flow).

    Service account provisioning is deferred to exchange_auth_code_for_session
    via the credential router's on_session_establishment hook.
    """
    logger.info("Headless: generating auth code", extra={"email": email})

    auth_code = secrets.token_urlsafe(32)
    await db.save_auth_code(auth_code, "", email)

    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body {{ font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }}
                h1 {{ color: #1a73e8; }}
                .code-box {{
                    background: #f1f3f4; border-radius: 8px; padding: 16px 20px;
                    font-family: monospace; font-size: 1.1em; letter-spacing: 0.5px;
                    word-break: break-all; margin: 20px 0;
                }}
                .instructions {{ color: #555; }}
            </style>
        </head>
        <body>
            <h1>Authentication Successful</h1>
            <p class="instructions">Copy the code below and paste it into your terminal:</p>
            <div class="code-box" id="auth-code">{auth_code}</div>
            <p class="instructions">You can close this window after copying the code.</p>
            <script>
                // Auto-select the code for easy copying
                var el = document.getElementById('auth-code');
                var range = document.createRange();
                range.selectNodeContents(el);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);
            </script>
        </body>
        </html>
        """
    )


def _cli_headless_error_response() -> HTMLResponse:
    """Return an HTML error page for the headless flow."""
    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html>
        <head><title>Authentication Error</title></head>
        <body style="font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px;">
            <h1 style="color: #d93025;">Authentication Error</h1>
            <p>Authentication failed. Please close this window and try again.</p>
            <p>If the problem persists, contact support.</p>
        </body>
        </html>
        """,
        status_code=400,
    )


def _build_cli_redirect_url(port: int) -> str:
    """Build CLI redirect URL from port - always localhost."""
    return f"http://localhost:{port}/on-authentication"


def _create_oauth_flow(settings: Settings) -> Flow:
    """Create Google OAuth flow.

    In sa+dwd mode: only identity scopes (openid + email) are requested.
    In sa+oauth or oauth mode: identity scopes + all configured workspace scopes.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    scopes = list(_IDENTITY_SCOPES)
    if settings.uses_oauth:
        scopes.extend(settings.get_oauth_scope_urls())

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


async def _generate_auth_code_and_redirect(
    db: Database, email: str, cli_redirect: str
) -> RedirectResponse | HTMLResponse:
    """Generate an auth code and redirect to the CLI callback URL.

    Service account provisioning is deferred to exchange_auth_code_for_session
    via the credential router's on_session_establishment hook.
    """
    logger.info("Generating auth code for CLI redirect", extra={"email": email})

    # Generate auth code; SA provisioning happens later in on_session_establishment
    auth_code = secrets.token_urlsafe(32)
    await db.save_auth_code(auth_code, "", email)

    # Redirect with auth code only
    params = {"code": auth_code}
    redirect_url = f"{cli_redirect}?{urlencode(params)}"
    return RedirectResponse(url=redirect_url)


def _cli_error_response(
    redirect: str, error: str = "authentication_failed"
) -> RedirectResponse | HTMLResponse:
    """Create error response for CLI flow.

    Security: Only uses predefined error codes, no internal details.
    Errors are logged server-side for debugging.
    """
    if redirect:
        # Redirect to CLI with error code
        params = {"error": error}
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
