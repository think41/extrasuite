"""Google Workspace Gateway - Secure OAuth token exchange for CLI tools.

This library provides a simple interface to obtain short-lived Google service
account tokens via a Google Workspace Gateway server. It handles the OAuth
flow automatically, including browser-based authentication and token caching.

Example:
    from google_workspace_gateway import GoogleWorkspaceGateway

    gateway = GoogleWorkspaceGateway(server_url="https://your-gwg-server.example.com")
    token = gateway.get_token()

    # Use token with Google APIs
    import gspread
    from google.oauth2.credentials import Credentials

    creds = Credentials(token)
    gc = gspread.authorize(creds)
"""

from google_workspace_gateway.gateway import GoogleWorkspaceGateway

__version__ = "1.0.0"
__all__ = ["GoogleWorkspaceGateway"]
