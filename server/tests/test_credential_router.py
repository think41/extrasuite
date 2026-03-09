"""Tests for CommandCredentialRouter: routing table construction and resolve()."""

import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from extrasuite.server.command_registry import _DWD_COMMAND_SCOPES, _SA_COMMAND_TYPES
from extrasuite.server.credential_provider import (
    DWDProvider,
    OAuthRefreshProvider,
    ServiceAccountProvider,
)
from extrasuite.server.credential_router import _OAUTH_SA_COMMAND_SCOPES, CommandCredentialRouter
from extrasuite.server.crypto import RefreshTokenEncryptor
from extrasuite.server.token_generator import GeneratedToken
from tests.fakes import FakeDatabase, FakeSettings


def _make_encryptor() -> RefreshTokenEncryptor:
    return RefreshTokenEncryptor(secrets.token_hex(32))


def _make_token_generator() -> MagicMock:

    tg = MagicMock()
    token = GeneratedToken(
        token="fake-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        service_account_email="sa@proj.iam.gserviceaccount.com",
    )
    tg.generate_token = AsyncMock(return_value=token)
    tg.generate_delegated_token = AsyncMock(return_value=token)
    tg.generate_oauth_token = AsyncMock(return_value=token)
    tg.ensure_service_account = AsyncMock(return_value="sa@proj.iam.gserviceaccount.com")
    return tg


def _make_router(credential_mode: str = "sa+dwd", encryptor=None) -> tuple[CommandCredentialRouter, FakeDatabase]:
    db = FakeDatabase()
    settings = FakeSettings(credential_mode=credential_mode)
    tg = _make_token_generator()
    if encryptor is None and settings.uses_oauth:
        encryptor = _make_encryptor()
    router = CommandCredentialRouter.from_settings(settings, tg, db, encryptor)
    return router, db


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------


class TestRouterConstruction:
    def test_sa_dwd_mode_sa_commands_use_sa_provider(self):
        router, _ = _make_router("sa+dwd")
        for cmd_type in _SA_COMMAND_TYPES:
            provider, scopes = router._table[cmd_type]
            assert isinstance(provider, ServiceAccountProvider), f"{cmd_type} should use SA"
            assert scopes == []

    def test_sa_dwd_mode_dwd_commands_use_dwd_provider(self):
        router, _ = _make_router("sa+dwd")
        for cmd_type, expected_scopes in _DWD_COMMAND_SCOPES.items():
            provider, scopes = router._table[cmd_type]
            assert isinstance(provider, DWDProvider), f"{cmd_type} should use DWD"
            assert scopes == expected_scopes

    def test_sa_oauth_mode_sa_commands_use_sa_provider(self):
        router, _ = _make_router("sa+oauth")
        for cmd_type in _SA_COMMAND_TYPES:
            provider, scopes = router._table[cmd_type]
            assert isinstance(provider, ServiceAccountProvider), f"{cmd_type} should use SA"
            assert scopes == []

    def test_sa_oauth_mode_dwd_commands_use_oauth_provider(self):
        router, _ = _make_router("sa+oauth")
        for cmd_type in _DWD_COMMAND_SCOPES:
            provider, scopes = router._table[cmd_type]
            assert isinstance(provider, OAuthRefreshProvider), f"{cmd_type} should use OAuth"
            assert scopes == _DWD_COMMAND_SCOPES[cmd_type]

    def test_oauth_mode_all_commands_use_oauth_provider(self):
        router, _ = _make_router("oauth")
        for cmd_type in _SA_COMMAND_TYPES:
            provider, _ = router._table[cmd_type]
            assert isinstance(provider, OAuthRefreshProvider), f"{cmd_type} should use OAuth"
        for cmd_type in _DWD_COMMAND_SCOPES:
            provider, _ = router._table[cmd_type]
            assert isinstance(provider, OAuthRefreshProvider), f"{cmd_type} should use OAuth"

    def test_oauth_mode_sa_commands_have_correct_scopes(self):
        router, _ = _make_router("oauth")
        for cmd_type in _SA_COMMAND_TYPES:
            _, scopes = router._table[cmd_type]
            assert scopes == _OAUTH_SA_COMMAND_SCOPES[cmd_type], f"{cmd_type} scope mismatch"

    def test_uses_oauth_without_encryptor_raises(self):
        settings = FakeSettings(credential_mode="oauth")
        tg = _make_token_generator()
        db = FakeDatabase()
        with pytest.raises(ValueError, match=r"[Ee]ncryptor"):
            CommandCredentialRouter.from_settings(settings, tg, db, encryptor=None)

    def test_sa_dwd_unique_providers_count(self):
        """sa+dwd: 2 unique providers (SA + DWD)."""
        router, _ = _make_router("sa+dwd")
        kinds = {p.kind for p in router._unique_providers}
        assert "bearer_sa" in kinds
        assert "bearer_dwd" in kinds
        assert "bearer_oauth" not in kinds

    def test_oauth_unique_providers_count(self):
        """oauth: 1 unique provider (OAuth only)."""
        router, _ = _make_router("oauth")
        kinds = {p.kind for p in router._unique_providers}
        assert kinds == {"bearer_oauth"}


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


class TestResolve:
    def _make_command(self, cmd_type: str):
        cmd = MagicMock()
        cmd.type = cmd_type
        cmd.model_dump.return_value = {}
        return cmd

    @pytest.mark.asyncio
    async def test_resolve_sa_command_in_sa_dwd_mode(self):
        router, _ = _make_router("sa+dwd")
        cmd = self._make_command("sheet.pull")
        credentials = await router.resolve(cmd, "user@example.com")
        assert len(credentials) == 1
        assert credentials[0].kind == "bearer_sa"

    @pytest.mark.asyncio
    async def test_resolve_dwd_command_in_sa_dwd_mode(self):
        router, _ = _make_router("sa+dwd")
        cmd = self._make_command("gmail.read")
        credentials = await router.resolve(cmd, "user@example.com")
        assert len(credentials) == 1
        assert credentials[0].kind == "bearer_dwd"

    @pytest.mark.asyncio
    async def test_resolve_oauth_command_retrieves_encrypted_token(self):
        encryptor = _make_encryptor()
        router, db = _make_router("sa+oauth", encryptor)
        # Store a refresh token for the user
        encrypted = encryptor.encrypt("my-refresh-token")
        await db.set_refresh_token("user@example.com", encrypted, "")

        cmd = self._make_command("gmail.compose")
        credentials = await router.resolve(cmd, "user@example.com")
        assert credentials[0].kind == "bearer_oauth"

    @pytest.mark.asyncio
    async def test_resolve_oauth_command_missing_token_raises_400(self):
        router, _ = _make_router("sa+oauth")
        # No refresh token stored
        cmd = self._make_command("gmail.compose")
        with pytest.raises(HTTPException) as exc_info:
            await router.resolve(cmd, "user@example.com")
        assert exc_info.value.status_code == 400
        assert "auth login" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_resolve_unknown_command_raises_400(self):
        router, _ = _make_router("sa+dwd")
        cmd = self._make_command("nonexistent.command")
        with pytest.raises(HTTPException) as exc_info:
            await router.resolve(cmd, "user@example.com")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_resolve_disallowed_scope_raises_403(self):
        db = FakeDatabase()
        settings = FakeSettings(
            credential_mode="sa+dwd",
            delegation_scopes=["https://www.googleapis.com/auth/calendar"],
        )
        tg = _make_token_generator()
        router = CommandCredentialRouter.from_settings(settings, tg, db, encryptor=None)

        cmd = self._make_command("gmail.read")  # needs gmail.readonly, not in allowlist
        with pytest.raises(HTTPException) as exc_info:
            await router.resolve(cmd, "user@example.com")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_resolve_oauth_mode_sa_command_disallowed_scope_raises_403(self):
        """In oauth mode, SA-class commands also go through the server allowlist."""
        db = FakeDatabase()
        settings = FakeSettings(
            credential_mode="oauth",
            delegation_scopes=["https://www.googleapis.com/auth/calendar"],
        )
        tg = _make_token_generator()
        encryptor = _make_encryptor()
        router = CommandCredentialRouter.from_settings(settings, tg, db, encryptor)

        encrypted = encryptor.encrypt("some-token")
        await db.set_refresh_token(
            "user@example.com",
            encrypted,
            "https://www.googleapis.com/auth/spreadsheets",
        )

        cmd = self._make_command("sheet.pull")  # maps to spreadsheets scope in oauth mode
        with pytest.raises(HTTPException) as exc_info:
            await router.resolve(cmd, "user@example.com")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_resolve_scope_not_in_consented_scopes_raises_403(self):
        """Command scope not consented to at login → 403 with clear re-login message."""
        encryptor = _make_encryptor()
        router, db = _make_router("sa+oauth", encryptor)

        encrypted = encryptor.encrypt("my-refresh-token")
        # Consent only covered spreadsheets; gmail.compose was NOT consented
        await db.set_refresh_token(
            "user@example.com",
            encrypted,
            "https://www.googleapis.com/auth/spreadsheets",
        )

        cmd = self._make_command("gmail.compose")
        with pytest.raises(HTTPException) as exc_info:
            await router.resolve(cmd, "user@example.com")
        assert exc_info.value.status_code == 403
        assert "auth login" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_resolve_scope_within_consented_scopes_succeeds(self):
        """Command scope is a subset of consented scopes → resolves successfully."""
        encryptor = _make_encryptor()
        router, db = _make_router("sa+oauth", encryptor)

        encrypted = encryptor.encrypt("my-refresh-token")
        gmail_compose = "https://www.googleapis.com/auth/gmail.compose"
        gmail_readonly = "https://www.googleapis.com/auth/gmail.readonly"
        await db.set_refresh_token(
            "user@example.com",
            encrypted,
            f"{gmail_compose} {gmail_readonly}",
        )

        cmd = self._make_command("gmail.compose")
        credentials = await router.resolve(cmd, "user@example.com")
        assert credentials[0].kind == "bearer_oauth"

    @pytest.mark.asyncio
    async def test_resolve_oauth_no_stored_scopes_skips_consent_check(self):
        """Old records without stored scopes skip the consent check (backward compat)."""
        encryptor = _make_encryptor()
        router, db = _make_router("sa+oauth", encryptor)

        encrypted = encryptor.encrypt("my-refresh-token")
        # Store with empty scopes — simulates pre-scope-tracking records
        await db.set_refresh_token("user@example.com", encrypted, "")

        cmd = self._make_command("gmail.compose")
        # Should not raise 403 for scope consent — falls through to token generation
        credentials = await router.resolve(cmd, "user@example.com")
        assert credentials[0].kind == "bearer_oauth"


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


class TestLifecycleHooks:
    @pytest.mark.asyncio
    async def test_on_session_establishment_dispatches_to_all_providers(self):
        """In sa+dwd mode, SA and DWD providers both get on_session_establishment."""
        router, _ = _make_router("sa+dwd")
        # Both SA and DWD providers call ensure_service_account
        for provider in router._unique_providers:
            provider.on_session_establishment = AsyncMock()

        await router.on_session_establishment("user@example.com")

        for provider in router._unique_providers:
            provider.on_session_establishment.assert_called_once_with("user@example.com")

    @pytest.mark.asyncio
    async def test_on_google_auth_callback_dispatches_to_all_providers(self):
        router, _ = _make_router("sa+dwd")
        fake_creds = MagicMock()
        for provider in router._unique_providers:
            provider.on_google_auth_callback = AsyncMock()

        await router.on_google_auth_callback("user@example.com", fake_creds)

        for provider in router._unique_providers:
            provider.on_google_auth_callback.assert_called_once_with("user@example.com", fake_creds)

    @pytest.mark.asyncio
    async def test_on_logout_dispatches_to_all_providers(self):
        router, _ = _make_router("sa+dwd")
        for provider in router._unique_providers:
            provider.on_logout = AsyncMock()

        await router.on_logout("user@example.com")

        for provider in router._unique_providers:
            provider.on_logout.assert_called_once_with("user@example.com")
