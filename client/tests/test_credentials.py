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


def _cred_dict(**kwargs) -> dict:
    """Return a dict matching Credential.to_dict() for writing to cache files."""
    return _make_sa_cred(**kwargs).to_dict()


def _v2_token_response(token: str = "v2-token", kind: str = "bearer_sa") -> dict:
    """Return a mock /api/auth/token response (new TokenResponse format)."""
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
        manager = CredentialsManager(server_url="https://auth.example.com")
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
            manager = CredentialsManager()
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
            manager = CredentialsManager(server_url="https://param.example.com")
        assert manager._server_base_url == "https://param.example.com"

    def test_init_extrasuite_takes_precedence_over_service_account(self) -> None:
        manager = CredentialsManager(
            server_url="https://auth.example.com",
            service_account_path="/path/to/sa.json",
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
            manager = CredentialsManager()
        assert manager._server_base_url == "https://myserver.example.com"

    def test_init_with_server_url_env_var_trailing_slash(self) -> None:
        env = {"EXTRASUITE_SERVER_URL": "https://myserver.example.com/"}
        with mock.patch.dict(os.environ, env, clear=True):
            manager = CredentialsManager()
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
        manager = CredentialsManager(gateway_config_path=gateway)
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
            manager = CredentialsManager(gateway_config_path=gateway)
        assert manager._server_base_url == "https://srv.example.com"


# ---------------------------------------------------------------------------
# TestCredentialsManagerCredentialCache
# ---------------------------------------------------------------------------


class TestCredentialsManagerCredentialCache:
    """Tests for per-command-type credential file caching."""

    def test_load_cached_credential_no_file(self, tmp_path: Path) -> None:
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/sa.json")
        cache_path = tmp_path / "sheet.pull.json"
        assert manager._load_cached_credential(cache_path) is None

    def test_load_cached_credential_valid(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "sheet.pull.json"
        cred = _make_sa_cred(token="cached-tok", expires_at=time.time() + 3600)
        cache_path.write_text(json.dumps(cred.to_dict()))

        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/sa.json")
        result = manager._load_cached_credential(cache_path)
        assert result is not None
        assert result.token == "cached-tok"

    def test_load_cached_credential_expired_returns_cred(self, tmp_path: Path) -> None:
        """Expired credential is loaded (caller decides freshness)."""
        cache_path = tmp_path / "sheet.pull.json"
        cred = _make_sa_cred(expires_at=time.time() - 100)
        cache_path.write_text(json.dumps(cred.to_dict()))

        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/sa.json")
        result = manager._load_cached_credential(cache_path)
        assert result is not None
        assert result.is_valid() is False

    def test_load_cached_credential_invalid_json(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "sheet.pull.json"
        cache_path.write_text("not-json")
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/sa.json")
        assert manager._load_cached_credential(cache_path) is None

    def test_save_credential_creates_secure_file(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "creds" / "sheet.pull.json"
        cred = _make_sa_cred(token="fresh-tok", expires_at=time.time() + 3600)
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/sa.json")
        manager._save_credential(cache_path, cred)

        assert cache_path.exists()
        import stat as stat_module

        mode = cache_path.stat().st_mode
        assert mode & 0o777 == stat_module.S_IRUSR | stat_module.S_IWUSR

        data = json.loads(cache_path.read_text())
        assert data["token"] == "fresh-tok"

    def test_credential_cache_path_uses_cmd_type(self) -> None:
        env = {"EXTRASUITE_SERVER_URL": "https://srv.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            manager = CredentialsManager()
        path = manager._credential_cache_path("sheet.pull")
        assert path.name == "sheet.pull.json"
        assert path.parent == CredentialsManager.CREDENTIALS_CACHE_DIR


# ---------------------------------------------------------------------------
# TestGetCredentialExtraSuite
# ---------------------------------------------------------------------------


class TestGetCredentialExtraSuite:
    """Tests for get_credential() in ExtraSuite (v2 session) mode."""

    def _make_v2_manager(self) -> CredentialsManager:
        env = {"EXTRASUITE_SERVER_URL": "https://myserver.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            return CredentialsManager()

    def test_get_credential_uses_cache(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()
        cred = _make_sa_cred(token="cached-tok", expires_at=time.time() + 3600)
        cache_path = tmp_path / "sheet.pull.json"
        cache_path.write_text(json.dumps(cred.to_dict()))

        with mock.patch.object(
            manager, "_credential_cache_path", return_value=cache_path
        ):
            result = manager.get_credential(
                command={
                    "type": "sheet.pull",
                    "file_url": "https://docs.google.com/...",
                },
                reason="Pulling sheet",
            )
        assert result.token == "cached-tok"

    def test_get_credential_force_refresh_ignores_cache(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()
        cached_cred = _make_sa_cred(token="old-tok", expires_at=time.time() + 3600)
        cache_path = tmp_path / "sheet.pull.json"
        cache_path.write_text(json.dumps(cached_cred.to_dict()))

        fresh_cred = _make_sa_cred(token="fresh-tok")
        with (
            mock.patch.object(
                manager, "_credential_cache_path", return_value=cache_path
            ),
            mock.patch.object(
                manager, "_get_extrasuite_credential", return_value=fresh_cred
            ) as mock_get,
        ):
            result = manager.get_credential(
                command={"type": "sheet.pull"},
                reason="Forced refresh",
                force_refresh=True,
            )
        mock_get.assert_called_once()
        assert result.token == "fresh-tok"

    def test_get_credential_v2_session_exchange(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()
        cache_path = tmp_path / "sheet.pull.json"

        valid_session = SessionToken(
            raw_token="my-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        mock_response = _v2_token_response("v2-access-token")

        with (
            mock.patch.object(
                manager, "_credential_cache_path", return_value=cache_path
            ),
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
        ):
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

    def test_get_credential_expired_cache_re_exchanges(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()
        expired_cred = _make_sa_cred(token="expired-tok", expires_at=time.time() - 100)
        cache_path = tmp_path / "sheet.pull.json"
        cache_path.write_text(json.dumps(expired_cred.to_dict()))

        valid_session = SessionToken(
            raw_token="my-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        mock_response = _v2_token_response("fresh-tok")

        with (
            mock.patch.object(
                manager, "_credential_cache_path", return_value=cache_path
            ),
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.get_credential(
                command={"type": "sheet.pull"},
                reason="Re-pull",
            )

        assert result.token == "fresh-tok"


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

    def test_service_account_uses_cache(self, tmp_path: Path) -> None:
        cred = _make_sa_cred(token="cached-sa-token", expires_at=time.time() + 3600)
        cache_path = tmp_path / "sheet.pull.json"
        cache_path.write_text(json.dumps(cred.to_dict()))

        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/path/to/sa.json")

        with mock.patch.object(
            manager, "_credential_cache_path", return_value=cache_path
        ):
            result = manager.get_credential(
                command={"type": "sheet.pull"}, reason="Test"
            )

        assert result.token == "cached-sa-token"

    def test_service_account_missing_google_auth(self, tmp_path: Path) -> None:
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(service_account_path="/path/to/sa.json")

        cache_path = tmp_path / "sheet.pull.json"
        try:
            import google.auth  # noqa: F401

            pytest.skip("google-auth is installed, cannot test ImportError case")
        except ImportError:
            with (
                mock.patch.object(
                    manager, "_credential_cache_path", return_value=cache_path
                ),
                pytest.raises(ImportError, match="google-auth"),
            ):
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
# TestCredentialsManagerIntegration
# ---------------------------------------------------------------------------


class TestCredentialsManagerIntegration:
    """Integration-style tests for complete flows."""

    def test_full_extrasuite_flow_with_cached_credential(self, tmp_path: Path) -> None:
        """Complete flow: load from file cache, return credential."""
        cache_path = tmp_path / "sheet.pull.json"
        cred = _make_sa_cred(token="cached-access-token", expires_at=time.time() + 3600)
        cache_path.write_text(json.dumps(cred.to_dict()))

        manager = CredentialsManager(server_url="https://auth.example.com")

        with mock.patch.object(
            manager, "_credential_cache_path", return_value=cache_path
        ):
            result = manager.get_credential(
                command={
                    "type": "sheet.pull",
                    "file_url": "https://docs.google.com/...",
                },
                reason="Test: pulling spreadsheet data",
            )

        assert result.token == "cached-access-token"
        assert result.service_account_email == "sa@example.com"
        assert result.is_valid()

    def test_expired_cache_triggers_session_exchange(self, tmp_path: Path) -> None:
        """Expired cache should trigger a fresh session-backed credential exchange."""
        cache_path = tmp_path / "sheet.pull.json"
        expired_cred = _make_sa_cred(
            token="expired-token", expires_at=time.time() - 100
        )
        cache_path.write_text(json.dumps(expired_cred.to_dict()))

        manager = CredentialsManager(server_url="https://auth.example.com")
        valid_session = SessionToken(
            raw_token="session-token",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        mock_response = _v2_token_response("fresh-token")

        with (
            mock.patch.object(
                manager, "_credential_cache_path", return_value=cache_path
            ),
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager.get_credential(
                command={"type": "sheet.pull"},
                reason="Test: refresh after token expiry",
            )

        assert result.token == "fresh-token"

        # Verify file was updated
        stored = json.loads(cache_path.read_text())
        assert stored["token"] == "fresh-token"


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
# TestSessionTokenCache
# ---------------------------------------------------------------------------


class TestSessionTokenCache:
    """Tests for session token file caching."""

    def _make_manager(self) -> CredentialsManager:
        env = {"EXTRASUITE_SERVER_URL": "https://myserver.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            return CredentialsManager()

    def test_load_session_token_no_file(self, tmp_path: Path) -> None:
        manager = self._make_manager()
        with mock.patch.object(
            CredentialsManager, "SESSION_CACHE_PATH", tmp_path / "session.json"
        ):
            assert manager._load_session_token() is None

    def test_load_session_token_valid(self, tmp_path: Path) -> None:
        session_path = tmp_path / "session.json"
        session_data = {
            "raw_token": "my-raw-token",
            "email": "user@example.com",
            "expires_at": time.time() + 86400,
        }
        session_path.write_text(json.dumps(session_data))

        manager = self._make_manager()
        with mock.patch.object(CredentialsManager, "SESSION_CACHE_PATH", session_path):
            token = manager._load_session_token()
        assert token is not None
        assert token.raw_token == "my-raw-token"
        assert token.email == "user@example.com"

    def test_load_session_token_expired(self, tmp_path: Path) -> None:
        session_path = tmp_path / "session.json"
        session_data = {
            "raw_token": "my-raw-token",
            "email": "user@example.com",
            "expires_at": time.time() - 100,
        }
        session_path.write_text(json.dumps(session_data))

        manager = self._make_manager()
        with mock.patch.object(CredentialsManager, "SESSION_CACHE_PATH", session_path):
            assert manager._load_session_token() is None

    def test_save_session_token(self, tmp_path: Path) -> None:
        session_path = tmp_path / "session.json"
        manager = self._make_manager()
        token = SessionToken(
            raw_token="my-raw-token",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        with mock.patch.object(CredentialsManager, "SESSION_CACHE_PATH", session_path):
            manager._save_session_token(token)

        assert session_path.exists()
        import stat as stat_module

        mode = session_path.stat().st_mode
        assert mode & 0o777 == stat_module.S_IRUSR | stat_module.S_IWUSR

        stored = json.loads(session_path.read_text())
        assert stored["raw_token"] == "my-raw-token"
        assert stored["email"] == "user@example.com"


# ---------------------------------------------------------------------------
# TestV2SessionFlow
# ---------------------------------------------------------------------------


class TestV2SessionFlow:
    """Tests for v2 session-token auth protocol."""

    def _make_v2_manager(self) -> CredentialsManager:
        env = {"EXTRASUITE_SERVER_URL": "https://myserver.example.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            return CredentialsManager()

    def test_get_or_create_session_token_returns_cached(self) -> None:
        manager = self._make_v2_manager()
        valid_session = SessionToken(
            raw_token="cached-session-token",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        with mock.patch.object(
            manager, "_load_session_token", return_value=valid_session
        ):
            result = manager._get_or_create_session_token()
        assert result.raw_token == "cached-session-token"

    def test_get_or_create_session_token_creates_new_when_no_cache(
        self, tmp_path: Path
    ) -> None:
        manager = self._make_v2_manager()
        session_path = tmp_path / "session.json"

        mock_exchange_response = {
            "session_token": "new-session-token",
            "email": "user@example.com",
            "expires_at": "2026-12-31T00:00:00+00:00",
        }

        with (
            mock.patch.object(manager, "_load_session_token", return_value=None),
            mock.patch.object(
                manager, "_run_browser_flow_for_session", return_value="test-auth-code"
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
            mock.patch.object(CredentialsManager, "SESSION_CACHE_PATH", session_path),
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_exchange_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager._get_or_create_session_token()

        assert result.raw_token == "new-session-token"
        assert result.email == "user@example.com"

    def test_get_or_create_session_token_force_skips_cache(
        self, tmp_path: Path
    ) -> None:
        manager = self._make_v2_manager()
        session_path = tmp_path / "session.json"
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
            mock.patch.object(CredentialsManager, "SESSION_CACHE_PATH", session_path),
        ):
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps(mock_exchange_response).encode()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = manager._get_or_create_session_token(force=True)

        assert result.raw_token == "new-token"

    def test_exchange_session_for_credential_success(self) -> None:
        """_exchange_session_for_credential returns raw response dict."""
        manager = self._make_v2_manager()
        session = SessionToken(
            raw_token="my-session-token",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )

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
        manager = self._make_v2_manager()
        session = SessionToken(
            raw_token="expired-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )

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

    def test_get_credential_v2_uses_session_exchange(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()
        cache_path = tmp_path / "sheet.pull.json"
        valid_session = SessionToken(
            raw_token="my-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        mock_response = _v2_token_response("v2-access-token")

        with (
            mock.patch.object(
                manager, "_credential_cache_path", return_value=cache_path
            ),
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
        ):
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

    def test_get_credential_dwd_v2_uses_session_exchange(self, tmp_path: Path) -> None:
        """get_credential() for a DWD command type works via session exchange."""
        manager = self._make_v2_manager()
        cache_path = tmp_path / "gmail.compose.json"
        valid_session = SessionToken(
            raw_token="my-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )
        mock_response = _v2_token_response("dwd-access-token", kind="bearer_dwd")
        mock_response["command_type"] = "gmail.compose"

        with (
            mock.patch.object(
                manager, "_credential_cache_path", return_value=cache_path
            ),
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ),
            mock.patch("urllib.request.urlopen") as mock_urlopen,
        ):
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
                    "cc": [],
                },
                reason="Test: send email",
            )

        assert result.token == "dwd-access-token"
        assert result.kind == "bearer_dwd"

    def test_login_public_method_calls_get_or_create(self) -> None:
        manager = self._make_v2_manager()
        valid_session = SessionToken(
            raw_token="new-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )

        with (
            mock.patch.object(manager, "_revoke_and_clear_session") as mock_revoke,
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ) as mock_create,
        ):
            result = manager.login(force=True)

        mock_revoke.assert_called_once()
        mock_create.assert_called_once_with(force=True)
        assert result.raw_token == "new-session"

    def test_login_without_force_does_not_revoke(self) -> None:
        manager = self._make_v2_manager()
        valid_session = SessionToken(
            raw_token="existing-session",
            email="user@example.com",
            expires_at=time.time() + 86400,
        )

        with (
            mock.patch.object(manager, "_revoke_and_clear_session") as mock_revoke,
            mock.patch.object(
                manager, "_get_or_create_session_token", return_value=valid_session
            ),
        ):
            manager.login(force=False)

        mock_revoke.assert_not_called()

    def test_logout_clears_local_caches(self, tmp_path: Path) -> None:
        session_path = tmp_path / "session.json"
        cred_dir = tmp_path / "credentials"
        cred_dir.mkdir()
        cred_file = cred_dir / "sheet.pull.json"

        session_path.write_text(
            '{"raw_token":"t","email":"u@e.com","expires_at":9999999999}'
        )
        cred = _make_sa_cred()
        cred_file.write_text(json.dumps(cred.to_dict()))

        manager = self._make_v2_manager()

        with (
            mock.patch.object(CredentialsManager, "SESSION_CACHE_PATH", session_path),
            mock.patch.object(CredentialsManager, "CREDENTIALS_CACHE_DIR", cred_dir),
            mock.patch.object(manager, "_revoke_and_clear_session") as mock_revoke,
        ):
            manager.logout()

        mock_revoke.assert_called_once()
        assert not cred_file.exists()

    def test_status_returns_active_session_info(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()
        valid_session = SessionToken(
            raw_token="my-token",
            email="user@example.com",
            expires_at=time.time() + 86400 * 5,
        )

        with (
            mock.patch.object(
                manager, "_load_session_token", return_value=valid_session
            ),
            mock.patch.object(
                CredentialsManager, "CREDENTIALS_CACHE_DIR", tmp_path / "empty"
            ),
        ):
            info = manager.status()

        assert info["session"] is not None
        assert info["session"]["active"] is True
        assert info["session"]["email"] == "user@example.com"
        assert info["session"]["days_remaining"] in (4, 5)

    def test_status_returns_none_when_no_session(self, tmp_path: Path) -> None:
        manager = self._make_v2_manager()

        with (
            mock.patch.object(manager, "_load_session_token", return_value=None),
            mock.patch.object(
                CredentialsManager, "CREDENTIALS_CACHE_DIR", tmp_path / "empty"
            ),
        ):
            info = manager.status()

        assert info["session"] is None

    def test_find_free_port(self) -> None:
        port = CredentialsManager._find_free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535
