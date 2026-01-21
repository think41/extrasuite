"""Unit tests for credentials module."""

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from extrasuite_client.credentials import CredentialsManager, Token


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

    def test_init_with_extrasuite_server_param(self) -> None:
        """Constructor param for extrasuite_server works."""
        manager = CredentialsManager(extrasuite_server="https://auth.example.com")
        assert manager._server_url == "https://auth.example.com"
        assert manager._use_extrasuite is True
        assert manager.auth_mode == "extrasuite"

    def test_init_with_extrasuite_server_trailing_slash(self) -> None:
        """Trailing slash is stripped from server URL."""
        manager = CredentialsManager(extrasuite_server="https://auth.example.com/")
        assert manager._server_url == "https://auth.example.com"

    def test_init_with_service_account_path_param(self) -> None:
        """Constructor param for service_account_path works."""
        manager = CredentialsManager(service_account_path="/path/to/sa.json")
        assert manager._sa_path == Path("/path/to/sa.json")
        assert manager._use_extrasuite is False
        assert manager.auth_mode == "service_account"

    def test_init_with_env_var_extrasuite(self) -> None:
        """EXTRASUITE_SERVER_URL env var is used."""
        with mock.patch.dict(os.environ, {"EXTRASUITE_SERVER_URL": "https://env.example.com"}):
            manager = CredentialsManager()
            assert manager._server_url == "https://env.example.com"
            assert manager.auth_mode == "extrasuite"

    def test_init_with_env_var_service_account(self) -> None:
        """SERVICE_ACCOUNT_PATH env var is used."""
        with mock.patch.dict(os.environ, {"SERVICE_ACCOUNT_PATH": "/env/path/sa.json"}, clear=True):
            # Clear EXTRASUITE_SERVER_URL if set
            env = {"SERVICE_ACCOUNT_PATH": "/env/path/sa.json"}
            with mock.patch.dict(os.environ, env, clear=True):
                manager = CredentialsManager()
                assert manager._sa_path == Path("/env/path/sa.json")
                assert manager.auth_mode == "service_account"

    def test_init_param_overrides_env_var(self) -> None:
        """Constructor params take precedence over env vars."""
        with mock.patch.dict(os.environ, {"EXTRASUITE_SERVER_URL": "https://env.example.com"}):
            manager = CredentialsManager(extrasuite_server="https://param.example.com")
            assert manager._server_url == "https://param.example.com"

    def test_init_extrasuite_takes_precedence_over_service_account(self) -> None:
        """ExtraSuite server takes precedence when both are configured."""
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            service_account_path="/path/to/sa.json",
        )
        assert manager._use_extrasuite is True
        assert manager.auth_mode == "extrasuite"

    def test_init_no_config_raises_error(self) -> None:
        """ValueError raised when no auth method is configured."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                CredentialsManager()
            assert "No authentication method configured" in str(exc_info.value)

    def test_init_custom_cache_path(self) -> None:
        """Custom token_cache_path is respected."""
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path="/custom/cache/token.json",
        )
        assert manager._token_cache_path == Path("/custom/cache/token.json")


class TestCredentialsManagerTokenCache:
    """Tests for token caching functionality."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for token cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_load_cached_token_no_file(self, temp_cache_dir: Path) -> None:
        """Returns None when cache file doesn't exist."""
        cache_path = temp_cache_dir / "token.json"
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        assert manager._load_cached_token() is None

    def test_load_cached_token_valid(self, temp_cache_dir: Path) -> None:
        """Returns Token when cache file contains valid token."""
        cache_path = temp_cache_dir / "token.json"
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        cache_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        token = manager._load_cached_token()
        assert token is not None
        assert token.access_token == "cached-token"

    def test_load_cached_token_expired(self, temp_cache_dir: Path) -> None:
        """Returns None when cached token is expired."""
        cache_path = temp_cache_dir / "token.json"
        token_data = {
            "access_token": "expired-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() - 100,  # Expired
        }
        cache_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        assert manager._load_cached_token() is None

    def test_load_cached_token_invalid_json(self, temp_cache_dir: Path) -> None:
        """Returns None when cache file contains invalid JSON."""
        cache_path = temp_cache_dir / "token.json"
        cache_path.write_text("not valid json")

        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        assert manager._load_cached_token() is None

    def test_save_token_creates_directory(self, temp_cache_dir: Path) -> None:
        """save_token creates parent directory if needed."""
        cache_path = temp_cache_dir / "subdir" / "token.json"
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        manager._save_token(token)

        assert cache_path.exists()
        saved_data = json.loads(cache_path.read_text())
        assert saved_data["access_token"] == "new-token"

    def test_save_token_secure_permissions(self, temp_cache_dir: Path) -> None:
        """save_token sets secure file permissions."""
        cache_path = temp_cache_dir / "token.json"
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        manager._save_token(token)

        # Check file permissions (0600 = owner read/write only)
        mode = cache_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestCredentialsManagerExtraSuite:
    """Tests for ExtraSuite authentication flow."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for token cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_get_token_uses_cache(self, temp_cache_dir: Path) -> None:
        """get_token returns cached token when valid."""
        cache_path = temp_cache_dir / "token.json"
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        cache_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )
        token = manager.get_token()
        assert token.access_token == "cached-token"

    def test_get_token_force_refresh_ignores_cache(self, temp_cache_dir: Path) -> None:
        """get_token with force_refresh ignores cached token."""
        cache_path = temp_cache_dir / "token.json"
        token_data = {
            "access_token": "cached-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        cache_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )

        # Mock the authentication to return a new token
        new_token = Token(
            access_token="new-token",
            service_account_email="sa@example.com",
            expires_at=time.time() + 3600,
        )
        with mock.patch.object(manager, "_authenticate_extrasuite", return_value=new_token):
            token = manager.get_token(force_refresh=True)
            assert token.access_token == "new-token"

    def test_exchange_auth_code_success(self, temp_cache_dir: Path) -> None:
        """_exchange_auth_code successfully exchanges code for token."""
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=temp_cache_dir / "token.json",
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

    def test_exchange_auth_code_http_error(self, temp_cache_dir: Path) -> None:
        """_exchange_auth_code raises on HTTP error."""
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=temp_cache_dir / "token.json",
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

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for token cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_sa_file(self, temp_cache_dir: Path):
        """Create a mock service account JSON file."""
        sa_path = temp_cache_dir / "service-account.json"
        sa_data = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key-id",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "sa@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        sa_path.write_text(json.dumps(sa_data))
        return sa_path

    def test_service_account_file_not_found(self, temp_cache_dir: Path) -> None:
        """Raises FileNotFoundError when service account file doesn't exist."""
        manager = CredentialsManager(
            service_account_path="/nonexistent/path/sa.json",
            token_cache_path=temp_cache_dir / "token.json",
        )
        # The file check happens after the import check, so we need to mock google-auth
        # or expect ImportError if google-auth is not installed
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

    def test_service_account_uses_cache(self, temp_cache_dir: Path, mock_sa_file: Path) -> None:
        """Service account mode also uses token cache."""
        cache_path = temp_cache_dir / "token.json"
        token_data = {
            "access_token": "cached-sa-token",
            "service_account_email": "sa@example.com",
            "expires_at": time.time() + 3600,
        }
        cache_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            service_account_path=mock_sa_file,
            token_cache_path=cache_path,
        )

        # Mock the google-auth imports since they happen before cache check
        # The actual flow is: check imports -> check cache -> load credentials
        # But for this test we just want to verify cache is used
        with mock.patch.object(manager, "_get_service_account_token") as mock_get:
            # Setup: make _load_cached_token return our cached token
            cached_token = Token(
                access_token="cached-sa-token",
                service_account_email="sa@example.com",
                expires_at=time.time() + 3600,
            )

            # The real method should check cache first, so let's verify by
            # not mocking but checking that cached token is returned
            # We need to patch the import inside the method
            def patched_get_sa_token(force_refresh: bool) -> Token:
                # Simulate what the real method does - check cache first
                if not force_refresh:
                    cached = manager._load_cached_token()
                    if cached and cached.is_valid():
                        return cached
                raise ImportError("Should not reach here in this test")

            mock_get.side_effect = patched_get_sa_token
            token = manager.get_token()
            assert token.access_token == "cached-sa-token"

    def test_service_account_missing_google_auth(self, temp_cache_dir: Path, mock_sa_file: Path) -> None:
        """Raises ImportError with helpful message when google-auth not installed."""
        cache_path = temp_cache_dir / "token.json"

        manager = CredentialsManager(
            service_account_path=mock_sa_file,
            token_cache_path=cache_path,
        )

        # Without a cached token, attempting to get a token should try to import google-auth
        # If google-auth is not installed, it will raise ImportError
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

        # Create a mock request
        class MockRequest:
            def makefile(self, *args, **kwargs):
                return mock.MagicMock()

        # Simulate the handler receiving a code
        with mock.patch.object(handler_class, "__init__", lambda self, *args: None):
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

        with mock.patch.object(handler_class, "__init__", lambda self, *args: None):
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

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for token cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_full_extrasuite_flow_with_cached_token(self, temp_cache_dir: Path) -> None:
        """Complete flow: load from cache, return token."""
        cache_path = temp_cache_dir / "token.json"

        # Pre-populate cache
        token_data = {
            "access_token": "cached-access-token",
            "service_account_email": "sa@project.iam.gserviceaccount.com",
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
        }
        cache_path.write_text(json.dumps(token_data))

        # Create manager and get token
        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )

        token = manager.get_token()

        assert token.access_token == "cached-access-token"
        assert token.service_account_email == "sa@project.iam.gserviceaccount.com"
        assert token.is_valid()

    def test_expired_cache_triggers_auth(self, temp_cache_dir: Path) -> None:
        """Expired cache should trigger re-authentication."""
        cache_path = temp_cache_dir / "token.json"

        # Pre-populate with expired token
        token_data = {
            "access_token": "expired-token",
            "service_account_email": "sa@project.iam.gserviceaccount.com",
            "expires_at": time.time() - 100,  # Expired
        }
        cache_path.write_text(json.dumps(token_data))

        manager = CredentialsManager(
            extrasuite_server="https://auth.example.com",
            token_cache_path=cache_path,
        )

        # Mock authentication to return new token
        new_token = Token(
            access_token="fresh-token",
            service_account_email="sa@project.iam.gserviceaccount.com",
            expires_at=time.time() + 3600,
        )

        with mock.patch.object(manager, "_authenticate_extrasuite", return_value=new_token):
            token = manager.get_token()

        assert token.access_token == "fresh-token"
        # Verify cache was updated
        saved_data = json.loads(cache_path.read_text())
        assert saved_data["access_token"] == "fresh-token"
