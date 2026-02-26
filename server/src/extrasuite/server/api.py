"""REST API endpoints for ExtraSuite.

This module contains all HTTP endpoints. Business logic is delegated to:
- TokenGenerator: Service account token generation and domain-wide delegation
- Database: Credential storage and OAuth state management

Endpoints:
- GET  /api/token/auth          - [Deprecated] CLI entry point, starts OAuth or refreshes token
- POST /api/token/exchange      - [Deprecated] Exchange auth code for service account token
- GET  /api/delegation/auth     - [Deprecated] Start delegation flow for user-level API access
- POST /api/delegation/exchange - [Deprecated] Exchange auth code for delegated token
- GET  /api/auth/callback       - OAuth callback (shared by all flows)
- POST /api/auth/session/exchange - Phase 1: Exchange auth code for 30-day session token
- POST /api/auth/token          - Phase 2: Exchange session token for short-lived access token
- GET  /api/admin/sessions      - List sessions for email (self-service or admin)
- DELETE /api/admin/sessions/{hash} - Revoke a session
- POST /api/admin/sessions/revoke-all - Revoke all sessions for email
- GET  /api/health              - Health check
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

from extrasuite.server.config import Settings, get_settings
from extrasuite.server.database import Database, get_database
from extrasuite.server.token_generator import DelegationError, TokenGenerator

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

# Pseudo-scope → credential type mapping (server-authoritative)
_SA_SCOPES: frozenset[str] = frozenset(
    {
        "sheet.pull",
        "sheet.push",
        "doc.pull",
        "doc.push",
        "slide.pull",
        "slide.push",
        "form.pull",
        "form.push",
        "drive.file",
    }
)
_DWD_SCOPES: frozenset[str] = frozenset(
    {"calendar", "gmail.compose", "gmail.send", "gmail.readonly", "script.projects", "drive"}
)
_ALL_SCOPES = _SA_SCOPES | _DWD_SCOPES

# Deprecation sunset date (one year from design)
_DEPRECATION_SUNSET = "2026-12-31"


# =============================================================================
# Health Endpoints
# =============================================================================


@router.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "extrasuite-server"}


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

    **Deprecated**: Use POST /api/auth/session/exchange + POST /api/auth/token instead.

    No authentication required - the auth code is the proof of authentication.
    Auth codes are single-use and expire after AUTH_CODE_TTL.

    The token is generated on-demand via SA impersonation.
    The service account MUST already exist - this endpoint does not create SAs.
    """
    logger.warning("Deprecated endpoint called: POST /api/token/exchange")
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

    response = TokenExchangeResponse(
        token=result.token,
        expires_at=result.expires_at.isoformat(),
        service_account=result.service_account_email,
    )
    # Return as JSONResponse so we can add deprecation headers
    resp = JSONResponse(content=response.model_dump())
    resp.headers["Deprecation"] = "true"
    resp.headers["Sunset"] = _DEPRECATION_SUNSET
    return resp  # type: ignore[return-value]


@router.get("/token/auth", response_model=None)
@limiter.limit("10/minute")
async def start_token_auth(
    request: Request,
    port: int = Query(..., description="CLI localhost callback port", ge=MIN_PORT, le=MAX_PORT),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
) -> RedirectResponse | HTMLResponse:
    """Start OAuth flow for CLI token exchange.

    **Deprecated**: Use GET /api/token/auth for Phase 1 session establishment only.
    After obtaining a session token via POST /api/auth/session/exchange,
    use POST /api/auth/token for all subsequent token requests.

    The CLI should call this with a port parameter for its localhost server.
    Example: /api/token/auth?port=8085

    Flow:
    1. If user has valid session → generate token and redirect to CLI
    2. Otherwise → redirect to Google OAuth (callback handles token generation)
    """
    logger.warning("Deprecated endpoint called: GET /api/token/auth")
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


@router.get("/auth/login", response_model=None)
@limiter.limit("10/minute")
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
    state_data = await db.retrieve_state(state)
    if not state_data:
        logger.warning(
            "Invalid OAuth state",
            extra={"state_prefix": state[:8], "reason": "not_found_or_expired"},
        )
        return _cli_error_response("", "invalid_state")

    cli_redirect = str(state_data["redirect_url"])
    flow_type = str(state_data.get("flow_type", ""))

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

    # Check if this is a UI login (redirect is "/") vs CLI login
    if cli_redirect == "/":
        # Ensure service account exists for UI login (no auth code needed)
        token_generator = TokenGenerator(database=db, settings=settings)
        try:
            sa_email = await token_generator.ensure_service_account(user_email)
            logger.info(
                "UI login complete, service account ready",
                extra={"email": user_email, "service_account": sa_email},
            )
        except Exception as e:
            logger.exception(
                "Service account setup failed during UI login",
                extra={"email": user_email, "error": str(e)},
            )
            # Continue to home page - user can retry later
        return RedirectResponse(url="/")

    # Handle delegation flow
    if flow_type == "delegation":
        delegation_scopes = list(state_data.get("scopes", []))  # type: ignore[arg-type]
        delegation_reason = str(state_data.get("reason", ""))
        return await _generate_delegation_code_and_redirect(
            db, user_email, delegation_scopes, delegation_reason, cli_redirect
        )

    # Generate token and redirect to CLI
    return await _generate_token_and_redirect(db, settings, user_email, cli_redirect)


# =============================================================================
# Delegation Endpoints (Domain-Wide Delegation)
# =============================================================================


class DelegationExchangeRequest(BaseModel):
    """Request body for delegation auth code exchange."""

    code: str = Field(..., min_length=1, description="Auth code received from redirect")


class DelegationExchangeResponse(BaseModel):
    """Response body for delegation auth code exchange."""

    access_token: str
    expires_at: str
    scopes: list[str]


@router.get("/delegation/auth", response_model=None)
@limiter.limit("10/minute")
async def start_delegation_auth(
    request: Request,
    port: int = Query(..., description="CLI localhost callback port", ge=MIN_PORT, le=MAX_PORT),
    scopes: str = Query(..., description="Comma-separated scope names (e.g., gmail.send,calendar)"),
    reason: str = Query("", description="Reason for requesting delegation"),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_database),
) -> RedirectResponse | HTMLResponse:
    """Start delegation auth flow for user-level API access.

    **Deprecated**: Use POST /api/auth/token with a session token instead.

    Resolves scope names to full URLs, validates against the optional
    DELEGATION_SCOPES allowlist, then either generates a delegation auth code
    (if session exists) or redirects to Google OAuth.
    """
    logger.warning("Deprecated endpoint called: GET /api/delegation/auth")
    cli_redirect = _build_cli_redirect_url(port)

    # Check if delegation is enabled
    if not settings.is_delegation_enabled():
        logger.warning("Delegation not enabled, redirecting error to CLI")
        return _cli_error_response(cli_redirect, "delegation_not_enabled")

    # Resolve short scope names to full URLs
    requested_scopes = [s.strip() for s in scopes.split(",") if s.strip()]
    if not requested_scopes:
        return _cli_error_response(cli_redirect, "no_scopes_requested")

    resolved_scopes = [_resolve_scope(s) for s in requested_scopes]

    # Validate against allowlist if configured
    disallowed = [s for s in resolved_scopes if not settings.is_scope_allowed(s)]
    if disallowed:
        short_names = [s.removeprefix(_GOOGLE_SCOPE_PREFIX) for s in disallowed]
        logger.warning("Disallowed scopes requested", extra={"scopes": short_names})
        return _cli_error_response(cli_redirect, "disallowed_scopes")

    # If user has a valid session, generate delegation auth code directly
    email = request.session.get("email")
    if email:
        logger.info(
            "Session found, generating delegation auth code",
            extra={"email": email, "scopes": resolved_scopes},
        )
        return await _generate_delegation_code_and_redirect(
            db, email, resolved_scopes, reason, cli_redirect
        )

    # No session - start OAuth flow with delegation context
    logger.info(
        "No session, starting OAuth flow for delegation",
        extra={"scopes": resolved_scopes},
    )
    state = secrets.token_urlsafe(32)
    await db.save_state(
        state,
        cli_redirect,
        scopes=resolved_scopes,
        reason=reason,
        flow_type="delegation",
    )

    flow = _create_oauth_flow(settings)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


@router.post("/delegation/exchange", response_model=DelegationExchangeResponse)
@limiter.limit("20/minute")
async def exchange_delegation_code(
    request: Request,  # noqa: ARG001 - Required for rate limiter
    body: DelegationExchangeRequest,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> DelegationExchangeResponse:
    """Exchange delegation auth code for a delegated access token.

    **Deprecated**: Use POST /api/auth/token with a session token instead.

    The auth code contains the user email and requested scopes.
    Generates a token via domain-wide delegation (IAM signBlob).
    """
    logger.warning("Deprecated endpoint called: POST /api/delegation/exchange")
    auth_data = await db.retrieve_delegation_auth_code(body.code)

    if not auth_data:
        logger.warning(
            "Invalid or expired delegation auth code",
            extra={"code_prefix": body.code[:8]},
        )
        raise HTTPException(status_code=400, detail="Invalid or expired auth code")

    email = str(auth_data["email"])
    scopes = list(auth_data["scopes"])  # type: ignore[arg-type]
    reason = str(auth_data.get("reason", ""))

    # Log the delegation request for audit
    await db.log_delegation_request(email, scopes, reason)

    # Generate delegated token
    token_generator = TokenGenerator(database=db, settings=settings)
    try:
        result = await token_generator.generate_delegated_token(email, scopes)
    except DelegationError as e:
        logger.warning(
            "Delegation failed",
            extra={"email": email, "scopes": scopes, "error": str(e)},
        )
        raise HTTPException(
            status_code=403,
            detail="Domain-wide delegation failed. The requested scopes may not be authorized in Google Workspace Admin Console.",
        ) from e

    logger.info(
        "Delegation auth code exchanged for token",
        extra={"email": email, "scopes": scopes},
    )

    response = DelegationExchangeResponse(
        access_token=result.token,
        expires_at=result.expires_at.isoformat(),
        scopes=scopes,
    )
    resp = JSONResponse(content=response.model_dump())
    resp.headers["Deprecation"] = "true"
    resp.headers["Sunset"] = _DEPRECATION_SUNSET
    return resp  # type: ignore[return-value]


# =============================================================================
# New Auth Endpoints (v2 Session Token Protocol)
# =============================================================================


class SessionExchangeRequest(BaseModel):
    """Request body for session token exchange (Phase 1)."""

    code: str = Field(..., min_length=1, description="Auth code received from redirect")
    device_mac: str = Field("", description="Device MAC address")
    device_hostname: str = Field("", description="Device hostname")
    device_os: str = Field("", description="Device OS (e.g., Darwin, Linux, Windows)")
    device_platform: str = Field("", description="Device platform string")


class SessionExchangeResponse(BaseModel):
    """Response body for session token exchange."""

    session_token: str
    expires_at: str  # ISO 8601
    email: str


class AccessTokenRequest(BaseModel):
    """Request body for access token exchange (Phase 2)."""

    session_token: str = Field(..., min_length=1, description="Session token from Phase 1")
    pseudo_scope: str = Field(
        ..., min_length=1, description="Pseudo-scope (e.g., sheet.pull, gmail.compose)"
    )
    reason: str = Field(..., min_length=1, description="Reason for requesting this token")
    file_hint: str = Field("", description="Optional Drive file URL or ID")


class AccessTokenResponse(BaseModel):
    """Response body for access token exchange."""

    access_token: str
    expires_at: str  # ISO 8601
    token_type: str = "Bearer"


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers or connection."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _validate_bearer_session(request: Request, db: Database) -> dict:
    """Extract and validate Bearer session token from Authorization header.

    Returns {email} dict or raises HTTPException(401).
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
@limiter.limit("10/minute")
async def exchange_auth_code_for_session(
    request: Request,
    body: SessionExchangeRequest,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> SessionExchangeResponse:
    """Exchange a short-lived auth code for a 30-day session token (Phase 1).

    The auth code must have been obtained via GET /api/token/auth (existing flow).
    On success, returns a session token that can be used with POST /api/auth/token
    to obtain short-lived access tokens without browser interaction.
    """
    # Validate auth code - try both SA and delegation code flows
    service_account_email = await db.retrieve_auth_code(body.code)
    if service_account_email:
        # SA flow: retrieve_auth_code returns SA email; look up which user owns this SA
        users = await db.list_users_with_service_accounts()
        email = next(
            (u["email"] for u in users if u["service_account_email"] == service_account_email),
            None,
        )
        if not email:
            raise HTTPException(
                status_code=400, detail="Could not resolve user email from auth code"
            )
    else:
        # Try delegation auth code
        delegation_data = await db.retrieve_delegation_auth_code(body.code)
        if not delegation_data:
            raise HTTPException(status_code=400, detail="Invalid or expired auth code")
        email = str(delegation_data["email"])

    # Validate email domain
    if not settings.is_email_domain_allowed(email):
        raise HTTPException(status_code=403, detail="Email domain not allowed")

    # Generate session token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    client_ip = _get_client_ip(request)
    expires_at = datetime.now(UTC) + timedelta(days=settings.session_token_expiry_days)

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

    logger.info(
        "Session token issued", extra={"email": email, "device_hostname": body.device_hostname}
    )

    return SessionExchangeResponse(
        session_token=raw_token,
        expires_at=expires_at.isoformat(),
        email=email,
    )


@router.post("/auth/token", response_model=AccessTokenResponse)
@limiter.limit("60/minute")
async def exchange_session_for_access_token(
    request: Request,
    body: AccessTokenRequest,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> AccessTokenResponse:
    """Exchange a session token for a short-lived access token (Phase 2).

    This is the headless path: no browser required. The session token
    (obtained once via Phase 1) is exchanged for a short-lived token
    scoped to the requested pseudo-scope.
    """
    # Validate session token
    token_hash = hashlib.sha256(body.session_token.encode()).hexdigest()
    session_data = await db.validate_session_token(token_hash)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Session expired or revoked. Run: extrasuite auth login",
        )
    email = str(session_data["email"])

    # Validate pseudo-scope
    if body.pseudo_scope not in _ALL_SCOPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pseudo-scope: {body.pseudo_scope}. Valid: {sorted(_ALL_SCOPES)}",
        )

    # Log access (best-effort)
    client_ip = _get_client_ip(request)
    try:
        await db.log_access_token_request(
            email=email,
            session_hash_prefix=token_hash[:16],
            pseudo_scope=body.pseudo_scope,
            credential_type="sa" if body.pseudo_scope in _SA_SCOPES else "dwd",
            reason=body.reason,
            ip=client_ip,
            file_hint=body.file_hint,
        )
    except Exception as e:
        logger.warning("Failed to log access token request", extra={"error": str(e)})

    # Generate token
    token_generator = TokenGenerator(database=db, settings=settings)
    if body.pseudo_scope in _SA_SCOPES:
        result = await token_generator.generate_token(email)
    else:
        scope_url = _resolve_scope(body.pseudo_scope)
        result = await token_generator.generate_delegated_token(email, [scope_url])

    logger.info(
        "Access token issued",
        extra={"email": email, "pseudo_scope": body.pseudo_scope},
    )

    return AccessTokenResponse(
        access_token=result.token,
        expires_at=result.expires_at.isoformat(),
    )


# =============================================================================
# Admin Session Management Endpoints
# =============================================================================


@router.get("/admin/sessions")
@limiter.limit("30/minute")
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

    if (
        caller_email.lower() != email.lower()
        and caller_email.lower() not in settings.get_admin_emails()
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to view sessions for this email"
        )

    sessions = await db.list_session_tokens(email)
    return sessions


@router.delete("/admin/sessions/{session_hash}", status_code=204)
@limiter.limit("30/minute")
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

    if not is_admin:
        # Verify caller owns this session
        sessions = await db.list_session_tokens(caller_email)
        owns = any(s["session_hash"] == session_hash for s in sessions)
        if not owns:
            raise HTTPException(status_code=403, detail="Not authorized to revoke this session")

    found = await db.revoke_session_token(session_hash)
    if not found:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(
        "Session revoked", extra={"session_hash_prefix": session_hash[:16], "by": caller_email}
    )
    return Response(status_code=204)


@router.post("/admin/sessions/revoke-all")
@limiter.limit("10/minute")
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

    if (
        caller_email.lower() != email.lower()
        and caller_email.lower() not in settings.get_admin_emails()
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to revoke sessions for this email"
        )

    count = await db.revoke_all_session_tokens(email)
    logger.info("All sessions revoked", extra={"email": email, "count": count, "by": caller_email})
    return {"revoked_count": count}


# =============================================================================
# Private Helpers
# =============================================================================


_GOOGLE_SCOPE_PREFIX = "https://www.googleapis.com/auth/"


def _resolve_scope(scope: str) -> str:
    """Resolve a short scope name to a full Google API scope URL."""
    if scope.startswith("https://"):
        return scope
    return f"{_GOOGLE_SCOPE_PREFIX}{scope}"


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


async def _generate_delegation_code_and_redirect(
    db: Database,
    email: str,
    scopes: list[str],
    reason: str,
    cli_redirect: str,
) -> RedirectResponse:
    """Generate a delegation auth code and redirect to CLI."""
    auth_code = secrets.token_urlsafe(32)
    await db.save_delegation_auth_code(auth_code, email, scopes, reason)

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
