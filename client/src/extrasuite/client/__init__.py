"""ExtraSuite Client - Secure credential exchange for CLI tools.

This library provides a simple interface to obtain short-lived credentials via
the ExtraSuite protocol or service account files. It handles the OAuth flow
automatically, including browser-based authentication and credential caching.

Credentials are cached per command type in ~/.config/extrasuite/credentials/
with secure file permissions (readable only by owner).

Example::

    from extrasuite.client import CredentialsManager

    manager = CredentialsManager()
    cred = manager.get_credential(
        command={"type": "sheet.pull", "file_url": "https://docs.google.com/..."},
        reason="User wants to review the Q4 budget sheet",
    )
    # cred.token is the Bearer token for Google APIs
    # cred.service_account_email is the SA email (for file sharing)
"""

from extrasuite.client.credentials import (
    Credential,
    CredentialsManager,
)

__version__ = "0.4.0"
__all__ = [
    "Credential",
    "CredentialsManager",
]
