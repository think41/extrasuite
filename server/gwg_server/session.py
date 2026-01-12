"""Session management for Google Workspace Gateway authentication.

Provides cookie-based session management backed by Firestore.
Sessions allow users to refresh tokens without re-authenticating.
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response

from gwg_server.database import create_session, delete_session, get_session

# Session configuration
SESSION_COOKIE_NAME = "gwg_session"
SESSION_MAX_AGE = timedelta(days=30)  # Sessions last 30 days


def get_session_id(request: Request) -> str | None:
    """Get session ID from request cookie."""
    return request.cookies.get(SESSION_COOKIE_NAME)


def get_session_email(request: Request) -> str | None:
    """Get the email associated with the current session.

    Returns None if no valid session exists.
    """
    session_id = get_session_id(request)
    if not session_id:
        return None

    session = get_session(session_id)
    if not session:
        return None

    # Check if session is expired (30 days)
    if session.created_at and datetime.now(UTC) - session.created_at > SESSION_MAX_AGE:
        # Session expired, delete it
        delete_session(session_id)
        return None

    return session.email


def create_user_session(response: Response, email: str) -> str:
    """Create a new session for the user and set the cookie.

    Returns the session ID.
    """
    session_id = secrets.token_urlsafe(32)
    create_session(session_id, email)

    # Set secure cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=int(SESSION_MAX_AGE.total_seconds()),
        httponly=True,
        samesite="lax",
        # secure=True should be set in production
    )

    return session_id


def clear_session(request: Request, response: Response) -> None:
    """Clear the current session."""
    session_id = get_session_id(request)
    if session_id:
        delete_session(session_id)

    response.delete_cookie(SESSION_COOKIE_NAME)
