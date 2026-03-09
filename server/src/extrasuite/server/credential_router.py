"""Command-to-credential routing table for ExtraSuite.

The CommandCredentialRouter is built ONCE at application startup from settings.
After construction, no credential_mode if/else checks exist anywhere at runtime.
All routing decisions are encoded in the table at construction time.

Lifecycle hooks (on_google_auth_callback, on_session_establishment, on_logout) are
dispatched to all unique providers, so each provider only needs to implement the
hooks relevant to its strategy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from loguru import logger

from extrasuite.server.command_registry import (
    _ALL_COMMAND_TYPES,
    _DWD_COMMAND_SCOPES,
    _SA_COMMAND_TYPES,
    Credential,
)
from extrasuite.server.credential_provider import (
    CredentialProvider,
    DWDProvider,
    OAuthRefreshProvider,
    ServiceAccountProvider,
)

if TYPE_CHECKING:
    from extrasuite.server.config import Settings
    from extrasuite.server.crypto import RefreshTokenEncryptor
    from extrasuite.server.token_generator import TokenGenerator

_GOOGLE_SCOPE_PREFIX = "https://www.googleapis.com/auth/"

# OAuth scope URLs for SA-class commands when CREDENTIAL_MODE=oauth.
# In oauth mode, the user's own OAuth token (not a service account) is used.
_OAUTH_SA_COMMAND_SCOPES: dict[str, list[str]] = {
    "sheet.pull": [f"{_GOOGLE_SCOPE_PREFIX}spreadsheets"],
    "sheet.push": [f"{_GOOGLE_SCOPE_PREFIX}spreadsheets"],
    "sheet.batchupdate": [f"{_GOOGLE_SCOPE_PREFIX}spreadsheets"],
    "doc.pull": [f"{_GOOGLE_SCOPE_PREFIX}documents"],
    "doc.push": [f"{_GOOGLE_SCOPE_PREFIX}documents"],
    "slide.pull": [f"{_GOOGLE_SCOPE_PREFIX}presentations"],
    "slide.push": [f"{_GOOGLE_SCOPE_PREFIX}presentations"],
    "form.pull": [f"{_GOOGLE_SCOPE_PREFIX}forms.body"],
    "form.push": [f"{_GOOGLE_SCOPE_PREFIX}forms.body"],
    "drive.ls": [f"{_GOOGLE_SCOPE_PREFIX}drive.readonly"],
    "drive.search": [f"{_GOOGLE_SCOPE_PREFIX}drive.readonly"],
}

# Routing table entry: (provider, scopes_for_this_command)
_RouteEntry = tuple[CredentialProvider, list[str]]


class CommandCredentialRouter:
    """Maps command types to providers. Built ONCE at startup from settings.

    After construction, no credential_mode checks exist anywhere at runtime.
    All mode decisions are encoded in self._table at construction time.

    Usage:
        router = CommandCredentialRouter.from_settings(settings, token_generator, db, encryptor)
        credentials = await router.resolve(command, email)
    """

    def __init__(
        self,
        table: dict[str, _RouteEntry],
        unique_providers: list[CredentialProvider],
        settings: Any,
        database: Any,
    ) -> None:
        self._table = table
        self._unique_providers = unique_providers
        self._settings = settings
        self._database = database

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        token_generator: TokenGenerator,
        database: Any,
        encryptor: RefreshTokenEncryptor | None,
    ) -> CommandCredentialRouter:
        """Build the routing table from credential_mode. Called once in lifespan.

        Args:
            settings: Application settings (credential_mode determines routing).
            token_generator: Shared TokenGenerator instance.
            database: Database instance (needed by OAuthRefreshProvider and the router).
            encryptor: RefreshTokenEncryptor; required when settings.uses_oauth, else None.

        Raises:
            ValueError: If uses_oauth=True but encryptor is None.
        """
        if settings.uses_oauth and encryptor is None:
            raise ValueError(
                "RefreshTokenEncryptor is required when CREDENTIAL_MODE != sa+dwd"
            )

        sa_provider = ServiceAccountProvider(token_generator)
        dwd_provider = DWDProvider(token_generator)
        oauth_provider = (
            OAuthRefreshProvider(token_generator, database, encryptor)  # type: ignore[arg-type]
            if settings.uses_oauth
            else None
        )

        table: dict[str, _RouteEntry] = {}

        if settings.credential_mode == "oauth":
            # All SA-class commands go through OAuth
            for cmd_type in _SA_COMMAND_TYPES:
                scopes = _OAUTH_SA_COMMAND_SCOPES[cmd_type]
                table[cmd_type] = (oauth_provider, scopes)  # type: ignore[assignment]
        else:
            # sa+dwd or sa+oauth: SA-class commands use service account impersonation
            for cmd_type in _SA_COMMAND_TYPES:
                table[cmd_type] = (sa_provider, [])

        for cmd_type, scopes in _DWD_COMMAND_SCOPES.items():
            if settings.credential_mode == "sa+dwd":
                table[cmd_type] = (dwd_provider, scopes)
            else:
                # sa+oauth or oauth: DWD-class commands use OAuth
                table[cmd_type] = (oauth_provider, scopes)  # type: ignore[assignment]

        # Deduplicate providers for lifecycle dispatch
        seen: dict[int, CredentialProvider] = {}
        for provider, _ in table.values():
            seen[id(provider)] = provider
        unique_providers = list(seen.values())

        logger.info(
            "Credential router built",
            extra={"credential_mode": settings.credential_mode, "routes": len(table)},
        )

        return cls(table, unique_providers, settings, database)

    # -------------------------------------------------------------------------
    # Runtime credential resolution
    # -------------------------------------------------------------------------

    async def resolve(self, command: Any, email: str) -> list[Credential]:
        """Look up the provider for command.type, generate and return credentials.

        Performs scope allowlist enforcement and, for OAuth providers, retrieves
        the encrypted refresh token from the database before calling generate_token().

        Args:
            command: Typed command object (has .type attribute).
            email: Authenticated user email.

        Returns:
            List containing exactly one Credential (extensible for future multi-provider).

        Raises:
            HTTPException(400): Unknown command type.
            HTTPException(400): OAuth refresh token not found (user must re-login).
            HTTPException(403): Scope not in server allowlist.
        """
        cmd_type = command.type

        if cmd_type not in _ALL_COMMAND_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown command type: {cmd_type!r}. "
                    f"Valid types: {sorted(_ALL_COMMAND_TYPES)}"
                ),
            )

        provider, scopes = self._table[cmd_type]

        # Enforce server-side scope allowlist (DWD-class commands only; SA scopes are internal)
        disallowed = [s for s in scopes if not self._settings.is_scope_allowed(s)]
        if disallowed:
            short_names = [s.removeprefix(_GOOGLE_SCOPE_PREFIX) for s in disallowed]
            raise HTTPException(
                status_code=403,
                detail=f"Scope(s) {short_names!r} are not permitted by server configuration.",
            )

        # For OAuth providers: retrieve the encrypted refresh token from DB
        encrypted_token = ""
        if provider.needs_refresh_token:
            encrypted_token = await self._database.get_encrypted_refresh_token(email) or ""
            if not encrypted_token:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "OAuth credentials not found for this account. "
                        "Run 'extrasuite auth login' to authenticate."
                    ),
                )

        result = await provider.generate_token(email, scopes, encrypted_token)

        return [
            Credential(
                provider="google",
                kind=provider.kind,
                token=result.token,
                expires_at=result.expires_at.isoformat(),
                scopes=scopes,
                metadata=(
                    {"service_account_email": result.service_account_email}
                    if result.service_account_email
                    else {}
                ),
            )
        ]

    # -------------------------------------------------------------------------
    # Lifecycle hooks — dispatched to all unique providers
    # -------------------------------------------------------------------------

    async def on_google_auth_callback(self, email: str, credentials: Any) -> None:
        """Dispatch to all unique providers after Google OAuth callback."""
        for provider in self._unique_providers:
            await provider.on_google_auth_callback(email, credentials)

    async def on_session_establishment(self, email: str) -> None:
        """Dispatch to all unique providers before issuing a session token."""
        for provider in self._unique_providers:
            await provider.on_session_establishment(email)

    async def on_logout(self, email: str) -> None:
        """Dispatch to all unique providers on explicit logout."""
        for provider in self._unique_providers:
            await provider.on_logout(email)
