"""End-to-end tests for v2 session-token auth protocol API endpoints.

Every test hits the real FastAPI route handler via httpx + ASGITransport.
External dependencies are replaced:
- Database  → FakeDatabase (in-memory, no Firestore)
- Settings  → FakeSettings (no env vars required)
- TokenGenerator → unittest.mock.patch (no Google API calls)

The fixtures `client`, `fake_db`, and `fake_settings` come from conftest.py.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from extrasuite.server.command_registry import _DWD_COMMAND_SCOPES, _SA_COMMAND_TYPES
from extrasuite.server.token_generator import GeneratedToken
from tests.conftest import make_test_app
from tests.fakes import FakeDatabase, FakeSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SA_EMAIL = "user-abc@test-project.iam.gserviceaccount.com"
_USER_EMAIL = "user@example.com"
_ADMIN_EMAIL = "admin@example.com"
_FAKE_TOKEN = "fake-access-token-xyz"


def _fake_generated_token(sa_email: str = _SA_EMAIL) -> GeneratedToken:
    return GeneratedToken(
        token=_FAKE_TOKEN,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        service_account_email=sa_email,
    )


async def _make_session(db: FakeDatabase, email: str = _USER_EMAIL, expiry_days: int = 30) -> str:
    """Save a fresh session token in the fake DB and return the raw token."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    await db.save_session_token(token_hash, email=email, expiry_days=expiry_days)
    return raw


def _bearer(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


# ===========================================================================
# POST /api/auth/session/exchange  (Phase 1)
# ===========================================================================


class TestSessionExchange:
    """Tests for POST /api/auth/session/exchange."""

    @pytest.fixture(autouse=True)
    def _patch_token_generator(self):
        """Patch TokenGenerator so ensure_service_account is a no-op."""
        with patch("extrasuite.server.api.TokenGenerator") as MockTG:
            mock_tg = MagicMock()
            mock_tg.ensure_service_account = AsyncMock(return_value=_SA_EMAIL)
            MockTG.return_value = mock_tg
            self._mock_tg = mock_tg
            yield

    async def test_valid_sa_code_returns_session_token(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Happy path: valid SA auth code → 200 with session_token, email, expires_at."""
        await fake_db.save_auth_code("valid-code", _SA_EMAIL, _USER_EMAIL)

        resp = await client.post(
            "/api/auth/session/exchange",
            json={"code": "valid-code", "device_hostname": "laptop"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "session_token" in data
        assert data["email"] == _USER_EMAIL
        assert "expires_at" in data
        # Session must be persisted in DB
        token_hash = hashlib.sha256(data["session_token"].encode()).hexdigest()
        session = await fake_db.validate_session_token(token_hash)
        assert session is not None
        assert session["email"] == _USER_EMAIL

    async def test_invalid_code_returns_400(self, client: httpx.AsyncClient) -> None:
        """Auth code not in DB → 400."""
        resp = await client.post("/api/auth/session/exchange", json={"code": "bad-code"})
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    async def test_disallowed_email_domain_returns_403(self, fake_db: FakeDatabase) -> None:
        """Email domain not in allowlist → 403."""
        restricted_settings = FakeSettings(
            admin_emails=[_ADMIN_EMAIL],
            allowed_domains=["allowed.com"],
        )
        app = make_test_app(fake_db, restricted_settings)

        with patch("extrasuite.server.api.TokenGenerator") as MockTG:
            mock_tg = MagicMock()
            mock_tg.ensure_service_account = AsyncMock(return_value=_SA_EMAIL)
            MockTG.return_value = mock_tg

            await fake_db.save_auth_code("code", _SA_EMAIL, "user@blocked.com")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as restricted_client:
                resp = await restricted_client.post(
                    "/api/auth/session/exchange", json={"code": "code"}
                )
        assert resp.status_code == 403

    async def test_sa_provisioning_failure_returns_500(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """SA creation failure → 500."""
        self._mock_tg.ensure_service_account = AsyncMock(
            side_effect=RuntimeError("IAM quota exceeded")
        )
        await fake_db.save_auth_code("code2", _SA_EMAIL, _USER_EMAIL)

        resp = await client.post("/api/auth/session/exchange", json={"code": "code2"})
        assert resp.status_code == 500

    async def test_missing_user_email_in_auth_code_returns_400(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Auth code with empty user_email → 400 (invariant violation at issuance)."""
        await fake_db.save_auth_code("code3", _SA_EMAIL, user_email="")

        resp = await client.post("/api/auth/session/exchange", json={"code": "code3"})
        assert resp.status_code == 400
        assert "user_email" in resp.json()["detail"]

    async def test_device_fingerprint_stored(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Device info sent in request body is persisted in the session record."""
        await fake_db.save_auth_code("code4", _SA_EMAIL, _USER_EMAIL)

        resp = await client.post(
            "/api/auth/session/exchange",
            json={
                "code": "code4",
                "device_hostname": "myhost",
                "device_os": "Linux",
                "device_mac": "0xaabbcc",
                "device_platform": "Linux-6.1",
            },
        )
        assert resp.status_code == 200
        token_hash = hashlib.sha256(resp.json()["session_token"].encode()).hexdigest()
        record = fake_db.session_tokens[token_hash]
        assert record["device_hostname"] == "myhost"
        assert record["device_os"] == "Linux"

    async def test_auth_code_is_consumed_single_use(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Auth code is deleted after first use; second exchange returns 400."""
        await fake_db.save_auth_code("one-time", _SA_EMAIL, _USER_EMAIL)

        resp1 = await client.post("/api/auth/session/exchange", json={"code": "one-time"})
        assert resp1.status_code == 200

        resp2 = await client.post("/api/auth/session/exchange", json={"code": "one-time"})
        assert resp2.status_code == 400


# ===========================================================================
# POST /api/auth/token  (Phase 2)
# ===========================================================================


class TestAccessToken:
    """Tests for POST /api/auth/token."""

    @pytest.fixture(autouse=True)
    def _patch_token_generator(self):
        with patch("extrasuite.server.api.TokenGenerator") as MockTG:
            mock_tg = MagicMock()
            mock_tg.generate_token = AsyncMock(return_value=_fake_generated_token())
            mock_tg.generate_delegated_token = AsyncMock(return_value=_fake_generated_token())
            MockTG.return_value = mock_tg
            self._mock_tg = mock_tg
            yield

    async def test_sa_command_returns_credentials(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Valid session + SA command → 200 with credentials list."""
        raw = await _make_session(fake_db)
        fake_db.users[_USER_EMAIL] = _SA_EMAIL

        resp = await client.post(
            "/api/auth/token",
            json={
                "command": {"type": "sheet.pull", "file_url": "https://docs.google.com/s/1"},
                "reason": "pulling a sheet",
            },
            headers=_bearer(raw),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["command_type"] == "sheet.pull"
        assert len(data["credentials"]) == 1
        cred = data["credentials"][0]
        assert cred["token"] == _FAKE_TOKEN
        assert cred["kind"] == "bearer_sa"
        assert cred["metadata"]["service_account_email"] == _SA_EMAIL
        self._mock_tg.generate_token.assert_awaited_once_with(_USER_EMAIL)

    async def test_dwd_command_returns_credentials(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Valid session + DWD command → 200; generate_delegated_token called."""
        raw = await _make_session(fake_db)
        fake_db.users[_USER_EMAIL] = _SA_EMAIL

        resp = await client.post(
            "/api/auth/token",
            json={
                "command": {
                    "type": "gmail.compose",
                    "subject": "Hello",
                    "recipients": [],
                    "cc": [],
                },
                "reason": "sending an email",
            },
            headers=_bearer(raw),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["command_type"] == "gmail.compose"
        cred = data["credentials"][0]
        assert cred["kind"] == "bearer_dwd"
        self._mock_tg.generate_delegated_token.assert_awaited_once()
        call_args = self._mock_tg.generate_delegated_token.call_args
        assert call_args.args[0] == _USER_EMAIL
        assert "https://www.googleapis.com/auth/gmail.compose" in call_args.args[1]

    async def test_access_request_is_logged(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Each access token request is logged to access_logs."""
        raw = await _make_session(fake_db)

        await client.post(
            "/api/auth/token",
            json={
                "command": {
                    "type": "sheet.pull",
                    "file_url": "https://docs.google.com/s/1",
                    "file_name": "Budget",
                },
                "reason": "audit test",
            },
            headers=_bearer(raw),
        )

        assert len(fake_db.access_logs) == 1
        log = fake_db.access_logs[0]
        assert log["email"] == _USER_EMAIL
        assert log["command_type"] == "sheet.pull"
        assert log["command_context"]["file_url"] == "https://docs.google.com/s/1"
        assert log["reason"] == "audit test"

    async def test_missing_authorization_header_returns_401(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/auth/token",
            json={"command": {"type": "sheet.pull"}, "reason": "test"},
        )
        assert resp.status_code == 401

    async def test_non_bearer_auth_header_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/auth/token",
            json={"command": {"type": "sheet.pull"}, "reason": "test"},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401

    async def test_invalid_session_token_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/auth/token",
            json={"command": {"type": "sheet.pull"}, "reason": "test"},
            headers=_bearer("not-a-real-token"),
        )
        assert resp.status_code == 401
        assert "Session expired" in resp.json()["detail"]

    async def test_revoked_session_returns_401(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        raw = await _make_session(fake_db)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        await fake_db.revoke_session_token(token_hash)

        resp = await client.post(
            "/api/auth/token",
            json={"command": {"type": "sheet.pull"}, "reason": "test"},
            headers=_bearer(raw),
        )
        assert resp.status_code == 401

    async def test_unknown_command_type_returns_400(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        raw = await _make_session(fake_db)

        # Pydantic discriminated union validation: unknown type → 422 (unprocessable entity)
        resp = await client.post(
            "/api/auth/token",
            json={"command": {"type": "not.a.real.command"}, "reason": "test"},
            headers=_bearer(raw),
        )
        assert resp.status_code == 422

    async def test_dwd_command_blocked_by_allowlist_returns_403(
        self, fake_db: FakeDatabase
    ) -> None:
        """DWD command whose required scope is not in DELEGATION_SCOPES allowlist → 403."""
        restricted_settings = FakeSettings(
            admin_emails=[_ADMIN_EMAIL],
            # Only allow calendar; gmail.compose is blocked
            delegation_scopes=["https://www.googleapis.com/auth/calendar"],
        )
        app = make_test_app(fake_db, restricted_settings)

        with patch("extrasuite.server.api.TokenGenerator") as MockTG:
            mock_tg = MagicMock()
            mock_tg.generate_delegated_token = AsyncMock(return_value=_fake_generated_token())
            MockTG.return_value = mock_tg

            raw = await _make_session(fake_db)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as restricted_client:
                resp = await restricted_client.post(
                    "/api/auth/token",
                    json={
                        "command": {
                            "type": "gmail.compose",
                            "subject": "",
                            "recipients": [],
                            "cc": [],
                        },
                        "reason": "test",
                    },
                    headers=_bearer(raw),
                )
        assert resp.status_code == 403
        assert "gmail.compose" in resp.json()["detail"]

    async def test_all_sa_commands_accepted(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Every SA command type registered in command_registry is accepted.

        Driven from _SA_COMMAND_TYPES so new commands automatically get coverage.
        All Command fields have defaults, so {"type": cmd_type} is a valid payload.
        """
        raw = await _make_session(fake_db)
        for cmd_type in sorted(_SA_COMMAND_TYPES):
            resp = await client.post(
                "/api/auth/token",
                json={"command": {"type": cmd_type}, "reason": "coverage test"},
                headers=_bearer(raw),
            )
            assert resp.status_code == 200, f"SA command {cmd_type!r} unexpectedly rejected"

    async def test_all_dwd_commands_accepted(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Every DWD command type registered in command_registry is accepted.

        Driven from _DWD_COMMAND_SCOPES so new commands automatically get coverage.
        All Command fields have defaults, so {"type": cmd_type} is a valid payload.
        """
        raw = await _make_session(fake_db)
        for cmd_type in sorted(_DWD_COMMAND_SCOPES):
            resp = await client.post(
                "/api/auth/token",
                json={"command": {"type": cmd_type}, "reason": "coverage test"},
                headers=_bearer(raw),
            )
            assert resp.status_code == 200, f"DWD command {cmd_type!r} unexpectedly rejected"

    async def test_multi_scope_dwd_command_passes_all_scopes(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """gmail.reply requires two scopes; both must be passed to generate_delegated_token."""
        raw = await _make_session(fake_db)
        fake_db.users[_USER_EMAIL] = _SA_EMAIL

        resp = await client.post(
            "/api/auth/token",
            json={
                "command": {
                    "type": "gmail.reply",
                    "thread_id": "t123",
                    "thread_subject": "Re: Hello",
                    "recipients": ["alice@example.com"],
                    "cc": [],
                },
                "reason": "replying to a thread",
            },
            headers=_bearer(raw),
        )

        assert resp.status_code == 200
        cred = resp.json()["credentials"][0]
        assert cred["kind"] == "bearer_dwd"
        # Both scopes required for gmail.reply must be granted
        assert set(cred["scopes"]) == {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        }
        call_args = self._mock_tg.generate_delegated_token.call_args
        passed_scopes = set(call_args.args[1])
        assert passed_scopes == {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        }


# ===========================================================================
# GET /api/admin/sessions
# ===========================================================================


class TestListSessions:
    """Tests for GET /api/admin/sessions."""

    async def test_owner_sees_own_sessions_with_full_hash(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """User can list their own sessions; full session_hash is returned."""
        raw = await _make_session(fake_db, email=_USER_EMAIL)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()

        resp = await client.get(
            "/api/admin/sessions",
            params={"email": _USER_EMAIL},
            headers=_bearer(raw),
        )

        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["session_hash"] == token_hash

    async def test_admin_sees_other_user_sessions_with_hash_redacted(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Admin listing another user's sessions gets session_hash redacted."""
        # Create a session for the regular user
        await _make_session(fake_db, email=_USER_EMAIL)
        # Admin logs in with their own session
        admin_raw = await _make_session(fake_db, email=_ADMIN_EMAIL)

        resp = await client.get(
            "/api/admin/sessions",
            params={"email": _USER_EMAIL},
            headers=_bearer(admin_raw),
        )

        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        # session_hash must be redacted for non-owner admin view
        assert "session_hash" not in sessions[0]

    async def test_non_admin_cannot_list_other_user_sessions(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Non-admin user trying to list another user's sessions → 403."""
        await _make_session(fake_db, email=_USER_EMAIL)
        other_raw = await _make_session(fake_db, email="other@example.com")

        resp = await client.get(
            "/api/admin/sessions",
            params={"email": _USER_EMAIL},
            headers=_bearer(other_raw),
        )
        assert resp.status_code == 403

    async def test_unauthenticated_request_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/admin/sessions", params={"email": _USER_EMAIL})
        assert resp.status_code == 401

    async def test_revoked_session_cannot_authenticate(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """A revoked session token cannot be used for subsequent requests."""
        raw = await _make_session(fake_db)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        await fake_db.revoke_session_token(token_hash)

        resp = await client.get(
            "/api/admin/sessions",
            params={"email": _USER_EMAIL},
            headers=_bearer(raw),
        )
        assert resp.status_code == 401

    async def test_multiple_sessions_all_returned(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """All active sessions for the user are returned."""
        raw1 = await _make_session(fake_db)
        await _make_session(fake_db)  # second session, same user

        resp = await client.get(
            "/api/admin/sessions",
            params={"email": _USER_EMAIL},
            headers=_bearer(raw1),
        )
        assert resp.status_code == 200
        # two sessions for _USER_EMAIL
        assert len(resp.json()) == 2


# ===========================================================================
# DELETE /api/admin/sessions/{hash}
# ===========================================================================


class TestRevokeSession:
    """Tests for DELETE /api/admin/sessions/{session_hash}."""

    async def test_owner_can_revoke_own_session(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """User can revoke their own session → 204."""
        # Two sessions: one to authenticate with, one to revoke
        auth_raw = await _make_session(fake_db)
        target_raw = await _make_session(fake_db)
        target_hash = hashlib.sha256(target_raw.encode()).hexdigest()

        resp = await client.delete(
            f"/api/admin/sessions/{target_hash}",
            headers=_bearer(auth_raw),
        )
        assert resp.status_code == 204

        # Verify revoked in DB
        assert await fake_db.validate_session_token(target_hash) is None

    async def test_admin_can_revoke_any_session(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Admin can revoke another user's session → 204."""
        target_raw = await _make_session(fake_db, email=_USER_EMAIL)
        target_hash = hashlib.sha256(target_raw.encode()).hexdigest()
        admin_raw = await _make_session(fake_db, email=_ADMIN_EMAIL)

        resp = await client.delete(
            f"/api/admin/sessions/{target_hash}",
            headers=_bearer(admin_raw),
        )
        assert resp.status_code == 204
        assert await fake_db.validate_session_token(target_hash) is None

    async def test_non_admin_cannot_revoke_other_users_session(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Non-admin trying to revoke another user's session → 403."""
        target_raw = await _make_session(fake_db, email=_USER_EMAIL)
        target_hash = hashlib.sha256(target_raw.encode()).hexdigest()
        other_raw = await _make_session(fake_db, email="other@example.com")

        resp = await client.delete(
            f"/api/admin/sessions/{target_hash}",
            headers=_bearer(other_raw),
        )
        assert resp.status_code == 403
        # Target session must still be active
        assert await fake_db.validate_session_token(target_hash) is not None

    async def test_admin_revoke_nonexistent_session_returns_404(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Admin revoking a non-existent session hash → 404."""
        admin_raw = await _make_session(fake_db, email=_ADMIN_EMAIL)
        fake_hash = "a" * 64  # valid hex length, but not in DB

        resp = await client.delete(
            f"/api/admin/sessions/{fake_hash}",
            headers=_bearer(admin_raw),
        )
        assert resp.status_code == 404

    async def test_non_admin_revoke_nonexistent_session_returns_403(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Non-admin revoking a non-existent session → 403 (not 404, to avoid enumeration)."""
        user_raw = await _make_session(fake_db, email=_USER_EMAIL)
        fake_hash = "b" * 64

        resp = await client.delete(
            f"/api/admin/sessions/{fake_hash}",
            headers=_bearer(user_raw),
        )
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete(f"/api/admin/sessions/{'c' * 64}")
        assert resp.status_code == 401


# ===========================================================================
# POST /api/admin/sessions/revoke-all
# ===========================================================================


class TestRevokeAllSessions:
    """Tests for POST /api/admin/sessions/revoke-all."""

    async def test_owner_can_revoke_all_own_sessions(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """User can revoke all their own sessions → 200 with revoked_count."""
        raw1 = await _make_session(fake_db)
        raw2 = await _make_session(fake_db)
        # Use a third session to call revoke-all so we can verify all are gone
        auth_raw = await _make_session(fake_db)

        resp = await client.post(
            "/api/admin/sessions/revoke-all",
            params={"email": _USER_EMAIL},
            headers=_bearer(auth_raw),
        )
        assert resp.status_code == 200
        # All 3 sessions belong to _USER_EMAIL
        assert resp.json()["revoked_count"] == 3

        for raw in (raw1, raw2, auth_raw):
            h = hashlib.sha256(raw.encode()).hexdigest()
            assert await fake_db.validate_session_token(h) is None

    async def test_admin_can_revoke_all_for_any_user(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Admin can revoke all sessions for another user."""
        await _make_session(fake_db, email=_USER_EMAIL)
        await _make_session(fake_db, email=_USER_EMAIL)
        admin_raw = await _make_session(fake_db, email=_ADMIN_EMAIL)

        resp = await client.post(
            "/api/admin/sessions/revoke-all",
            params={"email": _USER_EMAIL},
            headers=_bearer(admin_raw),
        )
        assert resp.status_code == 200
        assert resp.json()["revoked_count"] == 2

    async def test_non_admin_cannot_revoke_all_for_other_user(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Non-admin user trying to revoke-all for another user → 403."""
        await _make_session(fake_db, email=_USER_EMAIL)
        other_raw = await _make_session(fake_db, email="other@example.com")

        resp = await client.post(
            "/api/admin/sessions/revoke-all",
            params={"email": _USER_EMAIL},
            headers=_bearer(other_raw),
        )
        assert resp.status_code == 403

    async def test_revoke_all_returns_zero_when_no_sessions(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Revoking all sessions for a user with no sessions returns count 0."""
        admin_raw = await _make_session(fake_db, email=_ADMIN_EMAIL)

        resp = await client.post(
            "/api/admin/sessions/revoke-all",
            params={"email": "no-sessions@example.com"},
            headers=_bearer(admin_raw),
        )
        assert resp.status_code == 200
        assert resp.json()["revoked_count"] == 0

    async def test_unauthenticated_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/admin/sessions/revoke-all", params={"email": _USER_EMAIL})
        assert resp.status_code == 401


# ===========================================================================
# Cross-cutting: session token security properties
# ===========================================================================


class TestSessionTokenSecurity:
    """Verify security invariants that span multiple endpoints."""

    async def test_session_token_stored_as_hash_not_raw(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """The raw session token must never appear as a Firestore document ID."""
        with patch("extrasuite.server.api.TokenGenerator") as MockTG:
            mock_tg = MagicMock()
            mock_tg.ensure_service_account = AsyncMock(return_value=_SA_EMAIL)
            MockTG.return_value = mock_tg

            await fake_db.save_auth_code("raw-check-code", _SA_EMAIL, _USER_EMAIL)
            resp = await client.post("/api/auth/session/exchange", json={"code": "raw-check-code"})

        assert resp.status_code == 200
        raw_token = resp.json()["session_token"]
        # The raw token must NOT be a key in session_tokens (only the hash should be)
        assert raw_token not in fake_db.session_tokens
        # But the hash must be present
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert expected_hash in fake_db.session_tokens

    async def test_case_insensitive_admin_check(
        self, client: httpx.AsyncClient, fake_db: FakeDatabase
    ) -> None:
        """Admin email matching is case-insensitive.

        FakeSettings has admin_emails=["admin@example.com"] (lowercase, from conftest).
        We log in with "Admin@Example.Com" (mixed case) — it must be recognized as admin.
        """
        # Create a session for the regular user (to be listed)
        await _make_session(fake_db, email=_USER_EMAIL)
        # Create an admin session with mixed-case email
        admin_raw = await _make_session(fake_db, email="Admin@Example.Com")

        resp = await client.get(
            "/api/admin/sessions",
            params={"email": _USER_EMAIL},
            headers=_bearer(admin_raw),
        )
        # Admin@Example.Com matches admin@example.com → admin access granted
        assert resp.status_code == 200
        # session_hash should be redacted (admin viewing other user's sessions)
        sessions = resp.json()
        assert len(sessions) == 1
        assert "session_hash" not in sessions[0]
