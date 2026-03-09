"""Credential provider abstractions for ExtraSuite.

Each provider encapsulates a single credential strategy:
- ServiceAccountProvider: impersonates a per-user GCP service account
- DWDProvider: uses domain-wide delegation (server signs JWT as user)
- OAuthRefreshProvider: exchanges a stored OAuth refresh token for an access token

Providers are constructed ONCE at startup and injected into CommandCredentialRouter.
No credential-mode if/else branches exist outside of router construction.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from extrasuite.server.crypto import RefreshTokenEncryptor
    from extrasuite.server.token_generator import GeneratedToken, TokenGenerator


class CredentialProvider(ABC):
    """Abstract base for credential providers.

    Each concrete implementation encapsulates one auth strategy.
    Lifecycle hooks are called by CommandCredentialRouter at the appropriate
    points in the auth flow; most providers implement some hooks as no-ops.
    """

    kind: str  # "bearer_sa" | "bearer_dwd" | "bearer_oauth"

    @property
    def needs_refresh_token(self) -> bool:
        """True if generate_token() requires an encrypted refresh token.

        The router retrieves the token from DB only when this is True,
        avoiding unnecessary DB lookups for SA and DWD providers.
        """
        return False

    @abstractmethod
    async def generate_token(
        self, email: str, scopes: list[str], encrypted_token: str = ""
    ) -> GeneratedToken:
        """Generate a short-lived access token.

        Args:
            email: Authenticated user email.
            scopes: OAuth scope URLs required for the command (empty for SA).
            encrypted_token: Encrypted refresh token from Firestore (OAuth only).
        """

    async def on_google_auth_callback(self, _email: str, _credentials: Any) -> None:
        """Called after Google OAuth completes in google_callback().

        Args:
            _email: Verified user email from the ID token.
            _credentials: google-auth credentials object (has .refresh_token attribute).
        """
        return  # no-op default; override in subclasses that need OAuth token storage

    async def on_session_establishment(self, _email: str) -> None:
        """Called in exchange_auth_code_for_session() before the session token is issued.

        Args:
            _email: Verified user email.
        """
        return  # no-op default; override in subclasses that provision service accounts

    async def on_logout(self, _email: str) -> None:
        """Called when the user explicitly logs out via extrasuite auth logout.

        Args:
            _email: Verified user email from the session token.
        """
        return  # no-op default; override in subclasses that store revocable tokens


class ServiceAccountProvider(CredentialProvider):
    """Authenticates via per-user GCP service account impersonation.

    Used for sheet/doc/slide/form/drive SA commands in sa+dwd and sa+oauth modes.
    """

    kind = "bearer_sa"

    def __init__(self, token_generator: TokenGenerator) -> None:
        self._token_generator = token_generator

    async def generate_token(
        self, email: str, _scopes: list[str], _encrypted_token: str = ""
    ) -> GeneratedToken:
        return await self._token_generator.generate_token(email)

    async def on_session_establishment(self, email: str) -> None:
        """Provision the service account before issuing the session token."""
        await self._token_generator.ensure_service_account(email)


class DWDProvider(CredentialProvider):
    """Authenticates via domain-wide delegation (server JWT → user impersonation).

    Used for gmail/calendar/contacts/drive.file/script commands in sa+dwd mode.
    Requires a SA to be provisioned (for the server's identity lookup), so
    on_session_establishment also calls ensure_service_account.
    """

    kind = "bearer_dwd"

    def __init__(self, token_generator: TokenGenerator) -> None:
        self._token_generator = token_generator

    async def generate_token(
        self, email: str, scopes: list[str], _encrypted_token: str = ""
    ) -> GeneratedToken:
        return await self._token_generator.generate_delegated_token(email, scopes)

    async def on_session_establishment(self, email: str) -> None:
        """Provision SA — required for the DWD identity lookup at delegation time."""
        await self._token_generator.ensure_service_account(email)


class OAuthRefreshProvider(CredentialProvider):
    """Authenticates using the user's stored OAuth refresh token.

    Used for all commands in oauth mode, and for DWD-class commands in sa+oauth mode.
    Stores an AES-256-GCM encrypted refresh token in Firestore at login time.
    """

    kind = "bearer_oauth"

    def __init__(
        self,
        token_generator: TokenGenerator,
        database: Any,  # DatabaseProtocol — Any to avoid circular import
        encryptor: RefreshTokenEncryptor,
    ) -> None:
        self._token_generator = token_generator
        self._db = database
        self._encryptor = encryptor

    @property
    def needs_refresh_token(self) -> bool:
        return True

    async def generate_token(
        self, email: str, scopes: list[str], encrypted_token: str = ""
    ) -> GeneratedToken:
        return await self._token_generator.generate_oauth_token(email, encrypted_token, scopes)

    async def on_google_auth_callback(self, email: str, credentials: Any) -> None:
        """Capture and store the refresh token after OAuth consent.

        If credentials.refresh_token is absent (user re-authed without prompt=consent),
        log a warning. The existing token in Firestore may still be valid.
        """
        refresh_token = getattr(credentials, "refresh_token", None)
        if not refresh_token:
            logger.warning(
                "No refresh_token in OAuth callback — user may not have granted offline access. "
                "Existing stored token (if any) is preserved.",
                extra={"email": email},
            )
            return

        try:
            encrypted = self._encryptor.encrypt(refresh_token)
            # Scopes are stored as a hint for scope-mismatch detection
            scopes_str = " ".join(getattr(credentials, "scopes", None) or [])
            await self._db.set_refresh_token(email, encrypted, scopes_str)
            logger.info("OAuth refresh token stored", extra={"email": email})
        except Exception as e:
            logger.error(
                "Failed to store OAuth refresh token",
                extra={"email": email, "error": str(e)},
            )
            raise

    async def on_logout(self, email: str) -> None:
        """Revoke the stored refresh token at Google and delete it from Firestore.

        Google revocation invalidates all access tokens minted from this refresh token.
        Network failure on revocation is logged but does NOT block logout —
        the Firestore deletion still prevents future use from ExtraSuite's server.
        """
        encrypted = await self._db.get_encrypted_refresh_token(email)

        if encrypted:
            try:
                plaintext = self._encryptor.decrypt(encrypted)
                _revoke_token_at_google(plaintext)
                logger.info("OAuth refresh token revoked at Google", extra={"email": email})
            except Exception as e:
                logger.warning(
                    "Failed to revoke OAuth token at Google (continuing logout)",
                    extra={"email": email, "error": str(e)},
                )

        try:
            await self._db.delete_refresh_token(email)
        except Exception as e:
            logger.error(
                "Failed to delete refresh token from Firestore",
                extra={"email": email, "error": str(e)},
            )
            raise


def _revoke_token_at_google(refresh_token: str) -> None:
    """POST to Google's token revocation endpoint (blocking, call in thread if needed).

    Revocation invalidates all access tokens derived from this refresh token.
    Errors are raised to the caller; the caller decides whether to log and continue.
    """
    data = urllib.parse.urlencode({"token": refresh_token}).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/revoke",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        _ = resp.read()
