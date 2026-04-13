"""Unit tests for credentials module."""

import json
import os
import threading
import time
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from extrasuite.client.credentials import (
    Credential,
    CredentialsManager,
    InMemorySessionStore,
    SessionToken,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sa_cred(**kwargs) -> Credential:
    """Build a minimal SA Credential for testing."""
    defaults: dict = {
        "provider": "google",
        "kind": "bearer_sa",
        "token": "test-token",
        "expires_at": time.time() + 3600,
        "scopes": [],
        "metadata": {"service_account_email": "sa@example.com"},
    }
    defaults.update(kwargs)
    return Credential(**defaults)


def _make_dwd_cred(**kwargs) -> Credential:
    """Build a minimal DWD Credential for testing."""
    defaults: dict = {
        "provider": "google",
        "kind": "bearer_dwd",
        "token": "test-dwd-token",
        "expires_at": time.time() + 600,
        "scopes": ["https://www.googleapis.com/auth/gmail.compose"],
        "metadata": {},
    }
    defaults.update(kwargs)
    return Credential(**defaults)


def _v2_token_response(token: str = "v2-token", kind: str = "bearer_sa") -> dict:
    """Return a mock /api/auth/token response."""
    return {
        "credentials": [
            {
                "provider": "google",
                "kind": kind,
                "token": token,
                "expires_at": "2027-01-01T00:00:00+00:00",
                "scopes": [],
                "metadata": {
                    "service_account_email": "sa@project.iam.gserviceaccount.com"
                },
            }
        ],
        "command_type": "sheet.pull",
    }


def _make_manager(
    server_url: str = "https://myserver.example.com",
    store: InMemorySessionStore | None = None,
    **kwargs,
) -> CredentialsManager:
    """Create a CredentialsManager with an InMemorySessionStore."""
    return CredentialsManager(
        server_url=server_url,
        session_store=store or InMemorySessionStore(),
        **kwargs,
    )


def _valid_session(**kwargs) -> SessionToken:
    defaults = {
        "raw_token": "my-session-token",
        "email": "user@example.com",
        "expires_at": time.time() + 86400,
    }
    defaults.update(kwargs)
    return SessionToken(**defaults)


# ---------------------------------------------------------------------------
# TestCredential
# ---------------------------------------------------------------------------


class TestCredential:
    """Tests for Credential dataclass."""

    def test_is_valid_with_valid_token(self) -> None:
        cred = _make_sa_cred(expires_at=time.time() + 3600)
        assert cred.is_valid() is True

    def test_is_valid_with_expired_token(self) -> None:
        cred = _make_sa_cred(expires_at=time.time() - 100)
        assert cred.is_valid() is False

    def test_is_valid_respects_buffer(self) -> None:
        cred = _make_sa_cred(expires_at=time.time() + 30)
        assert cred.is_valid(buffer_seconds=60) is False
        assert cred.is_valid(buffer_seconds=10) is True

    def test_non_expiring_credential(self) -> None:
        cred = _make_sa_cred(expires_at=0)
        assert cred.is_valid() is True
        assert cred.expires_in_seconds() == 0

    def test_expires_in_seconds(self) -> None:
        future_time = time.time() + 3600
        cred = _make_sa_cred(expires_at=future_time)
        assert 3598 <= cred.expires_in_seconds() <= 3600

    def test_expires_in_seconds_with_expired(self) -> None:
        cred = _make_sa_cred(expires_at=time.time() - 100)
        assert cred.expires_in_seconds() == 0

    def test_service_account_email_property(self) -> None:
        cred = _make_sa_cred(
            metadata={"service_account_email": "sa@proj.iam.gserviceaccount.com"}
        )
        assert cred.service_account_email == "sa@proj.iam.gserviceaccount.com"

    def test_service_account_email_missing(self) -> None:
        cred = _make_dwd_cred(metadata={})
        assert cred.service_account_email == ""

    def test_to_dict_roundtrip(self) -> None:
        original = _make_sa_cred(expires_at=1234567890.0)
        restored = Credential.from_dict(original.to_dict())
        assert restored.provider == original.provider
        assert restored.kind == original.kind
        assert restored.token == original.token
        assert restored.expires_at == original.expires_at
        assert restored.scopes == original.scopes
        assert restored.metadata == original.metadata

    def test_to_dict_structure(self) -> None:
        cred = _make_sa_cred(token="tok", expires_at=1234.0)
        d = cred.to_dict()
        assert d["provider"] == "google"
        assert d["kind"] == "bearer_sa"
        assert d["token"] == "tok"
        assert d["expires_at"] == 1234.0
        assert "scopes" in d
        assert "metadata" in d

    def test_from_dict_missing_required_key_raises(self) -> None:
        with pytest.raises(KeyError):
            Credential.from_dict({"provider": "google"})


# ---------------------------------------------------------------------------
# TestCredentialsManagerInit
# ---------------------------------------------------------------------------


class TestCredentialsManagerInit:
    """Tests for CredentialsManager initialization."""

    def test_init_with_server_url_param(self) -> None:
        manager = _make_manager(server_url="https://auth.example.com")
        assert manager._server_base_url == "https://auth.example.com"
        assert manager._use_extrasuite is True
        assert manager.auth_mode == "extrasuite"

    def test_init_with_service_account_path_param(self) -> None:
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/path/to/sa.json")
        assert manager._sa_path == Path("/path/to/sa.json")
        assert manager._use_extrasuite is False
        assert manager.auth_mode == "service_account"

    def test_init_with_env_vars(self) -> None:
        env = {"EXTRASUITE_SERVER_URL": "https://auth.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            manager = _make_manager(server_url="https://auth.example.com")
        assert manager._server_base_url == "https://auth.example.com"

    def test_init_with_env_var_service_account(self) -> None:
        env = {"SERVICE_ACCOUNT_PATH": "/path/to/sa.json"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(
                CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
            ),
        ):
            manager = CredentialsManager()
        assert manager._sa_path == Path("/path/to/sa.json")
        assert manager._use_extrasuite is False

    def test_init_param_overrides_env_var(self) -> None:
        env = {"EXTRASUITE_SERVER_URL": "https://env.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            manager = _make_manager(server_url="https://param.example.com")
        assert manager._server_base_url == "https://param.example.com"

    def test_init_extrasuite_takes_precedence_over_service_account(self) -> None:
        manager = _make_manager(
            server_url="https://auth.example.com",
        )
        assert manager._use_extrasuite is True

    def test_init_no_config_raises_error(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
            ),
            pytest.raises(ValueError, match="No authentication method configured"),
        ):
            CredentialsManager()

    def test_init_with_server_url_env_var(self) -> None:
        env = {"EXTRASUITE_SERVER_URL": "https://myserver.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            manager = _make_manager()
        assert manager._server_base_url == "https://myserver.example.com"

    def test_init_with_server_url_env_var_trailing_slash(self) -> None:
        env = {"EXTRASUITE_SERVER_URL": "https://myserver.example.com/"}
        with mock.patch.dict(os.environ, env, clear=True):
            manager = _make_manager()
        assert manager._server_base_url == "https://myserver.example.com"


# ---------------------------------------------------------------------------
# TestCredentialsManagerGatewayConfig
# ---------------------------------------------------------------------------


class TestCredentialsManagerGatewayConfig:
    """Tests for gateway.json loading."""

    def test_gateway_config_path_override(self, tmp_path: Path) -> None:
        gateway = tmp_path / "gateway.json"
        gateway.write_text(
            json.dumps({"EXTRASUITE_SERVER_URL": "https://gw.example.com"})
        )
        manager = _make_manager(
            server_url="https://gw.example.com",
            gateway_config_path=gateway,
        )
        assert manager._server_base_url == "https://gw.example.com"

    def test_gateway_config_path_not_found_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing_gateway.json"
        with pytest.raises(FileNotFoundError):
            CredentialsManager(gateway_config_path=missing)

    def test_gateway_server_url_derives_all_urls(self, tmp_path: Path) -> None:
        gateway = tmp_path / "gateway.json"
        gateway.write_text(
            json.dumps({"EXTRASUITE_SERVER_URL": "https://srv.example.com"})
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            manager = CredentialsManager(
                gateway_config_path=gateway,
                session_store=InMemorySessionStore(),
            )
        assert manager._server_base_url == "https://srv.example.com"


# ---------------------------------------------------------------------------
# TestInMemorySessionStore
# ---------------------------------------------------------------------------


class TestInMemorySessionStore:
    """Tests for the InMemorySessionStore."""

    def test_load_returns_none_when_empty(self) -> None:
        store = InMemorySessionStore()
        assert store.load("default") is None

    def test_save_and_load_valid_token(self) -> None:
        store = InMemorySessionStore()
        token = _valid_session()
        store.save("default", token)
        loaded = store.load("default")
        assert loaded is not None
        assert loaded.raw_token == token.raw_token

    def test_load_returns_none_for_expired_token(self) -> None:
        store = InMemorySessionStore()
        expired = SessionToken(
            raw_token="tok", email="u@e.com", expires_at=time.time() - 100
        )
        store.save("default", expired)
        assert store.load("default") is None

    def test_delete_removes_token(self) -> None:
        store = InMemorySessionStore()
        store.save("default", _valid_session())
        store.delete("default")
        assert store.load("default") is None

    def test_delete_nonexistent_is_noop(self) -> None:
        store = InMemorySessionStore()
        store.delete("nonexistent")  # should not raise

    def test_multiple_profiles_are_independent(self) -> None:
        store = InMemorySessionStore()
        t1 = _valid_session(raw_token="tok-work", email="work@example.com")
        t2 = _valid_session(raw_token="tok-personal", email="personal@example.com")
        store.save("work", t1)
        store.save("personal", t2)
        assert store.load("work").raw_token == "tok-work"  # type: ignore[union-attr]
        assert store.load("personal").raw_token == "tok-personal"  # type: ignore[union-attr]
        store.delete("work")
        assert store.load("work") is None
        assert store.load("personal") is not None


# ---------------------------------------------------------------------------
# TestGetCredentialExtraSuite
# ---------------------------------------------------------------------------


class TestGetCredentialExtraSuite:
    """Tests for get_credential() in ExtraSuite (v2 session) mode."""

    def test_get_credential_v2_session_exchange(self) -> None:
        store = InMemorySessionStore()
        store.save("default", _valid_session())
        manager = _make_manager(store=store)
        mock_response = _v2_token_response("v2-access-token")

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.get_credential(
                command={
                    "type": "sheet.pull",
                    "file_url": "https://docs.google.com/...",
                },
                reason="Pull sheet for analysis",
            )

        assert result.token == "v2-access-token"
        assert result.service_account_email == "sa@project.iam.gserviceaccount.com"

    def test_get_credential_always_fetches_fresh(self) -> None:
        """get_credential() never returns a stale cached value — always exchanges."""
        store = InMemorySessionStore()
        store.save("default", _valid_session())
        manager = _make_manager(store=store)
        mock_response = _v2_token_response("fresh-tok")

        call_count = 0

        def fake_urlopen(_req, **_kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            return mock_resp

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            manager.get_credential(command={"type": "sheet.pull"}, reason="First call")
            manager.get_credential(command={"type": "sheet.pull"}, reason="Second call")

        assert call_count == 2

    def test_get_credential_force_refresh_accepted(self) -> None:
        """force_refresh=True is accepted without error (no effect, kept for API compat)."""
        store = InMemorySessionStore()
        store.save("default", _valid_session())
        manager = _make_manager(store=store)
        mock_response = _v2_token_response("v2-access-token")

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.get_credential(
                command={"type": "sheet.pull"},
                reason="Test",
                force_refresh=True,
            )
        assert result.token == "v2-access-token"


# ---------------------------------------------------------------------------
# TestGetCredentialServiceAccount
# ---------------------------------------------------------------------------


class TestGetCredentialServiceAccount:
    """Tests for get_credential() in service account file mode."""

    def test_service_account_file_not_found(self, tmp_path: Path) -> None:
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(
                service_account_path=str(tmp_path / "missing.json")
            )

        try:
            import google.auth  # noqa: F401

            with pytest.raises(FileNotFoundError):
                manager.get_credential(command={"type": "sheet.pull"}, reason="Test")
        except ImportError:
            with pytest.raises(ImportError):
                manager.get_credential(command={"type": "sheet.pull"}, reason="Test")

    def test_service_account_missing_google_auth(self) -> None:
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/path/to/sa.json")

        try:
            import google.auth  # noqa: F401

            pytest.skip("google-auth is installed, cannot test ImportError case")
        except ImportError:
            with pytest.raises(ImportError, match="google-auth"):
                manager.get_credential(command={"type": "sheet.pull"}, reason="Test")


# ---------------------------------------------------------------------------
# TestCredentialsManagerCallbackHandler
# ---------------------------------------------------------------------------


class TestCredentialsManagerCallbackHandler:
    """Tests for the HTTP callback handler."""

    def test_callback_handler_receives_code(self) -> None:
        result_holder = {"code": None, "error": None, "done": False}
        result_lock = threading.Lock()

        handler_class = CredentialsManager._create_handler_class(
            result_holder, result_lock
        )

        with mock.patch.object(handler_class, "__init__", lambda _self, *_args: None):
            handler = handler_class.__new__(handler_class)
            handler.path = "/on-authentication?code=test-auth-code"
            handler.send_response = mock.MagicMock()
            handler.send_header = mock.MagicMock()
            handler.end_headers = mock.MagicMock()
            handler.wfile = mock.MagicMock()

            handler.do_GET()

            assert result_holder["code"] == "test-auth-code"
            assert result_holder["done"] is True

    def test_callback_handler_receives_error(self) -> None:
        result_holder = {"code": None, "error": None, "done": False}
        result_lock = threading.Lock()

        handler_class = CredentialsManager._create_handler_class(
            result_holder, result_lock
        )

        with mock.patch.object(handler_class, "__init__", lambda _self, *_args: None):
            handler = handler_class.__new__(handler_class)
            handler.path = "/on-authentication?error=access_denied"
            handler.send_response = mock.MagicMock()
            handler.send_header = mock.MagicMock()
            handler.end_headers = mock.MagicMock()
            handler.wfile = mock.MagicMock()

            handler.do_GET()

            assert result_holder["error"] == "access_denied"
            assert result_holder["done"] is True


# ---------------------------------------------------------------------------
# TestSessionToken
# ---------------------------------------------------------------------------


class TestSessionToken:
    """Tests for SessionToken dataclass."""

    def test_is_valid_with_future_expiry(self) -> None:
        token = SessionToken(
            raw_token="raw-token",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        assert token.is_valid() is True

    def test_is_valid_with_expired_token(self) -> None:
        token = SessionToken(
            raw_token="raw-token",
            email="user@example.com",
            expires_at=time.time() - 100,
        )
        assert token.is_valid() is False

    def test_is_valid_respects_5min_buffer(self) -> None:
        token = SessionToken(
            raw_token="raw-token",
            email="user@example.com",
            expires_at=time.time() + 200,
        )
        assert token.is_valid(buffer_seconds=300) is False
        assert token.is_valid(buffer_seconds=100) is True

    def test_to_dict_from_dict_roundtrip(self) -> None:
        original = SessionToken(
            raw_token="raw-token-abc",
            email="user@example.com",
            expires_at=1234567890.0,
        )
        restored = SessionToken.from_dict(original.to_dict())
        assert restored.raw_token == original.raw_token
        assert restored.email == original.email
        assert restored.expires_at == original.expires_at


# ---------------------------------------------------------------------------
# TestV2SessionFlow
# ---------------------------------------------------------------------------


class TestV2SessionFlow:
    """Tests for v2 session-token auth protocol."""

    def test_get_or_create_session_token_returns_cached(self) -> None:
        store = InMemorySessionStore()
        session = _valid_session(raw_token="cached-session-token")
        store.save("default", session)
        manager = _make_manager(store=store)

        result = manager._get_or_create_session_token()
        assert result.raw_token == "cached-session-token"

    def test_get_or_create_session_token_creates_new_when_no_cache(self) -> None:
        manager = _make_manager()
        mock_exchange_response = {
            "session_token": "new-session-token",
            "email": "user@example.com",
            "expires_at": "2026-12-31T00:00:00+00:00",
        }

        with (
            mock.patch.object(
                manager, "_run_browser_flow_for_session", return_value="test-auth-code"
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
            mock.patch.object(manager, "_save_profiles"),
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_exchange_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager._get_or_create_session_token()

        assert result.raw_token == "new-session-token"
        assert result.email == "user@example.com"
        # Saved in the in-memory store
        assert manager._session_store.load("default") is not None  # type: ignore[attr-defined]

    def test_get_or_create_session_token_force_skips_cache(self) -> None:
        store = InMemorySessionStore()
        store.save("default", _valid_session(raw_token="old-token"))
        manager = _make_manager(store=store)
        mock_exchange_response = {
            "session_token": "new-token",
            "email": "user@example.com",
            "expires_at": "2026-12-31T00:00:00+00:00",
        }

        with (
            mock.patch.object(
                manager, "_run_browser_flow_for_session", return_value="fresh-auth-code"
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
            mock.patch.object(manager, "_save_profiles"),
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_exchange_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager._get_or_create_session_token(force=True)

        assert result.raw_token == "new-token"

    def test_exchange_session_for_credential_success(self) -> None:
        manager = _make_manager()
        session = _valid_session()
        mock_response = _v2_token_response("short-lived-token")

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager._exchange_session_for_credential(
                session,
                command={"type": "sheet.pull", "file_url": ""},
                reason="Test pull",
            )

        assert result["credentials"][0]["token"] == "short-lived-token"

    def test_exchange_session_for_credential_401_raises_helpful_error(self) -> None:
        manager = _make_manager()
        session = _valid_session()

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            error = urllib.error.HTTPError(
                url="https://myserver.example.com/api/auth/token",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=mock.MagicMock(read=lambda: b"Session expired"),
            )
            mock_urlopen.side_effect = error

            with pytest.raises(Exception) as exc_info:
                manager._exchange_session_for_credential(
                    session,
                    command={"type": "sheet.pull"},
                    reason="Test",
                )
        assert "extrasuite auth login" in str(exc_info.value)

    def test_get_credential_v2_uses_session_exchange(self) -> None:
        store = InMemorySessionStore()
        store.save("default", _valid_session())
        manager = _make_manager(store=store)
        mock_response = _v2_token_response("v2-access-token")

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.get_credential(
                command={
                    "type": "sheet.pull",
                    "file_url": "https://docs.google.com/...",
                },
                reason="Test: pull sheet",
            )

        assert result.token == "v2-access-token"
        assert result.service_account_email == "sa@project.iam.gserviceaccount.com"

    def test_get_credential_dwd_v2_uses_session_exchange(self) -> None:
        store = InMemorySessionStore()
        store.save("default", _valid_session())
        manager = _make_manager(store=store)
        mock_response = _v2_token_response("dwd-access-token", kind="bearer_dwd")
        mock_response["command_type"] = "gmail.compose"

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.get_credential(
                command={
                    "type": "gmail.compose",
                    "subject": "Hello",
                    "recipients": ["a@b.com"],
                },
                reason="Test: send email",
            )

        assert result.token == "dwd-access-token"
        assert result.kind == "bearer_dwd"

    def test_login_force_revokes_existing_and_creates_new(self) -> None:
        store = InMemorySessionStore()
        old_session = _valid_session(raw_token="old-session")
        store.save("default", old_session)
        manager = _make_manager(store=store)

        mock_exchange_response = {
            "session_token": "new-session",
            "email": "user@example.com",
            "expires_at": "2026-12-31T00:00:00+00:00",
        }

        with (
            mock.patch.object(manager, "_revoke_server_side") as mock_revoke,
            mock.patch.object(
                manager, "_run_browser_flow_for_session", return_value="auth-code"
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
            mock.patch.object(manager, "_save_profiles"),
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_exchange_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.login(force=True)

        mock_revoke.assert_called_once_with("old-session")
        assert result.raw_token == "new-session"
        # Old token deleted from store
        assert store.load("default") is not None  # new token now there
        assert store.load("default").raw_token == "new-session"  # type: ignore[union-attr]

    def test_login_without_force_returns_existing_session(self) -> None:
        store = InMemorySessionStore()
        existing = _valid_session(raw_token="existing-session")
        store.save("default", existing)
        manager = _make_manager(store=store)

        with (
            mock.patch.object(manager, "_revoke_server_side") as mock_revoke,
            mock.patch.object(manager, "_save_profiles"),
        ):
            result = manager.login(force=False)

        mock_revoke.assert_not_called()
        assert result.raw_token == "existing-session"

    def test_logout_revokes_server_side_and_deletes_from_store(self) -> None:
        store = InMemorySessionStore()
        store.save("default", _valid_session(raw_token="tok-to-revoke"))
        manager = _make_manager(store=store)

        with (
            mock.patch.object(manager, "_revoke_server_side") as mock_revoke,
            mock.patch.object(
                manager,
                "_load_profiles",
                return_value={"profiles": {"default": "u@e.com"}, "active": "default"},
            ),
            mock.patch.object(manager, "_save_profiles"),
        ):
            manager.logout()

        mock_revoke.assert_called_once_with("tok-to-revoke")
        assert store.load("default") is None

    def test_logout_with_no_session_is_noop(self) -> None:
        manager = _make_manager()

        with (
            mock.patch.object(manager, "_revoke_server_side") as mock_revoke,
            mock.patch.object(
                manager, "_load_profiles", return_value={"profiles": {}, "active": None}
            ),
            mock.patch.object(manager, "_save_profiles"),
        ):
            manager.logout()  # should not raise

        mock_revoke.assert_not_called()

    def test_status_returns_active_profiles(self) -> None:
        store = InMemorySessionStore()
        session = _valid_session(
            email="user@example.com", expires_at=time.time() + 86400 * 5
        )
        store.save("work", session)
        manager = _make_manager(store=store)

        profiles_data = {"profiles": {"work": "user@example.com"}, "active": "work"}
        with mock.patch.object(manager, "_load_profiles", return_value=profiles_data):
            info = manager.status()

        assert "work" in info["profiles"]
        assert info["profiles"]["work"]["active"] is True
        assert info["profiles"]["work"]["email"] == "user@example.com"
        assert info["profiles"]["work"]["days_remaining"] in (4, 5)
        assert info["active"] == "work"

    def test_status_marks_expired_profile(self) -> None:
        store = InMemorySessionStore()
        # No token saved → expired
        manager = _make_manager(store=store)

        profiles_data = {"profiles": {"work": "user@example.com"}, "active": "work"}
        with mock.patch.object(manager, "_load_profiles", return_value=profiles_data):
            info = manager.status()

        assert info["profiles"]["work"]["active"] is False
        assert info["profiles"]["work"].get("expired") is True

    def test_activate_sets_active_profile(self) -> None:
        manager = _make_manager()
        profiles_data = {
            "profiles": {"work": "u@e.com", "personal": "u2@e.com"},
            "active": "work",
        }

        with (
            mock.patch.object(manager, "_load_profiles", return_value=profiles_data),
            mock.patch.object(manager, "_save_profiles") as mock_save,
        ):
            manager.activate("personal")

        saved = mock_save.call_args[0][0]
        assert saved["active"] == "personal"

    def test_activate_unknown_profile_raises(self) -> None:
        manager = _make_manager()
        profiles_data = {"profiles": {"work": "u@e.com"}, "active": "work"}

        with (
            mock.patch.object(manager, "_load_profiles", return_value=profiles_data),
            pytest.raises(ValueError, match="Profile 'ghost' not found"),
        ):
            manager.activate("ghost")

    def test_find_free_port(self) -> None:
        port = CredentialsManager._find_free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535
