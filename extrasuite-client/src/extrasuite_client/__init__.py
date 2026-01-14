"""ExtraSuite Client - Secure OAuth token exchange for CLI tools.

This library provides a simple interface to obtain short-lived Google service
account tokens via an ExtraSuite server. It handles the OAuth flow automatically,
including browser-based authentication and token caching.

Example:
    from extrasuite_client import ExtraSuiteClient

    client = ExtraSuiteClient(server_url="https://your-extrasuite-server.example.com")
    token = client.get_token()

    # Use token with Google APIs
    import gspread
    from google.oauth2.credentials import Credentials

    creds = Credentials(token)
    gc = gspread.authorize(creds)
"""

from extrasuite_client.gateway import ExtraSuiteClient

__version__ = "1.0.0"
__all__ = ["ExtraSuiteClient"]
