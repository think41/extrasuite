"""Session management using starlette's signed cookie sessions.

Uses starlette's SessionMiddleware for secure, signed cookies.
The cookie stores only the user's email - credentials are looked up from Firestore.

This is stateless session management - no server-side session storage needed.
"""

from datetime import timedelta

from fastapi import Request

from gwg_server.database import Database

# Session configuration
SESSION_COOKIE_NAME = "gwg_session"
SESSION_MAX_AGE = timedelta(days=30)
SESSION_EMAIL_KEY = "email"


def get_session_email(request: Request) -> str | None:
    """Get the email from the session cookie.

    Returns None if no valid session exists.
    """
    return request.session.get(SESSION_EMAIL_KEY)


async def get_session_email_if_valid(request: Request, db: Database) -> str | None:
    """Get the email from session if user has valid credentials in Firestore.

    Returns None if:
    - No session exists
    - User has no credentials in Firestore
    - User's refresh token is missing
    """
    email = get_session_email(request)
    if not email:
        return None

    # Validate that user has credentials in Firestore
    user_creds = await db.get_user_credentials(email)
    if not user_creds or not user_creds.refresh_token:
        return None

    return email


def set_session_email(request: Request, email: str) -> None:
    """Set the email in the session cookie."""
    request.session[SESSION_EMAIL_KEY] = email


def clear_session(request: Request) -> None:
    """Clear the session."""
    request.session.clear()


def get_session_middleware_config(secret_key: str, is_production: bool) -> dict:
    """Get configuration for starlette's SessionMiddleware.

    Args:
        secret_key: Secret key for signing cookies
        is_production: Whether running in production (enables secure flag)

    Returns:
        Dict of kwargs for SessionMiddleware
    """
    return {
        "secret_key": secret_key,
        "session_cookie": SESSION_COOKIE_NAME,
        "max_age": int(SESSION_MAX_AGE.total_seconds()),
        "same_site": "lax",
        "https_only": is_production,
    }
