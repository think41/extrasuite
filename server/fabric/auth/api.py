"""Google OAuth authentication API endpoints."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from fabric.config import Settings, get_settings

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


# In-memory state storage for OAuth flow (use Redis in production)
_oauth_states: dict[str, datetime] = {}


def get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Get serializer for signing session cookies."""
    return URLSafeTimedSerializer(settings.secret_key)


def create_oauth_flow(settings: Settings) -> Flow:
    """Create Google OAuth flow."""
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
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
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


@router.get("/google")
async def google_login(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    """Initiate Google OAuth login flow."""
    flow = create_oauth_flow(settings)

    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = datetime.now(UTC)

    # Clean up old states (older than 10 minutes)
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    for old_state in list(_oauth_states.keys()):
        if _oauth_states[old_state] < cutoff:
            del _oauth_states[old_state]

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Google OAuth callback."""
    # Verify state token
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state token")

    # Check state expiry (10 minutes)
    state_time = _oauth_states.pop(state)
    if datetime.now(UTC) - state_time > timedelta(minutes=10):
        raise HTTPException(status_code=400, detail="State token expired")

    # Exchange code for tokens
    flow = create_oauth_flow(settings)
    try:
        flow.fetch_token(code=code)
    except Exception as e:
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
        raise HTTPException(status_code=400, detail=f"Failed to verify token: {e}") from None

    # Create session data
    session_data = SessionData(
        email=id_info.get("email", ""),
        name=id_info.get("name", ""),
        picture=id_info.get("picture"),
        hd=id_info.get("hd"),  # Hosted domain
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
