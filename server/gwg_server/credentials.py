"""OAuth credential storage.

This module handles storing and retrieving user OAuth credentials.
"""

from google.oauth2.credentials import Credentials

from gwg_server.database import Database
from gwg_server.oauth import CLI_SCOPES


def store_oauth_credentials(db: Database, email: str, credentials: Credentials) -> None:
    """Store or update OAuth credentials in Firestore."""
    scopes = list(credentials.scopes) if credentials.scopes else CLI_SCOPES
    db.store_user_credentials(
        email=email,
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        scopes=scopes,
    )
