"""End-to-end integration tests for the OAuth credential flow.

Tests the server-side wiring of the four-step protocol in oauth credential mode:
  1. Auth code delivery (simulating what google_callback writes to Firestore)
  2. POST /api/auth/session/exchange → 30-day session token
  3. POST /api/auth/token → OAuth credential issued
  4. POST /api/auth/oauth/revoke → on_logout called

Uses make_test_app() with a mock credential router in oauth mode and FakeDatabase.
No real Google API calls are made.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from extrasuite.server.command_registry import Credential
from extrasuite.server.credential_router import CommandCredentialRouter
from tests.conftest import make_test_app
from tests.fakes import FakeDatabase, FakeSettings

_USER_EMAIL = "user@oauth-test.com"
_FAKE_ACCESS_TOKEN = "ya29.fake-oauth-access-token"


def _make_oauth_router() -> MagicMock:
    """Mock router simulating oauth credential_mode: all commands return bearer_oauth."""
    mock_router = MagicMock(spec=CommandCredentialRouter)
    mock_router.on_google_auth_callback = AsyncMock()
    mock_router.on_session_establishment = AsyncMock()
    mock_router.on_logout = AsyncMock()

    async def _resolve(_command, _email: str) -> list[Credential]:
        return [
            Credential(
                provider="google",
                kind="bearer_oauth",
                token=_FAKE_ACCESS_TOKEN,
                expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
                metadata={},
            )
        ]

    mock_router.resolve = AsyncMock(side_effect=_resolve)
    return mock_router


def _bearer(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


@pytest.mark.asyncio
async def test_full_oauth_flow_auth_code_to_credential_to_revoke() -> None:
    """Walk the complete OAuth credential flow end-to-end."""
    db = FakeDatabase()
    settings = FakeSettings(credential_mode="oauth")
    router = _make_oauth_router()
    app = make_test_app(db, settings, router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Step 1: Simulate auth code delivery (what google_callback writes)
        auth_code = secrets.token_urlsafe(32)
        await db.save_auth_code(auth_code, "", _USER_EMAIL)

        # Step 2: Exchange auth code for session token
        resp = await client.post(
            "/api/auth/session/exchange",
            json={"code": auth_code, "device_hostname": "test-machine"},
        )
        assert resp.status_code == 200, resp.text
        session_data = resp.json()
        assert session_data["email"] == _USER_EMAIL
        assert "session_token" in session_data
        session_token = session_data["session_token"]

        # on_session_establishment must have been called (provisions SA or no-op for oauth)
        router.on_session_establishment.assert_called_once_with(_USER_EMAIL)

        # Session must be persisted in DB
        token_hash = hashlib.sha256(session_token.encode()).hexdigest()
        assert await db.validate_session_token(token_hash) is not None

        # Step 3: Use session to request an OAuth credential
        resp = await client.post(
            "/api/auth/token",
            json={
                "command": {
                    "type": "sheet.pull",
                    "file_url": "https://docs.google.com/spreadsheets/d/1/edit",
                    "file_name": "budget",
                },
                "reason": "reviewing the budget",
            },
            headers=_bearer(session_token),
        )
        assert resp.status_code == 200, resp.text
        cred_data = resp.json()
        assert cred_data["command_type"] == "sheet.pull"
        assert len(cred_data["credentials"]) == 1
        cred = cred_data["credentials"][0]
        assert cred["kind"] == "bearer_oauth"
        assert cred["token"] == _FAKE_ACCESS_TOKEN

        # Access must be logged
        assert len(db.access_logs) == 1
        log = db.access_logs[0]
        assert log["email"] == _USER_EMAIL
        assert log["command_type"] == "sheet.pull"
        assert log["reason"] == "reviewing the budget"
        assert log["credential_kind"] == "bearer_oauth"

        # Step 4: Revoke the OAuth token (logout)
        resp = await client.post("/api/auth/oauth/revoke", headers=_bearer(session_token))
        assert resp.status_code == 200
        assert resp.json() == {"status": "revoked"}
        router.on_logout.assert_called_once_with(_USER_EMAIL)


@pytest.mark.asyncio
async def test_auth_code_is_single_use() -> None:
    """The same auth code cannot be exchanged twice."""
    db = FakeDatabase()
    settings = FakeSettings(credential_mode="oauth")
    router = _make_oauth_router()
    app = make_test_app(db, settings, router)

    auth_code = secrets.token_urlsafe(32)
    await db.save_auth_code(auth_code, "", _USER_EMAIL)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp1 = await client.post("/api/auth/session/exchange", json={"code": auth_code})
        assert resp1.status_code == 200

        # Second exchange of the same code must fail
        resp2 = await client.post("/api/auth/session/exchange", json={"code": auth_code})
        assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_session_establishment_failure_returns_500() -> None:
    """If on_session_establishment raises, the exchange endpoint returns 500."""
    db = FakeDatabase()
    settings = FakeSettings(credential_mode="oauth")
    router = _make_oauth_router()
    router.on_session_establishment = AsyncMock(
        side_effect=RuntimeError("credential provisioning failed")
    )
    app = make_test_app(db, settings, router)

    auth_code = secrets.token_urlsafe(32)
    await db.save_auth_code(auth_code, "", _USER_EMAIL)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/auth/session/exchange", json={"code": auth_code})

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_revoke_requires_valid_session() -> None:
    """Revoke endpoint rejects requests without a valid session token."""
    db = FakeDatabase()
    settings = FakeSettings(credential_mode="oauth")
    router = _make_oauth_router()
    app = make_test_app(db, settings, router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # No header at all
        resp = await client.post("/api/auth/oauth/revoke")
        assert resp.status_code == 401

        # Invalid token
        resp = await client.post(
            "/api/auth/oauth/revoke", headers=_bearer("not-a-valid-token")
        )
        assert resp.status_code == 401
