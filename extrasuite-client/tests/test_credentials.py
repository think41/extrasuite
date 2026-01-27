"""Unit tests for credentials module."""

import json
import os
import threading
import time
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from extrasuite_client.credentials import (
    KEYRING_SERVICE,
    KEYRING_USERNAME,
    CredentialsManager,
    Token,
    authenticate,
)


class TestToken:
    """Tests for Token dataclass."""

    def test_is_valid_with_valid_token(self) -> None:
        """Token with future expiry is valid."""
        token = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,  # 1 hour from now
        )
        assert token.is_valid() is True

    def test_is_valid_with_expired_token(self) -> None:
        """Token with past expiry is invalid."""
        token = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=time.time() - 100,  # 100 seconds ago
        )
        assert token.is_valid() is False

    def test_is_valid_respects_buffer(self) -> None:
        """Token expiring within buffer period is invalid."""
        token = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 30,  # 30 seconds from now
        )
        # With default 60 second buffer, this should be invalid
        assert token.is_valid(buffer_seconds=60) is False
        # With 10 second buffer, this should be valid
        assert token.is_valid(buffer_seconds=10) is True

    def test_expires_in_seconds(self) -> None:
        """expires_in_seconds returns correct value."""
        future_time = time.time() + 3600
        token = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=future_time,
        )
        # Should be approximately 3600, allow small delta for test execution time
        assert 3598 <= token.expires_in_seconds() <= 3600

    def test_expires_in_seconds_with_expired_token(self) -> None:
        """expires_in_seconds returns 0 for expired token."""
        token = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=time.time() - 100,
        )
        assert token.expires_in_seconds() == 0

    def test_to_dict(self) -> None:
        """to_dict returns correct dictionary."""
        token = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=1234567890.0,
        )
        result = token.to_dict()
        assert result == {
            "access_token": "test-token",
            "service_account_email": "sa@example.com",
            "expires_at": 1234567890.0,
            "token_type": "Bearer",
        }

    def test_from_dict(self) -> None:
        """from_dict creates Token correctly."""
        data = {
            "access_token": "test-token",
            "service_account_email": "sa@example.com",
            "expires_at": 1234567890.0,
        }
        token = Token.from_dict(data)
        assert token.access_token == "test-token"
        assert token.service_account_email == "sa@example.com"
        assert token.expires_at == 1234567890.0

    def test_from_dict_missing_email(self) -> None:
        """from_dict handles missing service_account_email."""
        data = {
            "access_token": "test-token",
            "expires_at": 1234567890.0,
        }
        token = Token.from_dict(data)
        assert token.service_account_email == ""

    def test_roundtrip(self) -> None:
        """Token survives to_dict/from_dict roundtrip."""
        original = Token(
            access_token="test-token",
            service_account_email="sa@example.com",
            expires_at=1234567890.0,
        )
        restored = Token.from_dict(original.to_dict())
        assert restored.access_token == original.access_token
        assert restored.service_account_email == original.service_account_email
        assert restored.expires_at == original.expires_at


class TestCredentialsManagerInit:
    """Tests for CredentialsManager initialization."""

    def test_init_with_auth_and_exchange_urls(self) -> None:
        """Constructor params for auth_url and exchange_url work."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        assert manager._auth_url == "https://auth.example.com/api/token/auth"
        assert manager._exchange_url == "https://auth.example.com/api/token/exchange"
        assert manager._use_extrasuite is True
        assert manager.auth_mode == "extrasuite"

    def test_init_with_service_account_path_param(self) -> None:
        """Constructor param for service_account_path works."""
        with mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")):
            manager = CredentialsManager(service_account_path="/path/to/sa.json")
            assert manager._sa_path == Path("/path/to/sa.json")
            assert manager._use_extrasuite is False
            assert manager.auth_mode == "service_account"

    def test_init_with_env_vars(self) -> None:
        """EXTRASUITE_AUTH_URL and EXTRASUITE_EXCHANGE_URL env vars are used."""
        env = {
            "EXTRASUITE_AUTH_URL": "https://env.example.com/auth",
            "EXTRASUITE_EXCHANGE_URL": "https://env.example.com/exchange",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            manager = CredentialsManager()
            assert manager._auth_url == "https://env.example.com/auth"
            assert manager._exchange_url == "https://env.example.com/exchange"
            assert manager.auth_mode == "extrasuite"

    def test_init_with_env_var_service_account(self) -> None:
        """SERVICE_ACCOUNT_PATH env var is used."""
        with (
            mock.patch.dict(os.environ, {"SERVICE_ACCOUNT_PATH": "/env/path/sa.json"}, clear=True),
            mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")),
        ):
            manager = CredentialsManager()
            assert manager._sa_path == Path("/env/path/sa.json")
            assert manager.auth_mode == "service_account"

    def test_init_param_overrides_env_var(self) -> None:
        """Constructor params take precedence over env vars."""
        env = {
            "EXTRASUITE_AUTH_URL": "https://env.example.com/auth",
            "EXTRASUITE_EXCHANGE_URL": "https://env.example.com/exchange",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            manager = CredentialsManager(
                auth_url="https://param.example.com/auth",
                exchange_url="https://param.example.com/exchange",
            )
            assert manager._auth_url == "https://param.example.com/auth"
            assert manager._exchange_url == "https://param.example.com/exchange"

    def test_init_extrasuite_takes_precedence_over_service_account(self) -> None:
        """ExtraSuite protocol takes precedence when both are configured."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/auth",
            exchange_url="https://auth.example.com/exchange",
            service_account_path="/path/to/sa.json",
        )
        assert manager._use_extrasuite is True
        assert manager.auth_mode == "extrasuite"

    def test_init_no_config_raises_error(self) -> None:
        """ValueError raised when no auth method is configured."""
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")),
        ):
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager()
            assert "No authentication method configured" in str(exc_info.value)

    def test_init_partial_urls_raises_error(self) -> None:
        """ValueError raised when only one URL is provided."""
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")),
        ):
            # Missing exchange_url
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager(auth_url="https://auth.example.com/auth")
            assert "exchange_url is missing" in str(exc_info.value)

            # Missing auth_url
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager(exchange_url="https://auth.example.com/exchange")
            assert "auth_url is missing" in str(exc_info.value)


class TestCredentialsManagerKeyringCache:
    """Tests for keyring-based token caching functionality."""

    def test_load_cached_token_no_entry(self) -> None:
        """Returns None when no token in keyring."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        with mock.patch("keyring.get_password", return_value=None):
            assert manager._load_cached_token() is None

    def test_load_cached_token_valid(self) -> None:
        """Returns Token when keyring contains valid token."""
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        with mock.patch("keyring.get_password", return_value=json.dumps(token_data)):
            token = manager._load_cached_token()
            assert token is not None
            assert token.access_token == "cached-token"

    def test_load_cached_token_expired(self) -> None:
        """Returns None when cached token is expired."""
        token_data = {
            "access_token": "expired-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() - 100,  # Expired
        }
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        with mock.patch("keyring.get_password", return_value=json.dumps(token_data)):
            assert manager._load_cached_token() is None

    def test_load_cached_token_invalid_json(self) -> None:
        """Returns None when keyring contains invalid JSON."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        with mock.patch("keyring.get_password", return_value="not valid json"):
            assert manager._load_cached_token() is None

    def test_save_token_to_keyring(self) -> None:
        """save_token stores token in keyring."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        with mock.patch("keyring.set_password") as mock_set:
            manager._save_token(token)
            mock_set.assert_called_once()
            call_args = mock_set.call_args
            assert call_args[0][0] == KEYRING_SERVICE
            assert call_args[0][1] == KEYRING_USERNAME
            # Verify the stored JSON is valid
            stored_data = json.loads(call_args[0][2])
            assert stored_data["access_token"] == "new-token"


class TestCredentialsManagerExtraSuite:
    """Tests for ExtraSuite authentication flow."""

    def test_get_token_uses_cache(self) -> None:
        """get_token returns cached token when valid."""
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        with mock.patch("keyring.get_password", return_value=json.dumps(token_data)):
            token = manager.get_token()
            assert token.access_token == "cached-token"

    def test_get_token_force_refresh_ignores_cache(self) -> None:
        """get_token with force_refresh ignores cached token."""
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        # Mock the authentication to return a new token
        new_token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        with (
            mock.patch("keyring.get_password", return_value=json.dumps(token_data)),
            mock.patch("keyring.set_password"),
            mock.patch.object(manager, "_authenticate_extrasuite", return_value=new_token),
        ):
            token = manager.get_token(force_refresh=True)
            assert token.access_token == "new-token"

    def test_exchange_auth_code_success(self) -> None:
        """_exchange_auth_code successfully exchanges code for token."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        # Mock response from server
        mock_response = {
            "token": "exchanged-token",
            "expires_at": "2025-01-01T12:00:00Z",
            "service_account": "sa@example.com",
        }

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_response_obj = mock.MagicMock()
            mock_response_obj.read.return_value = json.dumps(mock_response).encode()
            mock_response_obj.__enter__ = mock.MagicMock(return_value=mock_response_obj)
            mock_response_obj.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response_obj

            token = manager._exchange_auth_code("test-code")

            assert token.access_token == "exchanged-token"
            assert token.service_account_email == "sa@example.com"

    def test_exchange_auth_code_http_error(self) -> None:
        """_exchange_auth_code raises on HTTP error."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            error = urllib.error.HTTPError(
                url="https://auth.example.com/api/token/exchange",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=mock.MagicMock(read=lambda: b"Invalid code"),
            )
            mock_urlopen.side_effect = error

            with pytest.raises(Exception) as exc_info:
                manager._exchange_auth_code("bad-code")
            assert "Token exchange failed" in str(exc_info.value)

    def test_find_free_port(self) -> None:
        """_find_free_port returns a valid port."""
        port = CredentialsManager._find_free_port()
        assert 1024 <= port <= 65535


class TestCredentialsManagerServiceAccount:
    """Tests for service account authentication."""

    def test_service_account_file_not_found(self) -> None:
        """Raises FileNotFoundError when service account file doesn't exist."""
        with mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")):
            manager = CredentialsManager(
                service_account_path="/nonexistent/path/sa.json",
            )
        # Mock keyring to return no cached token
        with mock.patch("keyring.get_password", return_value=None):
            # The file check happens after the import check
            try:
                import google.auth  # noqa: F401

                google_auth_available = True
            except ImportError:
                google_auth_available = False

            if google_auth_available:
                with pytest.raises(FileNotFoundError):
                    manager.get_token()
            else:
                # Without google-auth, we get ImportError first
                with pytest.raises(ImportError):
                    manager.get_token()

    def test_service_account_uses_cache(self) -> None:
        """Service account mode also uses keyring cache."""
        token_data = {
            "access_token": "cached-sa-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        with mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")):
            manager = CredentialsManager(
                service_account_path="/path/to/sa.json",
            )
        with mock.patch("keyring.get_password", return_value=json.dumps(token_data)):
            token = manager.get_token()
            assert token.access_token == "cached-sa-token"

    def test_service_account_missing_google_auth(self) -> None:
        """Raises ImportError with helpful message when google-auth not installed."""
        with mock.patch.object(CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")):
            manager = CredentialsManager(
                service_account_path="/path/to/sa.json",
            )

        # Without a cached token, attempting to get a token should try to import google-auth
        with mock.patch("keyring.get_password", return_value=None):
            try:
                import google.auth  # noqa: F401

                # google-auth is installed, skip this test
                pytest.skip("google-auth is installed, cannot test ImportError case")
            except ImportError:
                # google-auth is not installed, this is the case we want to test
                with pytest.raises(ImportError) as exc_info:
                    manager.get_token()
                assert "google-auth" in str(exc_info.value)


class TestCredentialsManagerCallbackHandler:
    """Tests for the HTTP callback handler."""

    def test_callback_handler_receives_code(self) -> None:
        """Callback handler correctly receives auth code."""
        result_holder = {"code": None, "error": None, "done": False}
        result_lock = threading.Lock()

        handler_class = CredentialsManager._create_handler_class(result_holder, result_lock)

        # Simulate the handler receiving a code
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
        """Callback handler correctly handles error."""
        result_holder = {"code": None, "error": None, "done": False}
        result_lock = threading.Lock()

        handler_class = CredentialsManager._create_handler_class(result_holder, result_lock)

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


class TestCredentialsManagerIntegration:
    """Integration-style tests for complete flows."""

    def test_full_extrasuite_flow_with_cached_token(self) -> None:
        """Complete flow: load from keyring cache, return token."""
        token_data = {
            "access_token": "cached-access-token",
            "service_account_email": "sa@project.iam.gserviceaccount.com",
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
        }

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        with mock.patch("keyring.get_password", return_value=json.dumps(token_data)):
            token = manager.get_token()

        assert token.access_token == "cached-access-token"
        assert token.service_account_email == "sa@project.iam.gserviceaccount.com"
        assert token.is_valid()

    def test_expired_cache_triggers_auth(self) -> None:
        """Expired cache should trigger re-authentication."""
        expired_token_data = {
            "access_token": "expired-token",
            "service_account_email": "sa@project.iam.gserviceaccount.com",
            "expires_at": time.time() - 100,  # Expired
        }

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        # Mock authentication to return new token
        new_token = Token(
            access_token="fresh-token",
            service_account_email="sa@project.iam.gserviceaccount.com",
            expires_at=time.time() + 3600,
        )

        with (
            mock.patch("keyring.get_password", return_value=json.dumps(expired_token_data)),
            mock.patch("keyring.set_password") as mock_set,
            mock.patch.object(manager, "_authenticate_extrasuite", return_value=new_token),
        ):
            token = manager.get_token()

        assert token.access_token == "fresh-token"
        # Verify keyring was updated
        mock_set.assert_called_once()
        stored_data = json.loads(mock_set.call_args[0][2])
        assert stored_data["access_token"] == "fresh-token"


class TestAuthenticateFunction:
    """Tests for the authenticate() convenience function."""

    def test_authenticate_returns_token(self) -> None:
        """authenticate() returns a valid token."""
        token_data = {
            "access_token": "test-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        with (
            mock.patch.dict(
                os.environ,
                {
                    "EXTRASUITE_AUTH_URL": "https://auth.example.com/auth",
                    "EXTRASUITE_EXCHANGE_URL": "https://auth.example.com/exchange",
                },
            ),
            mock.patch("keyring.get_password", return_value=json.dumps(token_data)),
        ):
            token = authenticate()
            assert token.access_token == "test-token"

    def test_authenticate_with_explicit_urls(self) -> None:
        """authenticate() works with explicit URLs."""
        token_data = {
            "access_token": "explicit-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        with mock.patch("keyring.get_password", return_value=json.dumps(token_data)):
            token = authenticate(
                auth_url="https://explicit.example.com/auth",
                exchange_url="https://explicit.example.com/exchange",
            )
            assert token.access_token == "explicit-token"

    def test_authenticate_force_refresh(self) -> None:
        """authenticate() with force_refresh ignores cache."""
        cached_token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        new_token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )

        with (
            mock.patch("keyring.get_password", return_value=json.dumps(cached_token_data)),
            mock.patch("keyring.set_password"),
            mock.patch(
                "extrasuite_client.credentials.CredentialsManager._authenticate_extrasuite",
                return_value=new_token,
            ),
        ):
            token = authenticate(
                auth_url="https://auth.example.com/auth",
                exchange_url="https://auth.example.com/exchange",
                force_refresh=True,
            )
            assert token.access_token == "new-token"
