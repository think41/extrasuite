"""Tests for TokenGenerator.generate_oauth_token()."""

import json
import secrets
import urllib.error
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from extrasuite.server.crypto import RefreshTokenEncryptor
from extrasuite.server.token_generator import OAuthTokenError, TokenGenerator
from tests.fakes import (
    FakeDatabase,
    FakeIAMAsyncClient,
    FakeSettings,
    create_fake_impersonated_credentials_class,
)


def _make_encryptor() -> RefreshTokenEncryptor:
    return RefreshTokenEncryptor(secrets.token_hex(32))


def _make_token_generator(db=None, encryptor=None):
    db = db or FakeDatabase()
    settings = FakeSettings(
        google_client_id="client-id-123",
        google_client_secret="client-secret-456",
    )
    FakeCreds = create_fake_impersonated_credentials_class()
    return TokenGenerator(
        database=db,
        settings=settings,
        iam_client=FakeIAMAsyncClient(),
        impersonated_credentials_class=FakeCreds,
        encryptor=encryptor,
    )


def _make_token_response(
    *,
    access_token: str = "ya29.access-token",
    expires_in: int = 3600,
    new_refresh_token: str | None = None,
) -> bytes:
    payload: dict = {"access_token": access_token, "expires_in": expires_in}
    if new_refresh_token:
        payload["refresh_token"] = new_refresh_token
    return json.dumps(payload).encode()


class FakeHTTPResponse:
    """Minimal urllib response mock."""

    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestGenerateOauthToken:
    @pytest.mark.asyncio
    async def test_success(self):
        encryptor = _make_encryptor()
        db = FakeDatabase()
        tg = _make_token_generator(db, encryptor)

        encrypted = encryptor.encrypt("1//04-refresh-token")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = FakeHTTPResponse(_make_token_response())
            token = await tg.generate_oauth_token("user@example.com", encrypted, scopes)

        assert token.token == "ya29.access-token"
        assert token.service_account_email == ""
        assert token.expires_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_invalid_grant_raises_oauth_token_error(self):
        encryptor = _make_encryptor()
        tg = _make_token_generator(encryptor=encryptor)

        encrypted = encryptor.encrypt("expired-refresh-token")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        error_body = json.dumps({"error": "invalid_grant"}).encode()
        http_error = urllib.error.HTTPError(
            url="https://oauth2.googleapis.com/token",
            code=400,
            msg="Bad Request",
            hdrs=MagicMock(),
            fp=BytesIO(error_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_error), pytest.raises(OAuthTokenError) as exc_info:
            await tg.generate_oauth_token("user@example.com", encrypted, scopes)

        assert "extrasuite auth login" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_encryptor_raises(self):
        tg = _make_token_generator(encryptor=None)
        with pytest.raises(OAuthTokenError, match=r"[Ee]ncryptor"):
            await tg.generate_oauth_token("user@example.com", "encrypted", [])

    @pytest.mark.asyncio
    async def test_decryption_failure_raises(self):
        encryptor = _make_encryptor()
        tg = _make_token_generator(encryptor=encryptor)

        with pytest.raises(OAuthTokenError, match=r"[Dd]ecrypt"):
            await tg.generate_oauth_token("user@example.com", "not-valid-ciphertext!!!", [])

    @pytest.mark.asyncio
    async def test_refresh_token_rotation_updates_firestore(self):
        encryptor = _make_encryptor()
        db = FakeDatabase()
        tg = _make_token_generator(db, encryptor)

        encrypted = encryptor.encrypt("old-refresh-token")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        # Google returns a new refresh_token (rotation)
        response_data = _make_token_response(new_refresh_token="brand-new-refresh-token")

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = FakeHTTPResponse(response_data)
            await tg.generate_oauth_token("user@example.com", encrypted, scopes)

        # New token should be stored in DB (encrypted)
        new_encrypted = await db.get_encrypted_refresh_token("user@example.com")
        assert new_encrypted is not None
        # Verify it decrypts to the new token
        assert encryptor.decrypt(new_encrypted) == "brand-new-refresh-token"

    @pytest.mark.asyncio
    async def test_no_rotation_does_not_update_firestore(self):
        encryptor = _make_encryptor()
        db = FakeDatabase()
        tg = _make_token_generator(db, encryptor)

        encrypted = encryptor.encrypt("stable-refresh-token")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = FakeHTTPResponse(_make_token_response())
            await tg.generate_oauth_token("user@example.com", encrypted, scopes)

        # No new token should be stored
        assert not await db.has_refresh_token("user@example.com")

    @pytest.mark.asyncio
    async def test_network_error_raises_oauth_token_error(self):
        encryptor = _make_encryptor()
        tg = _make_token_generator(encryptor=encryptor)

        encrypted = encryptor.encrypt("some-refresh-token")

        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")), pytest.raises(OAuthTokenError, match=r"[Nn]etwork|[Ff]ailed"):
            await tg.generate_oauth_token("user@example.com", encrypted, [])

    @pytest.mark.asyncio
    async def test_non_invalid_grant_http_error(self):
        """Non-400 errors or non-invalid_grant 400s should also raise OAuthTokenError."""
        encryptor = _make_encryptor()
        tg = _make_token_generator(encryptor=encryptor)

        encrypted = encryptor.encrypt("some-refresh-token")

        error_body = json.dumps({"error": "server_error"}).encode()
        http_error = urllib.error.HTTPError(
            url="https://oauth2.googleapis.com/token",
            code=500,
            msg="Internal Server Error",
            hdrs=MagicMock(),
            fp=BytesIO(error_body),
        )

        with patch("urllib.request.urlopen", side_effect=http_error), pytest.raises(OAuthTokenError):
            await tg.generate_oauth_token("user@example.com", encrypted, [])
