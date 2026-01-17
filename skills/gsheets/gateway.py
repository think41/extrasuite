"""ExtraSuite client implementation."""

from __future__ import annotations

import http.server
import json
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any


class ExtraSuiteClient:
    """Client for obtaining Google service account tokens via OAuth.

    This class handles the complete OAuth flow for obtaining short-lived
    service account tokens from an ExtraSuite server.

    Args:
        server_url: URL of the ExtraSuite server.
            Must be configured - there is no default.
        token_cache_path: Path to cache tokens. Defaults to
            ~/.config/extrasuite/token.json
        callback_timeout: Timeout in seconds for OAuth callback.
            Defaults to 120 seconds.

    Example:
        client = ExtraSuiteClient(
            server_url="https://your-extrasuite-server.example.com"
        )
        token = client.get_token()
    """

    DEFAULT_CACHE_PATH = Path.home() / ".config" / "extrasuite" / "token.json"
    DEFAULT_CALLBACK_TIMEOUT = 120

    def __init__(
        self,
        server_url: str,
        token_cache_path: str | Path | None = None,
        callback_timeout: int | None = None,
    ) -> None:
        """Initialize the ExtraSuite client.

        Args:
            server_url: URL of the ExtraSuite server (required).
            token_cache_path: Path to cache tokens.
            callback_timeout: Timeout for OAuth callback in seconds.
        """
        if not server_url:
            raise ValueError("server_url is required")

        self._server_url = server_url.rstrip("/")
        self._token_cache_path = (
            Path(token_cache_path) if token_cache_path else self.DEFAULT_CACHE_PATH
        )
        self._callback_timeout = callback_timeout or self.DEFAULT_CALLBACK_TIMEOUT

    @property
    def server_url(self) -> str:
        """The configured server URL."""
        return self._server_url

    @property
    def token_cache_path(self) -> Path:
        """The path where tokens are cached."""
        return self._token_cache_path

    def get_token(self, force_refresh: bool = False) -> str:
        """Get a valid access token, authenticating if necessary.

        This method checks for a cached token first. If no valid cached token
        exists (or force_refresh is True), it initiates the OAuth flow by
        opening a browser for user authentication.

        Args:
            force_refresh: If True, ignore cached token and re-authenticate.

        Returns:
            A valid access token string.

        Raises:
            Exception: If authentication fails or times out.
        """
        if not force_refresh:
            cached = self._load_cached_token()
            if cached:
                expires_in = int(cached["expires_at"] - time.time())
                print(f"Using cached token (expires in {expires_in} seconds)")
                return cached["access_token"]

        # Need to authenticate
        print("Starting authentication flow...")
        token_data = self._authenticate()
        self._save_token(token_data)

        print("\nAuthentication successful!")
        print(f"Service account: {token_data.get('service_account_email', 'N/A')}")
        expires_in = int(token_data["expires_at"] - time.time())
        print(f"Token expires in: {expires_in} seconds")

        return token_data["access_token"]

    def _load_cached_token(self) -> dict[str, Any] | None:
        """Load cached token if it exists and is still valid.

        Returns:
            Token data dict if valid token exists, None otherwise.
        """
        if not self._token_cache_path.exists():
            return None

        try:
            token_data = json.loads(self._token_cache_path.read_text())
            expires_at = token_data.get("expires_at", 0)

            # Check if token is still valid (with 60 second buffer)
            if time.time() < expires_at - 60:
                return token_data
            else:
                print("Cached token expired, need to re-authenticate")
                return None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Invalid cached token: {e}")
            return None

    def _save_token(self, token_data: dict[str, Any]) -> None:
        """Save token to cache file.

        Args:
            token_data: Token data dict to save.
        """
        self._token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_cache_path.write_text(json.dumps(token_data, indent=2))
        print(f"Token saved to {self._token_cache_path}")

    def _authenticate(self) -> dict[str, Any]:
        """Run the authentication flow and return token data.

        Returns:
            Token data dict containing access_token, expires_at, etc.

        Raises:
            Exception: If authentication fails or times out.
        """
        # Find available port
        port = self._find_free_port()

        # Build auth URL - server only needs the port, constructs localhost URL itself
        # This prevents open redirect vulnerabilities
        auth_url = f"{self._server_url}/api/token/auth?port={port}"

        # Token holder for callback
        token_holder: dict[str, Any] = {}

        # Start callback server
        handler_class = self._create_handler_class(token_holder)
        server = http.server.HTTPServer(("localhost", port), handler_class)
        server.timeout = self._callback_timeout

        # Handle single request in thread
        def serve() -> None:
            server.handle_request()

        thread = threading.Thread(target=serve)
        thread.start()

        # Open browser
        print("\nOpening browser for authentication...")
        print(f"If browser doesn't open, visit: {auth_url}\n")
        webbrowser.open(auth_url)

        # Wait for callback
        thread.join(timeout=self._callback_timeout)
        server.server_close()

        # Check result
        if "error" in token_holder:
            raise Exception(f"Authentication failed: {token_holder['error']}")

        if "token" not in token_holder:
            raise Exception("Authentication timed out. Please try again.")

        # Parse expires_at from ISO 8601 format to Unix timestamp
        expires_at_str = token_holder["expires_at"]
        expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        expires_at = expires_at_dt.timestamp()

        # Build token data
        token_data = {
            "access_token": token_holder["token"],
            "expires_at": expires_at,
            "service_account_email": token_holder.get("service_account", ""),
            "token_type": "Bearer",
        }

        return token_data

    @staticmethod
    def _find_free_port() -> int:
        """Find an available port on localhost.

        Returns:
            An available port number.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            s.listen(1)
            return s.getsockname()[1]

    @staticmethod
    def _create_handler_class(token_holder: dict[str, Any]) -> type:
        """Create HTTP handler class with token holder bound.

        Args:
            token_holder: Dict to store received token data.

        Returns:
            HTTP handler class.
        """

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            """HTTP handler to receive OAuth callback with token."""

            def log_message(self, format: str, *args: Any) -> None:
                """Suppress default logging."""
                pass

            def do_GET(self) -> None:
                """Handle GET request with token or error."""
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)

                if "error" in params:
                    error = params["error"][0]
                    token_holder["error"] = error
                    self._send_html(
                        f"""
                        <html>
                        <head><title>Authentication Failed</title></head>
                        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                            <h1 style="color: #dc3545;">Authentication Failed</h1>
                            <p>{error}</p>
                            <p>Please close this window and try again.</p>
                        </body>
                        </html>
                    """,
                        400,
                    )
                elif "token" in params:
                    token_holder["token"] = params["token"][0]
                    token_holder["expires_at"] = params.get("expires_at", [""])[0]
                    token_holder["service_account"] = params.get("service_account", [""])[0]
                    self._send_html("""
                        <html>
                        <head><title>Authentication Successful</title></head>
                        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                            <h1 style="color: #28a745;">Authentication Successful!</h1>
                            <p>You can close this window and return to your terminal.</p>
                            <script>window.close();</script>
                        </body>
                        </html>
                    """)
                else:
                    self._send_html(
                        """
                        <html>
                        <head><title>Invalid Request</title></head>
                        <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                            <h1>Invalid Request</h1>
                            <p>Missing token in callback.</p>
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
        description="Authenticate with ExtraSuite to get service account token"
    )
    parser.add_argument(
        "--server",
        required=True,
        help="ExtraSuite server URL",
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
        client = ExtraSuiteClient(server_url=args.server)
        token = client.get_token(force_refresh=args.force)
        if args.show_token:
            print(f"\nAccess Token:\n{token}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
