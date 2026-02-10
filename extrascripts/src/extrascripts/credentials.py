"""Credentials management for Google Apps Script API access.

Re-exports CredentialsManager from the extrasuite client package,
which supports both ExtraSuite server and service account authentication.

Note: The Apps Script API does not support service accounts for most
operations. User OAuth tokens with appropriate scopes are required.
"""

from extrasuite.client import CredentialsManager, Token, authenticate

__all__ = ["CredentialsManager", "Token", "authenticate"]
