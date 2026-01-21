"""Credentials management for Google API access.

Supports two authentication modes:
1. ExtraSuite server - short-lived tokens via OAuth flow
2. Service account file - direct credentials from JSON key file
"""

from __future__ import annotations

import http.server
import json
import os
import select
import socket
import ssl
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Try to use certifi for SSL certificates (common on macOS)
try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


@dataclass
class Token:
    """Unified token structure for Google API access.

    Attributes:
        access_token: The OAuth2 access token for API calls.
        service_account_email: Email of the service account.
        expires_at: Unix timestamp when the token expires.
    """

    access_token: str
    service_account_email: str
    expires_at: float

    def is_valid(self, buffer_seconds: int = 60) -> bool:
        """Check if token is still valid with a safety buffer."""
        return time.time() < self.expires_at - buffer_seconds

    def expires_in_seconds(self) -> int:
        """Return seconds until token expires."""
        return max(0, int(self.expires_at - time.time()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "access_token": self.access_token,
            "service_account_email": self.service_account_email,
            "expires_at": self.expires_at,
            "token_type": "Bearer",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Token:
        """Create Token from dictionary."""
        return cls(
            access_token=data["access_token"],
            service_account_email=data.get("service_account_email", ""),
            expires_at=data["expires_at"],
        )


class CredentialsManager:
    """Manages credentials for Google API access.

    Supports two authentication modes:
    1. ExtraSuite server - obtains short-lived tokens via OAuth flow
    2. Service account file - uses credentials from a JSON key file

    Precedence order for configuration:
    1. extrasuite_server constructor parameter
    2. EXTRASUITE_SERVER_URL environment variable
    3. service_account_path constructor parameter
    4. SERVICE_ACCOUNT_PATH environment variable

    Args:
        extrasuite_server: URL of the ExtraSuite server (optional).
        service_account_path: Path to service account JSON file (optional).
        token_cache_path: Path to cache tokens. Defaults to
            ~/.config/extrasuite/token.json

    Example:
        # Using ExtraSuite server (via env var or constructor)
        manager = CredentialsManager(extrasuite_server="https://auth.example.com")
        token = manager.get_token()

        # Using service account file
        manager = CredentialsManager(service_account_path="/path/to/sa.json")
        token = manager.get_token()
    """

    DEFAULT_CACHE_PATH = Path.home() / ".config" / "extrasuite" / "token.json"
    DEFAULT_CALLBACK_TIMEOUT = 300  # 5 minutes for headless mode

    def __init__(
        self,
        extrasuite_server: str | None = None,
        service_account_path: str | Path | None = None,
        token_cache_path: str | Path | None = None,
    ) -> None:
        """Initialize the credentials manager.

        Args:
            extrasuite_server: URL of the ExtraSuite server.
            service_account_path: Path to service account JSON file.
            token_cache_path: Path to cache tokens.

        Raises:
            ValueError: If neither extrasuite_server nor service_account_path
                is provided (via constructor or environment variables).
        """
        # Resolve configuration with precedence
        self._server_url = extrasuite_server or os.environ.get("EXTRASUITE_SERVER_URL")
        if self._server_url:
            self._server_url = self._server_url.rstrip("/")

        sa_path = service_account_path or os.environ.get("SERVICE_ACCOUNT_PATH")
        self._sa_path = Path(sa_path) if sa_path else None

        # Validate that at least one auth method is configured
        if not self._server_url and not self._sa_path:
            raise ValueError(
                "No authentication method configured. "
                "Set EXTRASUITE_SERVER_URL or SERVICE_ACCOUNT_PATH environment variable, "
                "or pass extrasuite_server or service_account_path to constructor."
            )

        # ExtraSuite server takes precedence if both are configured
        self._use_extrasuite = bool(self._server_url)

        self._token_cache_path = (
            Path(token_cache_path) if token_cache_path else self.DEFAULT_CACHE_PATH
        )

    @property
    def auth_mode(self) -> str:
        """Return the active authentication mode."""
        return "extrasuite" if self._use_extrasuite else "service_account"

    def get_token(self, force_refresh: bool = False) -> Token:
        """Get a valid access token, authenticating if necessary.

        For ExtraSuite mode: checks cache first, then initiates OAuth flow.
        For service account mode: generates token from credentials file.

        Args:
            force_refresh: If True, ignore cached token and re-authenticate.

        Returns:
            A valid Token object.

        Raises:
            Exception: If authentication fails.
        """
        if self._use_extrasuite:
            return self._get_extrasuite_token(force_refresh)
        else:
            return self._get_service_account_token(force_refresh)

    def _get_extrasuite_token(self, force_refresh: bool) -> Token:
        """Get token via ExtraSuite server."""
        if not force_refresh:
            cached = self._load_cached_token()
            if cached and cached.is_valid():
                print(f"Using cached token (expires in {cached.expires_in_seconds()} seconds)")
                return cached

        print("Starting authentication flow...")
        token = self._authenticate_extrasuite()
        self._save_token(token)

        print("\nAuthentication successful!")
        print(f"Service account: {token.service_account_email}")
        print(f"Token expires in: {token.expires_in_seconds()} seconds")

        return token

    def _get_service_account_token(self, force_refresh: bool) -> Token:
        """Get token from service account file."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError:
            raise ImportError(  # noqa: B904
                "google-auth package is required for service account authentication. "
                "Install it with: pip install google-auth"
            )

        if not self._sa_path or not self._sa_path.exists():
            raise FileNotFoundError(f"Service account file not found: {self._sa_path}")

        # Check cache first (service account tokens also benefit from caching)
        if not force_refresh:
            cached = self._load_cached_token()
            if cached and cached.is_valid():
                print(f"Using cached token (expires in {cached.expires_in_seconds()} seconds)")
                return cached

        print(f"Loading credentials from {self._sa_path}...")

        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            str(self._sa_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )

        # Refresh to get access token
        credentials.refresh(Request())

        # Build token
        token = Token(
            access_token=credentials.token,
            service_account_email=credentials.service_account_email,
            expires_at=credentials.expiry.timestamp() if credentials.expiry else 0,
        )

        # Cache for future use
        self._save_token(token)

        print(f"Service account: {token.service_account_email}")
        print(f"Token expires in: {token.expires_in_seconds()} seconds")

        return token

    def _load_cached_token(self) -> Token | None:
        """Load cached token if it exists and is still valid."""
        if not self._token_cache_path.exists():
            return None

        try:
            data = json.loads(self._token_cache_path.read_text())
            token = Token.from_dict(data)
            if token.is_valid():
                return token
            else:
                print("Cached token expired, need to re-authenticate")
                return None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Invalid cached token: {e}")
            return None

    def _save_token(self, token: Token) -> None:
        """Save token to cache file with secure permissions."""
        # Create parent directory with secure permissions (0700)
        self._token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self._token_cache_path.parent, stat.S_IRWXU)

        # Write to temp file, set permissions, then rename atomically
        temp_path = self._token_cache_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(token.to_dict(), indent=2))
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        temp_path.rename(self._token_cache_path)
        print(f"Token saved to {self._token_cache_path}")

    def _authenticate_extrasuite(self) -> Token:
        """Run the ExtraSuite authentication flow.

        Supports both browser-based and headless modes:
        - Attempts to open browser automatically
        - Always prints URL for manual access
        - Accepts auth code from either HTTP callback or stdin input
        """
        port = self._find_free_port()
        auth_url = f"{self._server_url}/api/token/auth?port={port}"

        # Shared state for receiving auth code
        result_holder: dict[str, Any] = {"code": None, "error": None, "done": False}
        result_lock = threading.Lock()

        # Start HTTP callback server
        handler_class = self._create_handler_class(result_holder, result_lock)
        server = http.server.HTTPServer(("127.0.0.1", port), handler_class)
        server.timeout = 1  # Short timeout for polling

        def serve_loop() -> None:
            """Serve HTTP requests until we get a result or timeout."""
            start_time = time.time()
            while time.time() - start_time < self.DEFAULT_CALLBACK_TIMEOUT:
                with result_lock:
                    if result_holder["done"]:
                        break
                server.handle_request()
            server.server_close()

        server_thread = threading.Thread(target=serve_loop, daemon=True)
        server_thread.start()

        # Print auth URL prominently
        print("\n" + "=" * 60)
        print("AUTHENTICATION REQUIRED")
        print("=" * 60)
        print(f"\nOpen this URL in your browser:\n\n  {auth_url}\n")

        # Try to open browser (may fail in headless environments)
        try:
            import webbrowser

            if webbrowser.open(auth_url):
                print("(Browser opened automatically)")
        except Exception:
            pass  # Browser open failed, user will use URL manually

        print("\nWaiting for authentication...")
        print("(Or paste the auth code here if redirect doesn't work)")
        print("-" * 60)

        # Start stdin reader thread for headless mode
        def read_stdin() -> None:
            """Read auth code from stdin."""
            try:
                # Check if stdin is available and interactive
                if not sys.stdin.isatty():
                    return

                while True:
                    with result_lock:
                        if result_holder["done"]:
                            return

                    # Use select for non-blocking read on Unix
                    if sys.platform != "win32":
                        ready, _, _ = select.select([sys.stdin], [], [], 1.0)
                        if not ready:
                            continue

                    line = sys.stdin.readline().strip()
                    if line:
                        with result_lock:
                            if not result_holder["done"]:
                                result_holder["code"] = line
                                result_holder["done"] = True
                        return
            except Exception:
                pass  # stdin read failed, rely on HTTP callback

        stdin_thread = threading.Thread(target=read_stdin, daemon=True)
        stdin_thread.start()

        # Wait for either HTTP callback or stdin input
        start_time = time.time()
        while time.time() - start_time < self.DEFAULT_CALLBACK_TIMEOUT:
            with result_lock:
                if result_holder["done"]:
                    break
            time.sleep(0.5)

        # Mark as done to stop threads
        with result_lock:
            result_holder["done"] = True

        # Check result
        if result_holder.get("error"):
            raise Exception(f"Authentication failed: {result_holder['error']}")

        if not result_holder.get("code"):
            raise Exception("Authentication timed out. Please try again.")

        # Exchange auth code for token
        print("\nExchanging auth code for token...")
        return self._exchange_auth_code(result_holder["code"])

    def _exchange_auth_code(self, auth_code: str) -> Token:
        """Exchange auth code for token via POST request to server."""
        exchange_url = f"{self._server_url}/api/token/exchange"
        body = json.dumps({"code": auth_code}).encode("utf-8")

        req = urllib.request.Request(
            exchange_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            raise Exception(f"Token exchange failed: {error_body}") from e
        except urllib.error.URLError as e:
            raise Exception(f"Failed to connect to server: {e}") from e

        # Parse expires_at from ISO 8601 format to Unix timestamp
        expires_at_str = result["expires_at"]
        expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))

        return Token(
            access_token=result["token"],
            service_account_email=result.get("service_account", ""),
            expires_at=expires_at_dt.timestamp(),
        )

    @staticmethod
    def _find_free_port() -> int:
        """Find an available port on 127.0.0.1."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            return s.getsockname()[1]

    @staticmethod
    def _create_handler_class(result_holder: dict[str, Any], result_lock: threading.Lock) -> type:
        """Create HTTP handler class for OAuth callback."""

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            """HTTP handler to receive OAuth callback."""

            def log_message(self, format: str, *args: Any) -> None:
                """Suppress default logging."""
                pass

            def do_GET(self) -> None:
                """Handle GET request with auth code or error."""
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)

                with result_lock:
                    if result_holder["done"]:
                        self._send_html("Already processed.", 400)
                        return

                    if "error" in params:
                        result_holder["error"] = params["error"][0]
                        result_holder["done"] = True
                        self._send_html(
                            f"""
                            <html>
                            <head><title>Authentication Failed</title></head>
                            <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                                <h1 style="color: #dc3545;">Authentication Failed</h1>
                                <p>{params["error"][0]}</p>
                                <p>Please close this window and try again.</p>
                            </body>
                            </html>
                            """,
                            400,
                        )
                    elif "code" in params:
                        result_holder["code"] = params["code"][0]
                        result_holder["done"] = True
                        self._send_html(
                            """
                            <html>
                            <head><title>Authentication Successful</title></head>
                            <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                                <h1 style="color: #28a745;">Authentication Successful!</h1>
                                <p>You can close this window and return to your terminal.</p>
                                <script>window.close();</script>
                            </body>
                            </html>
                            """
                        )
                    else:
                        self._send_html(
                            """
                            <html>
                            <head><title>Invalid Request</title></head>
                            <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                                <h1>Invalid Request</h1>
                                <p>Missing auth code in callback.</p>
                            </body>
                            </html>
                            """,
                            400,
                        )

            def _send_html(self, content: str, status: int = 200) -> None:
                """Send HTML response."""
                self.send_response(status)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content.encode())

        return CallbackHandler


def main() -> int:
    """Command-line entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Get Google API access token via ExtraSuite or service account"
    )
    parser.add_argument(
        "--server",
        help="ExtraSuite server URL (or set EXTRASUITE_SERVER_URL env var)",
    )
    parser.add_argument(
        "--service-account",
        help="Path to service account JSON file (or set SERVICE_ACCOUNT_PATH env var)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-authentication even if cached token is valid",
    )
    parser.add_argument(
        "--show-token",
        action="store_true",
        help="Print the access token to stdout",
    )

    args = parser.parse_args()

    try:
        manager = CredentialsManager(
            extrasuite_server=args.server,
            service_account_path=args.service_account,
        )
        print(f"Auth mode: {manager.auth_mode}")
        token = manager.get_token(force_refresh=args.force)
        if args.show_token:
            print(f"\nAccess Token:\n{token.access_token}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
