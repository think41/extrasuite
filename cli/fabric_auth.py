#!/usr/bin/env python3
"""Fabric CLI Authentication - Reference Implementation.

This script demonstrates the authentication flow for CLI tools that need
to access Google Sheets/Docs via Fabric-provisioned service accounts.

Flow:
1. Check for existing valid token in ~/.config/fabric/token.json
2. If no valid token, start localhost callback server
3. Open browser to Fabric auth URL with redirect to localhost
4. Receive short-lived SA token via redirect
5. Save token and continue

Usage:
    python fabric_auth.py
    python fabric_auth.py --server https://fabric.example.com
"""

import argparse
import http.server
import json
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

# Default configuration
DEFAULT_FABRIC_SERVER = "http://localhost:8001"
TOKEN_FILE = Path.home() / ".config" / "fabric" / "token.json"
CALLBACK_TIMEOUT = 120  # seconds


def find_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        s.listen(1)
        return s.getsockname()[1]


def load_cached_token() -> dict | None:
    """Load cached token if it exists and is still valid."""
    if not TOKEN_FILE.exists():
        return None

    try:
        token_data = json.loads(TOKEN_FILE.read_text())
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


def save_token(token_data: dict) -> None:
    """Save token to cache file."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    print(f"Token saved to {TOKEN_FILE}")


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to receive OAuth callback with token."""

    def __init__(self, token_holder: dict, *args, **kwargs):
        self.token_holder = token_holder
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET request with token or error."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            error = params["error"][0]
            self.token_holder["error"] = error
            self._send_html(f"""
                <html>
                <head><title>Authentication Failed</title></head>
                <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                    <h1 style="color: #dc3545;">Authentication Failed</h1>
                    <p>{error}</p>
                    <p>Please close this window and try again.</p>
                </body>
                </html>
            """, 400)
        elif "token" in params:
            self.token_holder["token"] = params["token"][0]
            self.token_holder["expires_in"] = int(params.get("expires_in", ["3600"])[0])
            self.token_holder["service_account"] = params.get("service_account", [""])[0]
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
            self._send_html("""
                <html>
                <head><title>Invalid Request</title></head>
                <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                    <h1>Invalid Request</h1>
                    <p>Missing token in callback.</p>
                </body>
                </html>
            """, 400)

    def _send_html(self, content: str, status: int = 200):
        """Send HTML response."""
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(content.encode())


def create_handler_class(token_holder: dict):
    """Create handler class with token holder bound."""
    def handler(*args, **kwargs):
        return CallbackHandler(token_holder, *args, **kwargs)
    return handler


def authenticate(fabric_server: str) -> dict:
    """Run the authentication flow and return token data."""
    # Find available port
    port = find_free_port()

    # Build auth URL - server only needs the port, constructs localhost URL itself
    # This prevents open redirect vulnerabilities
    auth_url = f"{fabric_server}/api/token/auth?port={port}"

    # Token holder for callback
    token_holder = {}

    # Start callback server
    handler_class = create_handler_class(token_holder)
    server = http.server.HTTPServer(("localhost", port), handler_class)
    server.timeout = CALLBACK_TIMEOUT

    # Handle single request in thread
    def serve():
        server.handle_request()

    thread = threading.Thread(target=serve)
    thread.start()

    # Open browser
    print(f"\nOpening browser for authentication...")
    print(f"If browser doesn't open, visit: {auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    thread.join(timeout=CALLBACK_TIMEOUT)
    server.server_close()

    # Check result
    if "error" in token_holder:
        raise Exception(f"Authentication failed: {token_holder['error']}")

    if "token" not in token_holder:
        raise Exception("Authentication timed out. Please try again.")

    # Build token data
    token_data = {
        "access_token": token_holder["token"],
        "expires_at": time.time() + token_holder["expires_in"],
        "expires_in": token_holder["expires_in"],
        "service_account_email": token_holder.get("service_account", ""),
        "token_type": "Bearer",
    }

    return token_data


def get_token(fabric_server: str = DEFAULT_FABRIC_SERVER, force_refresh: bool = False) -> str:
    """Get a valid access token, authenticating if necessary.

    Args:
        fabric_server: URL of the Fabric server
        force_refresh: Force re-authentication even if cached token is valid

    Returns:
        Valid access token string
    """
    if not force_refresh:
        cached = load_cached_token()
        if cached:
            print(f"Using cached token (expires in {int(cached['expires_at'] - time.time())} seconds)")
            return cached["access_token"]

    # Need to authenticate
    print("Starting authentication flow...")
    token_data = authenticate(fabric_server)
    save_token(token_data)

    print(f"\nAuthentication successful!")
    print(f"Service account: {token_data.get('service_account_email', 'N/A')}")
    print(f"Token expires in: {token_data['expires_in']} seconds")

    return token_data["access_token"]


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Authenticate with Fabric to get service account token"
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_FABRIC_SERVER,
        help=f"Fabric server URL (default: {DEFAULT_FABRIC_SERVER})",
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
        token = get_token(args.server, args.force)
        if args.show_token:
            print(f"\nAccess Token:\n{token}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
