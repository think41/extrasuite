"""Tests for credential providers (ServiceAccountProvider, DWDProvider, OAuthRefreshProvider)."""

import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from extrasuite.server.credential_provider import (
    DWDProvider,
    OAuthRefreshProvider,
    ServiceAccountProvider,
)
from extrasuite.server.crypto import RefreshTokenEncryptor
from extrasuite.server.token_generator import (
    GeneratedToken,
    TokenGenerator,
)
from tests.fakes import (
    FakeDatabase,
    FakeIAMAsyncClient,
    FakeSettings,
    create_fake_impersonated_credentials_class,
)


def _make_encryptor() -> RefreshTokenEncryptor:
    return RefreshTokenEncryptor(secrets.token_hex(32))


def _make_token_generator(db=None, settings=None, encryptor=None):
    db = db or FakeDatabase()
    settings = settings or FakeSettings()
    iam_client = FakeIAMAsyncClient()
    FakeCreds = create_fake_impersonated_credentials_class()
    return TokenGenerator(
        database=db,
        settings=settings,
        iam_client=iam_client,
        impersonated_credentials_class=FakeCreds,
        encryptor=encryptor,
    )


def _fake_generated_token(kind: str = "sa") -> GeneratedToken:
    return GeneratedToken(
        token=f"fake-token-{kind}",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        service_account_email="sa@project.iam.gserviceaccount.com" if kind == "sa" else "",
    )


# ---------------------------------------------------------------------------
# ServiceAccountProvider
# ---------------------------------------------------------------------------


class TestServiceAccountProvider:
    @pytest.mark.asyncio
    async def test_generate_token_delegates_to_token_generator(self):
        token_generator = MagicMock()
        token_generator.generate_token = AsyncMock(return_value=_fake_generated_token("sa"))
        provider = ServiceAccountProvider(token_generator)

        result = await provider.generate_token("user@example.com", [])
        token_generator.generate_token.assert_called_once_with("user@example.com")
        assert result.token == "fake-token-sa"

    @pytest.mark.asyncio
    async def test_on_session_establishment_calls_ensure_service_account(self):
        token_generator = MagicMock()
        token_generator.ensure_service_account = AsyncMock(return_value="sa@proj.iam.gserviceaccount.com")
        provider = ServiceAccountProvider(token_generator)

        await provider.on_session_establishment("user@example.com")
        token_generator.ensure_service_account.assert_called_once_with("user@example.com")

    @pytest.mark.asyncio
    async def test_on_google_auth_callback_is_noop(self):
        provider = ServiceAccountProvider(MagicMock())
        # Should not raise
        await provider.on_google_auth_callback("user@example.com", MagicMock())

    @pytest.mark.asyncio
    async def test_on_logout_is_noop(self):
        provider = ServiceAccountProvider(MagicMock())
        await provider.on_logout("user@example.com")

    def test_kind_is_bearer_sa(self):
        provider = ServiceAccountProvider(MagicMock())
        assert provider.kind == "bearer_sa"

    def test_needs_refresh_token_is_false(self):
        provider = ServiceAccountProvider(MagicMock())
        assert provider.needs_refresh_token is False


# ---------------------------------------------------------------------------
# DWDProvider
# ---------------------------------------------------------------------------


class TestDWDProvider:
    @pytest.mark.asyncio
    async def test_generate_token_calls_generate_delegated_token(self):
        token_generator = MagicMock()
        token_generator.generate_delegated_token = AsyncMock(return_value=_fake_generated_token("dwd"))
        provider = DWDProvider(token_generator)

        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        result = await provider.generate_token("user@example.com", scopes)
        token_generator.generate_delegated_token.assert_called_once_with("user@example.com", scopes)
        assert result.token == "fake-token-dwd"

    @pytest.mark.asyncio
    async def test_on_session_establishment_provisions_service_account(self):
        token_generator = MagicMock()
        token_generator.ensure_service_account = AsyncMock(return_value="sa@proj.iam.gserviceaccount.com")
        provider = DWDProvider(token_generator)

        await provider.on_session_establishment("user@example.com")
        token_generator.ensure_service_account.assert_called_once_with("user@example.com")

    def test_kind_is_bearer_dwd(self):
        provider = DWDProvider(MagicMock())
        assert provider.kind == "bearer_dwd"


# ---------------------------------------------------------------------------
# OAuthRefreshProvider
# ---------------------------------------------------------------------------


class TestOAuthRefreshProvider:
    def test_kind_is_bearer_oauth(self):
        provider = OAuthRefreshProvider(MagicMock(), FakeDatabase(), _make_encryptor())
        assert provider.kind == "bearer_oauth"

    def test_needs_refresh_token_is_true(self):
        provider = OAuthRefreshProvider(MagicMock(), FakeDatabase(), _make_encryptor())
        assert provider.needs_refresh_token is True

    @pytest.mark.asyncio
    async def test_generate_token_calls_generate_oauth_token(self):
        token_generator = MagicMock()
        token_generator.generate_oauth_token = AsyncMock(return_value=_fake_generated_token("oauth"))
        encryptor = _make_encryptor()
        provider = OAuthRefreshProvider(token_generator, FakeDatabase(), encryptor)

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        encrypted = encryptor.encrypt("my-refresh-token")
        result = await provider.generate_token("user@example.com", scopes, encrypted)

        token_generator.generate_oauth_token.assert_called_once_with("user@example.com", encrypted, scopes)
        assert result.token == "fake-token-oauth"

    @pytest.mark.asyncio
    async def test_on_google_auth_callback_stores_refresh_token(self):
        db = FakeDatabase()
        encryptor = _make_encryptor()
        provider = OAuthRefreshProvider(MagicMock(), db, encryptor)

        fake_creds = MagicMock()
        fake_creds.refresh_token = "the-refresh-token"
        fake_creds.scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        await provider.on_google_auth_callback("user@example.com", fake_creds)

        assert await db.has_refresh_token("user@example.com")
        stored_encrypted = await db.get_encrypted_refresh_token("user@example.com")
        assert stored_encrypted is not None
        # Verify it decrypts to the original token
        assert encryptor.decrypt(stored_encrypted) == "the-refresh-token"

    @pytest.mark.asyncio
    async def test_on_google_auth_callback_no_refresh_token_is_warning(self):
        db = FakeDatabase()
        provider = OAuthRefreshProvider(MagicMock(), db, _make_encryptor())

        fake_creds = MagicMock()
        fake_creds.refresh_token = None

        # Should NOT raise even when refresh_token is absent
        await provider.on_google_auth_callback("user@example.com", fake_creds)
        assert not await db.has_refresh_token("user@example.com")

    @pytest.mark.asyncio
    async def test_on_logout_revokes_and_deletes(self):
        db = FakeDatabase()
        encryptor = _make_encryptor()
        provider = OAuthRefreshProvider(MagicMock(), db, encryptor)

        # Pre-store a token
        encrypted = encryptor.encrypt("refresh-token-to-revoke")
        await db.set_refresh_token("user@example.com", encrypted, "https://www.googleapis.com/auth/spreadsheets")

        with patch("extrasuite.server.credential_provider._revoke_token_at_google") as mock_revoke:
            await provider.on_logout("user@example.com")
            mock_revoke.assert_called_once_with("refresh-token-to-revoke")

        assert not await db.has_refresh_token("user@example.com")

    @pytest.mark.asyncio
    async def test_on_logout_no_token_is_noop(self):
        db = FakeDatabase()
        provider = OAuthRefreshProvider(MagicMock(), db, _make_encryptor())

        # No token stored — should not raise
        with patch("extrasuite.server.credential_provider._revoke_token_at_google") as mock_revoke:
            await provider.on_logout("user@example.com")
            mock_revoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_logout_google_revoke_failure_still_deletes_from_firestore(self):
        """Network error during revocation should not block Firestore deletion."""
        db = FakeDatabase()
        encryptor = _make_encryptor()
        provider = OAuthRefreshProvider(MagicMock(), db, encryptor)

        encrypted = encryptor.encrypt("some-refresh-token")
        await db.set_refresh_token("user@example.com", encrypted, "")

        with patch(
            "extrasuite.server.credential_provider._revoke_token_at_google",
            side_effect=Exception("network error"),
        ):
            # Should not raise — we log the error and continue
            await provider.on_logout("user@example.com")

        # Token should still be deleted from Firestore
        assert not await db.has_refresh_token("user@example.com")

    @pytest.mark.asyncio
    async def test_on_session_establishment_is_noop(self):
        provider = OAuthRefreshProvider(MagicMock(), FakeDatabase(), _make_encryptor())
        # Should not raise and should not call anything on token_generator
        await provider.on_session_establishment("user@example.com")
