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
    CredentialsManager,
    OAuthToken,
    Token,
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
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
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
            mock.patch.dict(
                os.environ, {"SERVICE_ACCOUNT_PATH": "/env/path/sa.json"}, clear=True
            ),
            mock.patch.object(
                CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
            ),
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
            mock.patch.object(
                CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
            ),
        ):
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager()
            assert "No authentication method configured" in str(exc_info.value)

    def test_init_partial_urls_raises_error(self) -> None:
        """ValueError raised when only one URL is provided."""
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
            ),
        ):
            # Missing exchange_url
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager(auth_url="https://auth.example.com/auth")
            assert "exchange_url is missing" in str(exc_info.value)

            # Missing auth_url
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager(exchange_url="https://auth.example.com/exchange")
            assert "auth_url is missing" in str(exc_info.value)


class TestCredentialsManagerFileCache:
    """Tests for file-based token caching functionality."""

    def test_load_cached_token_no_file(self, tmp_path: Path) -> None:
        """Returns None when no token file exists."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=tmp_path / "token.json",
        )
        assert manager._load_cached_token() is None

    def test_load_cached_token_valid(self, tmp_path: Path) -> None:
        """Returns Token when file contains valid token."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        token_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )
        token = manager._load_cached_token()
        assert token is not None
        assert token.access_token == "cached-token"

    def test_load_cached_token_expired(self, tmp_path: Path) -> None:
        """Returns None when cached token is expired."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "expired-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() - 100,  # Expired
        }
        token_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )
        assert manager._load_cached_token() is None

    def test_load_cached_token_invalid_json(self, tmp_path: Path) -> None:
        """Returns None when file contains invalid JSON."""
        token_path = tmp_path / "token.json"
        token_path.write_text("not valid json")

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )
        assert manager._load_cached_token() is None

    def test_save_token_to_file(self, tmp_path: Path) -> None:
        """save_token stores token in file with secure permissions."""
        token_path = tmp_path / "extrasuite" / "token.json"
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )
        token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        manager._save_token(token)

        # Verify file was created
        assert token_path.exists()

        # Verify content
        stored_data = json.loads(token_path.read_text())
        assert stored_data["access_token"] == "new-token"

        # Verify permissions (0600 = owner read/write only)
        import stat

        mode = token_path.stat().st_mode
        assert mode & 0o777 == stat.S_IRUSR | stat.S_IWUSR


class TestCredentialsManagerExtraSuite:
    """Tests for ExtraSuite authentication flow."""

    def test_get_token_uses_cache(self, tmp_path: Path) -> None:
        """get_token returns cached token when valid."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        token_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )
        token = manager.get_token()
        assert token.access_token == "cached-token"

    def test_get_token_force_refresh_ignores_cache(self, tmp_path: Path) -> None:
        """get_token with force_refresh ignores cached token."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        token_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )

        # Mock the authentication to return a new token
        new_token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        with mock.patch.object(
            manager, "_authenticate_extrasuite", return_value=new_token
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

    def test_service_account_file_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when service account file doesn't exist."""
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(
                service_account_path="/nonexistent/path/sa.json",
                token_cache_path=tmp_path / "token.json",
            )
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

    def test_service_account_uses_cache(self, tmp_path: Path) -> None:
        """Service account mode also uses file cache."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "cached-sa-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        token_path.write_text(json.dumps(token_data))

        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(
                service_account_path="/path/to/sa.json",
                token_cache_path=token_path,
            )
        token = manager.get_token()
        assert token.access_token == "cached-sa-token"

    def test_service_account_missing_google_auth(self, tmp_path: Path) -> None:
        """Raises ImportError with helpful message when google-auth not installed."""
        with mock.patch.object(
            CredentialsManager, "GATEWAY_CONFIG_PATH", Path("/nonexistent")
        ):
            manager = CredentialsManager(
                service_account_path="/path/to/sa.json",
                token_cache_path=tmp_path / "token.json",
            )

        # Without a cached token, attempting to get a token should try to import google-auth
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

        handler_class = CredentialsManager._create_handler_class(
            result_holder, result_lock
        )

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


class TestCredentialsManagerIntegration:
    """Integration-style tests for complete flows."""

    def test_full_extrasuite_flow_with_cached_token(self, tmp_path: Path) -> None:
        """Complete flow: load from file cache, return token."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "cached-access-token",
            "service_account_email": "sa@project.iam.gserviceaccount.com",
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
        }
        token_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )

        token = manager.get_token()

        assert token.access_token == "cached-access-token"
        assert token.service_account_email == "sa@project.iam.gserviceaccount.com"
        assert token.is_valid()

    def test_expired_cache_triggers_auth(self, tmp_path: Path) -> None:
        """Expired cache should trigger re-authentication."""
        token_path = tmp_path / "token.json"
        expired_token_data = {
            "access_token": "expired-token",
            "service_account_email": "sa@project.iam.gserviceaccount.com",
            "expires_at": time.time() - 100,  # Expired
        }
        token_path.write_text(json.dumps(expired_token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
            token_cache_path=token_path,
        )

        # Mock authentication to return new token
        new_token = Token(
            access_token="fresh-token",
            service_account_email="sa@project.iam.gserviceaccount.com",
            expires_at=time.time() + 3600,
        )

        with mock.patch.object(
            manager, "_authenticate_extrasuite", return_value=new_token
        ):
            token = manager.get_token()

        assert token.access_token == "fresh-token"

        # Verify file was updated
        stored_data = json.loads(token_path.read_text())
        assert stored_data["access_token"] == "fresh-token"


class TestOAuthToken:
    """Tests for OAuthToken dataclass."""

    def test_is_valid_with_valid_token(self) -> None:
        """Token with future expiry is valid."""
        token = OAuthToken(
            access_token="test-token",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            expires_at=time.time() + 3600,
        )
        assert token.is_valid() is True

    def test_is_valid_with_expired_token(self) -> None:
        """Token with past expiry is invalid."""
        token = OAuthToken(
            access_token="test-token",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            expires_at=time.time() - 100,
        )
        assert token.is_valid() is False

    def test_to_dict(self) -> None:
        """to_dict returns correct dictionary."""
        token = OAuthToken(
            access_token="test-token",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            expires_at=1234567890.0,
        )
        result = token.to_dict()
        assert result["access_token"] == "test-token"
        assert result["scopes"] == ["https://www.googleapis.com/auth/gmail.send"]
        assert result["expires_at"] == 1234567890.0
        assert result["token_type"] == "Bearer"

    def test_roundtrip(self) -> None:
        """OAuthToken survives to_dict/from_dict roundtrip."""
        original = OAuthToken(
            access_token="test-token",
            scopes=[
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/calendar",
            ],
            expires_at=1234567890.0,
        )
        restored = OAuthToken.from_dict(original.to_dict())
        assert restored.access_token == original.access_token
        assert restored.scopes == original.scopes
        assert restored.expires_at == original.expires_at


class TestDelegationFlow:
    """Tests for delegation authentication flow."""

    def test_get_oauth_token_uses_cache(self, tmp_path: Path) -> None:
        """get_oauth_token returns cached token when valid and scopes match."""
        oauth_path = tmp_path / "oauth_token.json"
        token_data = {
            "access_token": "cached-oauth-token",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
            "expires_at": time.time() + 3600,
        }
        oauth_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        with mock.patch.object(CredentialsManager, "OAUTH_CACHE_PATH", oauth_path):
            token = manager.get_oauth_token(["gmail.send"])
            assert token.access_token == "cached-oauth-token"

    def test_get_oauth_token_ignores_cache_with_different_scopes(
        self, tmp_path: Path
    ) -> None:
        """get_oauth_token ignores cache when scopes don't match."""
        oauth_path = tmp_path / "oauth_token.json"
        token_data = {
            "access_token": "cached-oauth-token",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
            "expires_at": time.time() + 3600,
        }
        oauth_path.write_text(json.dumps(token_data))

        new_token = OAuthToken(
            access_token="new-oauth-token",
            scopes=[
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/calendar",
            ],
            expires_at=time.time() + 3600,
        )

        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        with (
            mock.patch.object(CredentialsManager, "OAUTH_CACHE_PATH", oauth_path),
            mock.patch.object(
                manager, "_authenticate_delegation", return_value=new_token
            ),
        ):
            token = manager.get_oauth_token(["gmail.send", "calendar"])
            assert token.access_token == "new-oauth-token"

    def test_exchange_delegation_code_success(self) -> None:
        """_exchange_delegation_code parses response correctly."""
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )

        mock_response = {
            "access_token": "delegated-token",
            "expires_at": "2025-01-01T12:00:00Z",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
        }

        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_response_obj = mock.MagicMock()
            mock_response_obj.read.return_value = json.dumps(mock_response).encode()
            mock_response_obj.__enter__ = mock.MagicMock(return_value=mock_response_obj)
            mock_response_obj.__exit__ = mock.MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response_obj

            token = manager._exchange_delegation_code(
                "test-code", "https://auth.example.com/api/delegation/exchange"
            )

            assert token.access_token == "delegated-token"
            assert token.scopes == ["https://www.googleapis.com/auth/gmail.send"]

    def test_resolve_scopes(self) -> None:
        """_resolve_scopes converts aliases to full URLs."""
        result = CredentialsManager._resolve_scopes(["gmail.send", "calendar"])
        assert result == [
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
        ]

    def test_resolve_scopes_passthrough(self) -> None:
        """_resolve_scopes passes through full URLs unchanged."""
        full_url = "https://www.googleapis.com/auth/gmail.send"
        result = CredentialsManager._resolve_scopes([full_url])
        assert result == [full_url]
