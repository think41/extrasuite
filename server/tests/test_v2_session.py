"""Tests for v2 session-token auth protocol — database and scope-allowlist logic."""

import hashlib
import typing

import pytest

from extrasuite.server.command_registry import _ALL_COMMAND_TYPES, _DWD_COMMAND_SCOPES
from extrasuite.server.commands import Command
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
            command_type="sheet.pull",
            command_context={"file_url": "https://docs.google.com/s/1", "file_name": "Budget"},
            reason="Pulling sheet data",
            ip="1.2.3.4",
        )
        assert len(db.access_logs) == 1
        log = db.access_logs[0]
        assert log["email"] == "user@example.com"
        assert log["command_type"] == "sheet.pull"
        assert log["command_context"]["file_url"] == "https://docs.google.com/s/1"
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

    def test_dwd_command_scopes_use_full_urls(self) -> None:
        """Verify all values in _DWD_COMMAND_SCOPES are full Google OAuth scope URLs."""
        prefix = "https://www.googleapis.com/auth/"
        for cmd_type, scopes in _DWD_COMMAND_SCOPES.items():
            assert scopes, f"Command {cmd_type!r} has empty scopes list"
            for scope in scopes:
                assert scope.startswith(prefix), (
                    f"Command {cmd_type!r} scope {scope!r} is not a full URL. "
                    "All scopes in _DWD_COMMAND_SCOPES must be full https://... URLs."
                )


class TestSAAuthCodeRetrieve:
    """Tests for auth-code retrieval used by session establishment."""

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
    async def test_retrieve_auth_code_is_single_use(self, db: FakeDatabase) -> None:
        """Auth code is consumed on first retrieval."""
        await db.save_auth_code(
            "one-time-code",
            service_account_email="sa@proj.iam.gserviceaccount.com",
            user_email="user@example.com",
        )
        first = await db.retrieve_auth_code("one-time-code")
        assert first is not None
        second = await db.retrieve_auth_code("one-time-code")
        assert second is None


class TestCommandRegistrySync:
    """Ensures the Command union and command_registry stay in sync."""

    def test_command_union_matches_registry(self) -> None:
        """Every type literal in the Command union must appear in command_registry,
        and every registry entry must have a corresponding Command class.

        This test prevents the common mistake of adding a new Command class to
        commands.py but forgetting to register it in command_registry.py (or
        vice versa).
        """
        # Extract the type literals from the discriminated union via Pydantic metadata.
        union_args = typing.get_args(typing.get_args(Command)[0])
        union_types: set[str] = set()
        for cls in union_args:
            (literal_type,) = typing.get_args(cls.model_fields["type"].annotation)
            union_types.add(literal_type)

        assert union_types == _ALL_COMMAND_TYPES, (
            f"Mismatch between Command union and command_registry._ALL_COMMAND_TYPES.\n"
            f"  In union but not registry: {union_types - _ALL_COMMAND_TYPES}\n"
            f"  In registry but not union: {_ALL_COMMAND_TYPES - union_types}"
        )
