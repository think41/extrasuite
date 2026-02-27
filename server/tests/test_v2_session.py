"""Tests for v2 session-token auth protocol — database and scope-allowlist logic."""

import hashlib

import pytest

from extrasuite.server.api import _DWD_SCOPES
from tests.fakes import FakeDatabase, FakeSettings


class TestFakeDatabaseSessionTokens:
    """Tests for session token operations in FakeDatabase."""

    @pytest.fixture
    def db(self) -> FakeDatabase:
        return FakeDatabase()

    def _make_hash(self, raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_save_and_validate_session_token(self, db: FakeDatabase) -> None:
        """Saved session token can be validated immediately."""
        raw = "my-raw-token"
        token_hash = self._make_hash(raw)
        await db.save_session_token(token_hash, email="user@example.com")

        result = await db.validate_session_token(token_hash)
        assert result is not None
        assert result["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_validate_unknown_token_returns_none(self, db: FakeDatabase) -> None:
        """Validating an unknown token hash returns None."""
        result = await db.validate_session_token("not-a-real-hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_revoke_session_token(self, db: FakeDatabase) -> None:
        """Revoked token fails validation."""
        raw = "my-raw-token"
        token_hash = self._make_hash(raw)
        await db.save_session_token(token_hash, email="user@example.com")

        found = await db.revoke_session_token(token_hash)
        assert found is True

        result = await db.validate_session_token(token_hash)
        assert result is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token_returns_false(self, db: FakeDatabase) -> None:
        """Revoking a token that doesn't exist returns False."""
        found = await db.revoke_session_token("nonexistent-hash")
        assert found is False

    @pytest.mark.asyncio
    async def test_revoke_all_session_tokens(self, db: FakeDatabase) -> None:
        """revoke_all_session_tokens revokes all active sessions for email."""
        email = "user@example.com"
        hashes = [self._make_hash(f"token-{i}") for i in range(3)]
        for h in hashes:
            await db.save_session_token(h, email=email)
        # Save one for a different user (should not be revoked)
        await db.save_session_token(self._make_hash("other"), email="other@example.com")

        count = await db.revoke_all_session_tokens(email)
        assert count == 3

        for h in hashes:
            assert await db.validate_session_token(h) is None
        # Other user's token untouched
        assert await db.validate_session_token(self._make_hash("other")) is not None

    @pytest.mark.asyncio
    async def test_list_session_tokens(self, db: FakeDatabase) -> None:
        """list_session_tokens returns only active sessions for the given email."""
        email = "user@example.com"
        h1 = self._make_hash("token-1")
        h2 = self._make_hash("token-2")
        await db.save_session_token(h1, email=email, device_hostname="laptop")
        await db.save_session_token(h2, email=email, device_hostname="desktop")
        await db.revoke_session_token(h2)  # Revoke the second one

        sessions = await db.list_session_tokens(email)
        assert len(sessions) == 1
        assert sessions[0]["device_hostname"] == "laptop"

    @pytest.mark.asyncio
    async def test_log_access_token_request(self, db: FakeDatabase) -> None:
        """log_access_token_request records the access event."""
        await db.log_access_token_request(
            email="user@example.com",
            session_hash_prefix="abc123",
            scope="sheet.pull",
            credential_type="sa",
            reason="Pulling sheet data",
            ip="1.2.3.4",
        )
        assert len(db.access_logs) == 1
        log = db.access_logs[0]
        assert log["email"] == "user@example.com"
        assert log["scope"] == "sheet.pull"
        assert log["reason"] == "Pulling sheet data"


class TestScopeAllowlist:
    """Tests for Settings.is_scope_allowed() and its interaction with v2 DWD scopes."""

    _PREFIX = "https://www.googleapis.com/auth/"

    def test_no_allowlist_permits_any_scope(self) -> None:
        """When delegation_scopes is empty, all scopes are permitted."""
        settings = FakeSettings(delegation_scopes=[])
        assert settings.is_scope_allowed(f"{self._PREFIX}gmail.compose") is True
        assert settings.is_scope_allowed(f"{self._PREFIX}calendar") is True
        assert settings.is_scope_allowed(f"{self._PREFIX}gmail.readonly") is True

    def test_allowlist_restricts_to_configured_scopes(self) -> None:
        """When delegation_scopes is set, only listed scopes are permitted."""
        allowed = [f"{self._PREFIX}gmail.compose", f"{self._PREFIX}calendar"]
        settings = FakeSettings(delegation_scopes=allowed)

        assert settings.is_scope_allowed(f"{self._PREFIX}gmail.compose") is True
        assert settings.is_scope_allowed(f"{self._PREFIX}calendar") is True
        assert settings.is_scope_allowed(f"{self._PREFIX}script.projects") is False
        assert settings.is_scope_allowed(f"{self._PREFIX}gmail.readonly") is False

    def test_dwd_scope_set_matches_claude_md(self) -> None:
        """Verify _DWD_SCOPES in api.py matches the documented allowed scopes in CLAUDE.md."""
        expected = frozenset(
            {
                "calendar",
                "gmail.compose",
                "gmail.readonly",
                "script.projects",
                "script.deployments",
                "contacts.readonly",
                "contacts.other.readonly",
                "drive.file",
            }
        )
        assert expected == _DWD_SCOPES, (
            f"_DWD_SCOPES {_DWD_SCOPES} does not match documented allowed scopes {expected}. "
            "Update either _DWD_SCOPES or CLAUDE.md."
        )


class TestSAAuthCodeRetrieve:
    """Tests that retrieve_auth_code only returns SA codes, not delegation codes."""

    @pytest.fixture
    def db(self) -> FakeDatabase:
        return FakeDatabase()

    @pytest.mark.asyncio
    async def test_sa_auth_code_is_retrievable(self, db: FakeDatabase) -> None:
        """SA auth codes are returned by retrieve_auth_code."""
        await db.save_auth_code(
            "sa-code",
            service_account_email="sa@proj.iam.gserviceaccount.com",
            user_email="user@example.com",
        )
        result = await db.retrieve_auth_code("sa-code")
        assert result is not None
        assert result["service_account_email"] == "sa@proj.iam.gserviceaccount.com"
        assert result["user_email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_delegation_auth_code_is_not_returned_by_retrieve_auth_code(
        self, db: FakeDatabase
    ) -> None:
        """Delegation auth codes must NOT be returned by retrieve_auth_code.

        This enforces that delegation codes cannot be used to obtain 30-day sessions.
        """
        await db.save_delegation_auth_code(
            "deleg-code",
            email="user@example.com",
            scopes=["https://www.googleapis.com/auth/gmail.compose"],
            reason="test",
        )
        result = await db.retrieve_auth_code("deleg-code")
        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_auth_code_is_single_use(self, db: FakeDatabase) -> None:
        """Auth code is consumed on first retrieval."""
        await db.save_auth_code(
            "one-time-code", service_account_email="sa@proj.iam.gserviceaccount.com"
        )
        first = await db.retrieve_auth_code("one-time-code")
        assert first is not None
        second = await db.retrieve_auth_code("one-time-code")
        assert second is None
