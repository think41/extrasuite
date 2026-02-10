"""ExtraSuite Client - Secure OAuth token exchange for CLI tools.

This library provides a simple interface to obtain short-lived Google service
account tokens via the ExtraSuite protocol or service account files. It handles
the OAuth flow automatically, including browser-based authentication and token caching.

Tokens are cached in ~/.config/extrasuite/token.json with secure file permissions
(readable only by owner). This follows the same pattern used by gcloud, aws-cli,
and other CLI tools that store short-lived credentials.

Example:
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager()
    token = manager.get_token()

    # Use token with Google APIs
    import gspread
    from google.oauth2.credentials import Credentials

    creds = Credentials(token=token.access_token)
    gc = gspread.authorize(creds)
"""

from extrasuite.client.credentials import (
    CredentialsManager,
    OAuthToken,
    Token,
)

__version__ = "0.4.0"
__all__ = [
    "CredentialsManager",
    "OAuthToken",
    "Token",
]
