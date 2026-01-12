"""OAuth configuration and flow creation.

This module contains shared OAuth constants and utilities used by both
google_auth.py and token_exchange.py, avoiding circular imports.
"""

import secrets

from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow

from gwg_server.config import Settings
from gwg_server.database import Database

# OAuth scopes for CLI login (includes cloud-platform for SA impersonation)
CLI_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cloud-platform",
]

# Scopes for the impersonated SA token (what the CLI can do)
SA_TOKEN_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]


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


async def create_cli_auth_state(db: Database, cli_redirect: str) -> str:
    """Create and store a new OAuth state token for CLI flow in Firestore."""
    state = secrets.token_urlsafe(32)
    await db.create_oauth_state(state, cli_redirect)
    return state
