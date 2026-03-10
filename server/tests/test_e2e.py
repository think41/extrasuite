"""End-to-end tests for the full ExtraSuite server auth flows.

All three gaps are covered here:
  Gap 1 — Real CommandCredentialRouter + FakeTokenGenerator (not a mock)
  Gap 2 — FakeGoogleAuthGateway exercises the full OAuth callback path
  Gap 3 — FakeRevokeFn exercises token revocation without hitting Google

Every test hits real FastAPI route handlers via httpx ASGITransport. The only
faked boundaries are:
  - FakeDatabase       (in-memory Firestore)
  - FakeSettings       (no env vars required)
  - FakeTokenGenerator (no Google IAM / impersonation API calls)
  - FakeGoogleAuthGateway (no Google OAuth / ID token calls)
  - FakeRevokeFn       (no Google token revocation call)
"""

import hashlib
import secrets
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.conftest import make_e2e_test_app
from tests.fakes import (
    FakeDatabase,
    FakeGoogleAuthGateway,
    FakeRevokeFn,
    FakeSettings,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_USER_EMAIL = "user@example.com"
_ADMIN_EMAIL = "admin@example.com"
_FAKE_ENCRYPTION_KEY = secrets.token_hex(32)  # valid 32-byte hex key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_encryptor():
    from extrasuite.server.crypto import RefreshTokenEncryptor

    return RefreshTokenEncryptor(_FAKE_ENCRYPTION_KEY)


async def _inject_session(db: FakeDatabase, email: str = _USER_EMAIL) -> str:
    """Bypass Phase 1 and inject a session token directly into the DB."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    await db.save_session_token(token_hash, email=email)
    return raw


async def _do_oauth_callback(
    client: httpx.AsyncClient,
    db: FakeDatabase,
    port: int = 8080,
) -> str:
    """Simulate the Phase 1 browser flow. Returns the auth_code for session exchange.

    Steps:
    1. GET /api/token/auth?port={port}  → saves state, redirects to fake Google
    2. GET /api/auth/callback?code=...&state=...  → verifies, sets session, redirects to CLI
    3. Extract auth_code from the CLI redirect URL
    """
    # Step 1: Start auth flow
    resp = await client.get(
        "/api/token/auth",
        params={"port": port},
        follow_redirects=False,
    )
    assert resp.is_redirect, f"Expected redirect, got {resp.status_code}: {resp.text}"

    # State is saved in DB; extract it (simulates Google echoing it back)
    assert len(db.oauth_states) == 1, "Expected exactly one oauth_state in DB"
    state = list(db.oauth_states.keys())[0]

    # Step 2: Simulate Google's callback
    resp = await client.get(
        "/api/auth/callback",
        params={"code": "fake-google-auth-code", "state": state},
        follow_redirects=False,
    )
    assert resp.is_redirect, f"Expected redirect from callback, got {resp.status_code}"

    # Step 3: Extract auth code from the CLI redirect URL
    location = resp.headers["location"]
    auth_code = parse_qs(urlparse(location).query).get("code", [None])[0]
    assert auth_code is not None, f"No auth code in CLI redirect: {location}"
    return auth_code


async def _exchange_session(client: httpx.AsyncClient, auth_code: str) -> str:
    """Exchange auth_code for a 30-day session token. Returns the raw token."""
    resp = await client.post(
        "/api/auth/session/exchange",
        json={"code": auth_code, "device_hostname": "test-host"},
    )
    assert resp.status_code == 200, f"Session exchange failed: {resp.text}"
    return resp.json()["session_token"]


async def _get_credential(
    client: httpx.AsyncClient,
    session_token: str,
    command: dict,
    reason: str = "e2e test",
) -> dict:
    """Request credentials for a command. Asserts 200 and returns response JSON."""
    resp = await client.post(
        "/api/auth/token",
        json={"command": command, "reason": reason},
        headers=_bearer(session_token),
    )
    assert resp.status_code == 200, f"Token request failed: {resp.text}"
    return resp.json()


# ===========================================================================
# Gap 2 — OAuth callback flow (GET /api/token/auth + GET /api/auth/callback)
# ===========================================================================


class TestOAuthCallbackFlow:
    """Tests for the browser-based Phase 1 OAuth callback endpoints."""

    @pytest.fixture
    def db(self) -> FakeDatabase:
        return FakeDatabase()

    @pytest.fixture
    def settings(self) -> FakeSettings:
        return FakeSettings(credential_mode="sa+dwd")

    @pytest.fixture
    async def client(self, db: FakeDatabase, settings: FakeSettings) -> AsyncGenerator:
        app = make_e2e_test_app(db, settings)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    async def test_start_auth_redirects_to_google(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """GET /api/token/auth?port=N redirects to the (fake) Google OAuth URL."""
        resp = await client.get(
            "/api/token/auth", params={"port": 8080}, follow_redirects=False
        )

        assert resp.is_redirect
        assert "fake-accounts.google.com" in resp.headers["location"]

    async def test_start_auth_saves_state_in_db(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """State token is saved to DB so the callback can verify it."""
        await client.get("/api/token/auth", params={"port": 8080}, follow_redirects=False)

        assert len(db.oauth_states) == 1
        state_data = list(db.oauth_states.values())[0]
        assert state_data["redirect_url"] == "http://localhost:8080/on-authentication"

    async def test_start_auth_state_embedded_in_redirect_url(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """The redirect URL contains the state that was saved in the DB."""
        resp = await client.get(
            "/api/token/auth", params={"port": 8080}, follow_redirects=False
        )
        location = resp.headers["location"]
        state_in_url = parse_qs(urlparse(location).query).get("state", [None])[0]

        assert state_in_url is not None
        assert state_in_url in db.oauth_states

    async def test_callback_redirects_to_cli_with_auth_code(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """Valid callback produces a CLI redirect containing an auth_code."""
        auth_code = await _do_oauth_callback(client, db)

        # Auth code was stored in DB
        assert auth_code in db.auth_codes
        assert db.auth_codes[auth_code]["user_email"] == _USER_EMAIL

    async def test_callback_invalid_state_returns_html_error(
        self, client: httpx.AsyncClient
    ) -> None:
        """Callback with unknown state returns 400 HTML (no CLI redirect to redirect to)."""
        resp = await client.get(
            "/api/auth/callback",
            params={"code": "some-code", "state": "invalid-state-not-in-db"},
            follow_redirects=False,
        )
        assert resp.status_code == 400

    async def test_callback_invalid_state_consumes_no_auth_code(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """No auth_code is stored when the callback fails due to invalid state."""
        await client.get(
            "/api/auth/callback",
            params={"code": "some-code", "state": "invalid"},
            follow_redirects=False,
        )
        assert len(db.auth_codes) == 0

    async def test_callback_fetch_token_failure_redirects_to_cli_error(
        self, db: FakeDatabase, settings: FakeSettings
    ) -> None:
        """If fetch_token raises OAuth2Error, callback redirects to CLI with error."""
        gateway = FakeGoogleAuthGateway(user_email=_USER_EMAIL, fetch_token_fails=True)
        app = make_e2e_test_app(db, settings, auth_gateway=gateway)

        await db.save_state("test-state", "http://localhost:8080/on-authentication")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(
                "/api/auth/callback",
                params={"code": "bad-code", "state": "test-state"},
                follow_redirects=False,
            )

        assert resp.is_redirect
        assert "error" in resp.headers["location"]

    async def test_callback_id_token_failure_redirects_to_cli_error(
        self, db: FakeDatabase, settings: FakeSettings
    ) -> None:
        """If ID token verification fails, callback redirects to CLI with error."""
        gateway = FakeGoogleAuthGateway(user_email=_USER_EMAIL, id_token_fails=True)
        app = make_e2e_test_app(db, settings, auth_gateway=gateway)

        await db.save_state("test-state", "http://localhost:8080/on-authentication")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(
                "/api/auth/callback",
                params={"code": "ok-code", "state": "test-state"},
                follow_redirects=False,
            )

        assert resp.is_redirect
        assert "error" in resp.headers["location"]

    async def test_callback_blocked_domain_redirects_to_cli_error(
        self, db: FakeDatabase
    ) -> None:
        """Callback for a blocked email domain redirects to CLI with error."""
        restricted = FakeSettings(
            credential_mode="sa+dwd",
            allowed_domains=["allowed.com"],
        )
        gateway = FakeGoogleAuthGateway(user_email="user@blocked.com")
        app = make_e2e_test_app(db, restricted, auth_gateway=gateway)

        await db.save_state("test-state", "http://localhost:8080/on-authentication")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(
                "/api/auth/callback",
                params={"code": "ok-code", "state": "test-state"},
                follow_redirects=False,
            )

        assert resp.is_redirect
        assert "error" in resp.headers["location"]

    async def test_headless_callback_shows_auth_code_in_html(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """Without port= (headless), auth_code is displayed in an HTML page."""
        # Start headless flow (no port= param)
        resp = await client.get("/api/token/auth", follow_redirects=False)
        assert resp.is_redirect

        state = list(db.oauth_states.keys())[0]

        resp = await client.get(
            "/api/auth/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )

        # Headless returns 200 HTML with the auth code embedded
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        # One auth_code was created
        assert len(db.auth_codes) == 1


# ===========================================================================
# Gap 1 — sa+dwd mode: real routing table + FakeTokenGenerator
# ===========================================================================


class TestE2ESaDwdMode:
    """End-to-end tests for CREDENTIAL_MODE=sa+dwd (the default)."""

    @pytest.fixture
    def db(self) -> FakeDatabase:
        return FakeDatabase()

    @pytest.fixture
    def settings(self) -> FakeSettings:
        return FakeSettings(credential_mode="sa+dwd")

    @pytest.fixture
    async def client(self, db: FakeDatabase, settings: FakeSettings) -> AsyncGenerator:
        app = make_e2e_test_app(db, settings)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    async def test_session_exchange_provisions_service_account(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """Phase 1 exchange provisions a SA and stores it in DB before issuing session."""
        assert len(db.users) == 0

        auth_code = await _do_oauth_callback(client, db)
        await _exchange_session(client, auth_code)

        assert len(db.users) == 1
        sa_email = list(db.users.values())[0]
        assert sa_email.endswith("@test-project.iam.gserviceaccount.com")
        assert sa_email.startswith("user-")  # derived from user@example.com

    async def test_sa_command_returns_bearer_sa_credential(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """sheet.pull → bearer_sa credential with SA email in metadata."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        data = await _get_credential(
            client,
            session,
            {"type": "sheet.pull", "file_url": "https://docs.google.com/s/1"},
        )

        assert data["command_type"] == "sheet.pull"
        cred = data["credentials"][0]
        assert cred["kind"] == "bearer_sa"
        assert cred["token"] == "fake-sa-token"
        assert "service_account_email" in cred["metadata"]
        assert cred["metadata"]["service_account_email"] == db.users[_USER_EMAIL]

    async def test_dwd_command_returns_bearer_dwd_credential(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """gmail.compose → bearer_dwd credential with correct scope."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        data = await _get_credential(
            client,
            session,
            {"type": "gmail.compose", "subject": "Hello", "recipients": [], "cc": []},
        )

        cred = data["credentials"][0]
        assert cred["kind"] == "bearer_dwd"
        assert cred["token"] == "fake-dwd-token"
        assert "https://www.googleapis.com/auth/gmail.compose" in cred["scopes"]

    async def test_access_request_is_logged_with_full_context(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """Access log entry includes email, command type, context fields, and reason."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        await _get_credential(
            client,
            session,
            {
                "type": "sheet.pull",
                "file_url": "https://docs.google.com/s/1",
                "file_name": "Budget",
            },
            reason="reviewing the Q4 budget",
        )

        assert len(db.access_logs) == 1
        log = db.access_logs[0]
        assert log["email"] == _USER_EMAIL
        assert log["command_type"] == "sheet.pull"
        assert log["reason"] == "reviewing the Q4 budget"
        assert log["command_context"]["file_url"] == "https://docs.google.com/s/1"
        assert log["credential_kind"] == "bearer_sa"

    async def test_dwd_token_fails_when_sa_not_in_db(
        self, db: FakeDatabase, settings: FakeSettings
    ) -> None:
        """DWD credential request returns 500 if SA was never provisioned (invariant violation).

        Uses raise_app_exceptions=False so the unhandled_exception_handler's 500 response
        is received rather than the re-raised exception propagating to the test.
        """
        app = make_e2e_test_app(db, settings)

        # Inject a session directly — skips Phase 1, so no SA is provisioned
        raw = await _inject_session(db, email="orphan@example.com")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as c:
            resp = await c.post(
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

        assert resp.status_code == 500

    async def test_scope_allowlist_blocks_restricted_dwd_command(
        self, db: FakeDatabase
    ) -> None:
        """DWD command whose scope is not in DELEGATION_SCOPES returns 403."""
        restricted = FakeSettings(
            credential_mode="sa+dwd",
            # Only calendar is allowed; gmail.compose is blocked
            delegation_scopes=["https://www.googleapis.com/auth/calendar"],
        )
        app = make_e2e_test_app(db, restricted)

        await db.save_auth_code("blocked-code", "", _USER_EMAIL)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            session = await _exchange_session(c, "blocked-code")
            resp = await c.post(
                "/api/auth/token",
                json={
                    "command": {
                        "type": "gmail.compose",
                        "subject": "",
                        "recipients": [],
                        "cc": [],
                    },
                    "reason": "blocked",
                },
                headers=_bearer(session),
            )

        assert resp.status_code == 403
        assert "gmail.compose" in resp.json()["detail"]

    async def test_scope_allowlist_permits_allowed_dwd_command(
        self, db: FakeDatabase
    ) -> None:
        """DWD command whose scope is in DELEGATION_SCOPES succeeds."""
        restricted = FakeSettings(
            credential_mode="sa+dwd",
            delegation_scopes=["https://www.googleapis.com/auth/calendar"],
        )
        app = make_e2e_test_app(db, restricted)

        await db.save_auth_code("allowed-code", "", _USER_EMAIL)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            session = await _exchange_session(c, "allowed-code")
            data = await _get_credential(
                c,
                session,
                {"type": "calendar.list"},
            )

        assert data["credentials"][0]["kind"] == "bearer_dwd"

    async def test_all_sa_command_types_route_to_bearer_sa(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """Every registered SA command type routes to bearer_sa. Driven from registry."""
        from extrasuite.server.command_registry import _SA_COMMAND_TYPES

        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        for cmd_type in sorted(_SA_COMMAND_TYPES):
            data = await _get_credential(
                client, session, {"type": cmd_type}, reason=f"coverage: {cmd_type}"
            )
            assert data["credentials"][0]["kind"] == "bearer_sa", (
                f"SA command {cmd_type!r} did not return bearer_sa"
            )

    async def test_all_dwd_command_types_route_to_bearer_dwd(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """Every registered DWD command type routes to bearer_dwd. Driven from registry."""
        from extrasuite.server.command_registry import _DWD_COMMAND_SCOPES

        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        for cmd_type in sorted(_DWD_COMMAND_SCOPES):
            data = await _get_credential(
                client, session, {"type": cmd_type}, reason=f"coverage: {cmd_type}"
            )
            assert data["credentials"][0]["kind"] == "bearer_dwd", (
                f"DWD command {cmd_type!r} did not return bearer_dwd"
            )


# ===========================================================================
# Gap 1 + Gap 3 — sa+oauth mode
# ===========================================================================


class TestE2ESaOauthMode:
    """End-to-end tests for CREDENTIAL_MODE=sa+oauth.

    SA commands use service account impersonation; DWD-class commands use the
    stored OAuth refresh token.
    """

    @pytest.fixture
    def db(self) -> FakeDatabase:
        return FakeDatabase()

    @pytest.fixture
    def encryptor(self):
        return _make_encryptor()

    @pytest.fixture
    def settings(self) -> FakeSettings:
        return FakeSettings(
            credential_mode="sa+oauth",
            oauth_scopes="spreadsheets,gmail.compose,gmail.readonly,calendar",
        )

    @pytest.fixture
    def revoke_fn(self) -> FakeRevokeFn:
        return FakeRevokeFn()

    @pytest.fixture
    async def client(
        self,
        db: FakeDatabase,
        settings: FakeSettings,
        encryptor,
        revoke_fn: FakeRevokeFn,
    ) -> AsyncGenerator:
        app = make_e2e_test_app(db, settings, encryptor=encryptor, oauth_revoke_fn=revoke_fn)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    async def test_callback_stores_encrypted_refresh_token(
        self,
        client: httpx.AsyncClient,
        db: FakeDatabase,
        encryptor,
    ) -> None:
        """OAuth callback stores an encrypted refresh token in DB for the user."""
        await _do_oauth_callback(client, db)

        record = await db.get_refresh_token(_USER_EMAIL)
        # Decrypt to confirm it's the expected value
        plaintext = encryptor.decrypt(record.encrypted_token)
        assert plaintext == "fake-refresh-token"

    async def test_session_exchange_provisions_service_account(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """sa+oauth: Phase 1 still provisions a service account for SA commands."""
        auth_code = await _do_oauth_callback(client, db)
        await _exchange_session(client, auth_code)

        assert len(db.users) == 1
        assert list(db.users.values())[0].endswith("@test-project.iam.gserviceaccount.com")

    async def test_sa_command_returns_bearer_sa(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """SA-class command (sheet.pull) returns bearer_sa in sa+oauth mode."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        data = await _get_credential(
            client,
            session,
            {"type": "sheet.pull", "file_url": "https://docs.google.com/s/1"},
        )

        cred = data["credentials"][0]
        assert cred["kind"] == "bearer_sa"
        assert cred["token"] == "fake-sa-token"

    async def test_dwd_command_uses_oauth_token(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """DWD-class command (gmail.compose) returns bearer_oauth in sa+oauth mode."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        data = await _get_credential(
            client,
            session,
            {"type": "gmail.compose", "subject": "Hi", "recipients": [], "cc": []},
        )

        cred = data["credentials"][0]
        assert cred["kind"] == "bearer_oauth"
        assert cred["token"] == "fake-oauth-token"

    async def test_dwd_command_fails_with_no_refresh_token(
        self, db: FakeDatabase, settings: FakeSettings, encryptor, revoke_fn: FakeRevokeFn
    ) -> None:
        """DWD command returns 400 if no refresh token is stored (user must re-login)."""
        app = make_e2e_test_app(db, settings, encryptor=encryptor, oauth_revoke_fn=revoke_fn)

        # Skip OAuth callback → no refresh token in DB
        await db.save_auth_code("no-token-code", "", _USER_EMAIL)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            session = await _exchange_session(c, "no-token-code")
            resp = await c.post(
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
                headers=_bearer(session),
            )

        assert resp.status_code == 400
        assert "re-authenticate" in resp.json()["detail"].lower() or "login" in resp.json()["detail"].lower()

    async def test_logout_revokes_token_at_google_and_deletes_from_db(
        self,
        client: httpx.AsyncClient,
        db: FakeDatabase,
        encryptor,
        revoke_fn: FakeRevokeFn,
    ) -> None:
        """POST /api/auth/oauth/revoke decrypts the refresh token, calls revoke_fn,
        and deletes the token from DB."""
        from extrasuite.server.database import RefreshTokenNotFound

        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        resp = await client.post(
            "/api/auth/oauth/revoke",
            headers=_bearer(session),
        )

        assert resp.status_code == 200
        assert resp.json() == {"status": "revoked"}

        # FakeRevokeFn should have been called with the plaintext refresh token
        assert revoke_fn.revoked_tokens == ["fake-refresh-token"]

        # Token deleted from DB
        with pytest.raises(RefreshTokenNotFound):
            await db.get_refresh_token(_USER_EMAIL)

    async def test_logout_no_token_is_noop(
        self, db: FakeDatabase, settings: FakeSettings, encryptor, revoke_fn: FakeRevokeFn
    ) -> None:
        """Logout when no refresh token stored is a no-op (returns 200)."""
        app = make_e2e_test_app(db, settings, encryptor=encryptor, oauth_revoke_fn=revoke_fn)

        raw = await _inject_session(db)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/auth/oauth/revoke", headers=_bearer(raw))

        assert resp.status_code == 200
        assert revoke_fn.revoked_tokens == []  # revoke_fn was not called

    async def test_all_dwd_commands_route_to_bearer_oauth(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """In sa+oauth mode, every DWD command routes to bearer_oauth. Driven from registry."""
        from extrasuite.server.command_registry import _DWD_COMMAND_SCOPES

        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        for cmd_type in sorted(_DWD_COMMAND_SCOPES):
            data = await _get_credential(
                client, session, {"type": cmd_type}, reason=f"coverage: {cmd_type}"
            )
            assert data["credentials"][0]["kind"] == "bearer_oauth", (
                f"DWD command {cmd_type!r} did not return bearer_oauth in sa+oauth mode"
            )


# ===========================================================================
# Gap 1 + Gap 3 — oauth mode (all commands via user's OAuth token)
# ===========================================================================


class TestE2EOauthMode:
    """End-to-end tests for CREDENTIAL_MODE=oauth.

    All commands use the stored user OAuth refresh token. No service accounts
    are provisioned.
    """

    @pytest.fixture
    def db(self) -> FakeDatabase:
        return FakeDatabase()

    @pytest.fixture
    def encryptor(self):
        return _make_encryptor()

    @pytest.fixture
    def settings(self) -> FakeSettings:
        return FakeSettings(
            credential_mode="oauth",
            oauth_scopes="spreadsheets,documents,presentations,forms.body,drive.readonly,gmail.compose,gmail.readonly,calendar,contacts.readonly,script.projects",
        )

    @pytest.fixture
    def revoke_fn(self) -> FakeRevokeFn:
        return FakeRevokeFn()

    @pytest.fixture
    async def client(
        self,
        db: FakeDatabase,
        settings: FakeSettings,
        encryptor,
        revoke_fn: FakeRevokeFn,
    ) -> AsyncGenerator:
        app = make_e2e_test_app(db, settings, encryptor=encryptor, oauth_revoke_fn=revoke_fn)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    async def test_session_exchange_does_not_provision_sa(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """In oauth mode, no service account is provisioned during session exchange."""
        auth_code = await _do_oauth_callback(client, db)
        await _exchange_session(client, auth_code)

        # DB must have no SA mapping
        assert len(db.users) == 0

    async def test_sa_command_returns_bearer_oauth(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """In oauth mode, SA-class commands return bearer_oauth (not bearer_sa)."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        data = await _get_credential(
            client,
            session,
            {"type": "sheet.pull", "file_url": "https://docs.google.com/s/1"},
        )

        cred = data["credentials"][0]
        assert cred["kind"] == "bearer_oauth"
        assert cred["token"] == "fake-oauth-token"

    async def test_dwd_command_returns_bearer_oauth(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """DWD-class commands also return bearer_oauth in oauth mode."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        data = await _get_credential(
            client,
            session,
            {"type": "gmail.compose", "subject": "Test", "recipients": [], "cc": []},
        )

        assert data["credentials"][0]["kind"] == "bearer_oauth"

    async def test_missing_refresh_token_returns_400(
        self, db: FakeDatabase, settings: FakeSettings, encryptor, revoke_fn: FakeRevokeFn
    ) -> None:
        """Any command returns 400 if no refresh token stored (user must re-login)."""
        app = make_e2e_test_app(db, settings, encryptor=encryptor, oauth_revoke_fn=revoke_fn)

        # Bypass callback so no refresh token is stored
        await db.save_auth_code("no-token", "", _USER_EMAIL)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            session = await _exchange_session(c, "no-token")
            resp = await c.post(
                "/api/auth/token",
                json={
                    "command": {"type": "sheet.pull", "file_url": "https://docs.google.com/s/1"},
                    "reason": "test",
                },
                headers=_bearer(session),
            )

        assert resp.status_code == 400

    async def test_logout_revokes_and_deletes_refresh_token(
        self,
        client: httpx.AsyncClient,
        db: FakeDatabase,
        revoke_fn: FakeRevokeFn,
    ) -> None:
        """Logout revokes the refresh token at Google and deletes it from DB."""
        from extrasuite.server.database import RefreshTokenNotFound

        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        resp = await client.post("/api/auth/oauth/revoke", headers=_bearer(session))

        assert resp.status_code == 200
        assert revoke_fn.revoked_tokens == ["fake-refresh-token"]
        with pytest.raises(RefreshTokenNotFound):
            await db.get_refresh_token(_USER_EMAIL)

    async def test_all_sa_commands_route_to_bearer_oauth(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """In oauth mode, every SA command type routes to bearer_oauth. Driven from registry."""
        from extrasuite.server.command_registry import _SA_COMMAND_TYPES

        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        for cmd_type in sorted(_SA_COMMAND_TYPES):
            data = await _get_credential(
                client, session, {"type": cmd_type}, reason=f"coverage: {cmd_type}"
            )
            assert data["credentials"][0]["kind"] == "bearer_oauth", (
                f"SA command {cmd_type!r} did not return bearer_oauth in oauth mode"
            )

    async def test_revoke_all_sessions_includes_oauth_warning(
        self, client: httpx.AsyncClient, db: FakeDatabase
    ) -> None:
        """In oauth mode, revoke-all returns a warning about the OAuth refresh token."""
        auth_code = await _do_oauth_callback(client, db)
        session = await _exchange_session(client, auth_code)

        resp = await client.post(
            "/api/admin/sessions/revoke-all",
            params={"email": _USER_EMAIL},
            headers=_bearer(session),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["oauth_token_revoked"] is False
        assert "warning" in data
