"""ExtraSuite Client - Secure OAuth token exchange for CLI tools.

This library provides a simple interface to obtain short-lived Google service
account tokens via the ExtraSuite protocol or service account files. It handles
the OAuth flow automatically, including browser-based authentication and token caching.

Example:
    from extrasuite_client import CredentialsManager

    # Configure via environment variables:
    # - AUTH_URL and EXCHANGE_URL for ExtraSuite protocol
    # - SERVICE_ACCOUNT_PATH for service account file
    manager = CredentialsManager()
    token = manager.get_token()

    # Use token with Google APIs
    import gspread
    from google.oauth2.credentials import Credentials

    creds = Credentials(token=token.access_token)
    gc = gspread.authorize(creds)
"""

from extrasuite_client.credentials import CredentialsManager, Token

__version__ = "1.0.0"
__all__ = ["CredentialsManager", "Token"]
