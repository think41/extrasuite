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

import certifi
import keyring

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Keyring service name for storing tokens
KEYRING_SERVICE = "extrasuite"
KEYRING_USERNAME = "token"


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
    1. ExtraSuite protocol - obtains short-lived tokens via OAuth flow
    2. Service account file - uses credentials from a JSON key file

    Precedence order for configuration:
    1. auth_url/exchange_url constructor parameters
    2. EXTRASUITE_AUTH_URL/EXTRASUITE_EXCHANGE_URL environment variables
    3. ~/.config/extrasuite/gateway.json (created by install script)
    4. service_account_path constructor parameter
    5. SERVICE_ACCOUNT_PATH environment variable

    Tokens are securely cached in the OS keyring (macOS Keychain, Windows Credential
    Locker, or Linux Secret Service).

    Args:
        auth_url: URL to start authentication (e.g., "https://server.com/api/token/auth").
            The port parameter will be appended as a query string.
        exchange_url: URL to exchange auth code for token (e.g., "https://server.com/api/token/exchange").
        service_account_path: Path to service account JSON file (optional).

    Example:
        # Using explicit URLs
        manager = CredentialsManager(
            auth_url="https://auth.example.com/api/token/auth",
            exchange_url="https://auth.example.com/api/token/exchange",
        )
        token = manager.get_token()

        # Using service account file
        manager = CredentialsManager(service_account_path="/path/to/sa.json")
        token = manager.get_token()
    """

    GATEWAY_CONFIG_PATH = Path.home() / ".config" / "extrasuite" / "gateway.json"
    DEFAULT_CALLBACK_TIMEOUT = 300  # 5 minutes for headless mode

    def __init__(
        self,
        auth_url: str | None = None,
        exchange_url: str | None = None,
        service_account_path: str | Path | None = None,
    ) -> None:
        """Initialize the credentials manager.

        Args:
            auth_url: URL to start authentication flow.
            exchange_url: URL to exchange auth code for token.
            service_account_path: Path to service account JSON file.

        Raises:
            ValueError: If neither auth_url/exchange_url nor service_account_path
                is provided (via constructor, environment variables, or gateway.json).
        """
        # Resolve configuration with precedence: constructor > env var > gateway.json
        self._auth_url = auth_url or os.environ.get("EXTRASUITE_AUTH_URL")
        self._exchange_url = exchange_url or os.environ.get("EXTRASUITE_EXCHANGE_URL")

        # If not set, try gateway.json
        if not self._auth_url or not self._exchange_url:
            gateway_urls = self._load_gateway_config()
            if gateway_urls:
                self._auth_url = self._auth_url or gateway_urls.get("auth_url")
                self._exchange_url = self._exchange_url or gateway_urls.get(
                    "exchange_url"
                )

        sa_path = service_account_path or os.environ.get("SERVICE_ACCOUNT_PATH")
        self._sa_path = Path(sa_path) if sa_path else None

        # Validate that at least one auth method is configured
        has_extrasuite = bool(self._auth_url and self._exchange_url)
        has_partial_extrasuite = bool(self._auth_url) != bool(self._exchange_url)
        if has_partial_extrasuite:
            missing = "exchange_url" if self._auth_url else "auth_url"
            raise ValueError(
                f"Incomplete ExtraSuite configuration: {missing} is missing. "
                "Both auth_url and exchange_url must be provided together."
            )
        if not has_extrasuite and not self._sa_path:
            raise ValueError(
                "No authentication method configured. "
                "Set EXTRASUITE_AUTH_URL and EXTRASUITE_EXCHANGE_URL environment variables, "
                "install skills via the ExtraSuite website (creates gateway.json), "
                "or pass auth_url/exchange_url or service_account_path to constructor."
            )

        # ExtraSuite protocol takes precedence if both are configured
        self._use_extrasuite = has_extrasuite

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
                print(
                    f"Using cached token (expires in {cached.expires_in_seconds()} seconds)"
                )
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
        # Check cache first (service account tokens also benefit from caching)
        # This avoids requiring google-auth if we have a valid cached token
        if not force_refresh:
            cached = self._load_cached_token()
            if cached and cached.is_valid():
                print(
                    f"Using cached token (expires in {cached.expires_in_seconds()} seconds)"
                )
                return cached

        # Only import google-auth when we actually need to refresh
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
        """Load cached token from OS keyring if it exists and is still valid."""
        try:
            token_json = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if not token_json:
                return None

            data = json.loads(token_json)
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
        """Save token securely to OS keyring."""
        token_json = json.dumps(token.to_dict())
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token_json)
        print("Token saved to OS keyring")

    def _load_gateway_config(self) -> dict[str, str] | None:
        """Load endpoint URLs from gateway.json if it exists.

        The gateway.json file is created by the install script and contains
        the authentication endpoint URLs configured during skill installation.

        Supports both formats:
        - New format: EXTRASUITE_AUTH_URL and EXTRASUITE_EXCHANGE_URL
        - Legacy format: EXTRASUITE_SERVER_URL (deprecated, will derive URLs)

        Returns:
            Dictionary with 'auth_url' and 'exchange_url' if gateway.json exists
            and is valid, None otherwise.
        """
        if not self.GATEWAY_CONFIG_PATH.exists():
            return None
        try:
            data = json.loads(self.GATEWAY_CONFIG_PATH.read_text())

            # Check for new format first
            auth_url = data.get("EXTRASUITE_AUTH_URL")
            exchange_url = data.get("EXTRASUITE_EXCHANGE_URL")

            # Fall back to legacy EXTRASUITE_SERVER_URL format
            if not auth_url or not exchange_url:
                server_url = data.get("EXTRASUITE_SERVER_URL")
                if server_url:
                    # Remove trailing slash if present
                    server_url = server_url.rstrip("/")
                    auth_url = f"{server_url}/api/token/auth"
                    exchange_url = f"{server_url}/api/token/exchange"
                    print(
                        "Warning: gateway.json uses deprecated EXTRASUITE_SERVER_URL format. "
                        "Please update to use EXTRASUITE_AUTH_URL and EXTRASUITE_EXCHANGE_URL."
                    )

            return {
                "auth_url": auth_url,
                "exchange_url": exchange_url,
            }
        except (json.JSONDecodeError, OSError):
            return None

    def _authenticate_extrasuite(self) -> Token:
        """Run the ExtraSuite authentication flow.

        Supports both browser-based and headless modes:
        - Attempts to open browser automatically
        - Always prints URL for manual access
        - Accepts auth code from either HTTP callback or stdin input
        """
        port = self._find_free_port()
        auth_url = f"{self._auth_url}?port={port}"

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
        assert self._exchange_url is not None  # Guaranteed when using ExtraSuite mode
        body = json.dumps({"code": auth_code}).encode("utf-8")

        req = urllib.request.Request(
            self._exchange_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, timeout=30, context=SSL_CONTEXT
            ) as response:
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
    def _create_handler_class(
        result_holder: dict[str, Any], result_lock: threading.Lock
    ) -> type:
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


def authenticate(
    auth_url: str | None = None,
    exchange_url: str | None = None,
    service_account_path: str | Path | None = None,
    force_refresh: bool = False,
) -> Token:
    """Authenticate and get a valid Google API access token.

    This is a convenience function that creates a CredentialsManager and
    retrieves a token. Configuration can be provided via parameters,
    environment variables (EXTRASUITE_AUTH_URL, EXTRASUITE_EXCHANGE_URL,
    SERVICE_ACCOUNT_PATH), or gateway.json.

    Args:
        auth_url: URL to start authentication flow.
        exchange_url: URL to exchange auth code for token.
        service_account_path: Path to service account JSON file.
        force_refresh: If True, ignore cached token and re-authenticate.

    Returns:
        A valid Token object with access_token, service_account_email,
        and expires_at fields.

    Raises:
        ValueError: If no authentication method is configured.
        Exception: If authentication fails.

    Example:
        from extrasheet import authenticate

        token = authenticate()
        print(f"Token: {token.access_token[:50]}...")
        print(f"Service account: {token.service_account_email}")
    """
    manager = CredentialsManager(
        auth_url=auth_url,
        exchange_url=exchange_url,
        service_account_path=service_account_path,
    )
    return manager.get_token(force_refresh=force_refresh)


def main() -> int:
    """Command-line entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Get Google API access token via ExtraSuite or service account"
    )
    parser.add_argument(
        "--auth-url",
        help="URL to start authentication (or set EXTRASUITE_AUTH_URL env var)",
    )
    parser.add_argument(
        "--exchange-url",
        help="URL to exchange auth code for token (or set EXTRASUITE_EXCHANGE_URL env var)",
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
            auth_url=args.auth_url,
            exchange_url=args.exchange_url,
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
