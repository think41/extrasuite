"""ExtraSuite Client - Secure OAuth token exchange for CLI tools.

This library provides a simple interface to obtain short-lived Google service
account tokens via the ExtraSuite protocol or service account files. It handles
the OAuth flow automatically, including browser-based authentication and token caching.

Tokens are securely stored in the OS keyring (macOS Keychain, Windows Credential
Locker, or Linux Secret Service).

Example:
    from extrasuite_client import authenticate

    # Configure via environment variables:
    # - EXTRASUITE_AUTH_URL and EXTRASUITE_EXCHANGE_URL for ExtraSuite protocol
    # - SERVICE_ACCOUNT_PATH for service account file
    token = authenticate()

    # Use token with Google APIs
    import gspread
    from google.oauth2.credentials import Credentials

    creds = Credentials(token=token.access_token)
    gc = gspread.authorize(creds)
"""

from extrasuite_client.credentials import CredentialsManager, Token, authenticate

__version__ = "0.1.0"
__all__ = ["CredentialsManager", "Token", "authenticate"]
