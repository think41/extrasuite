"""Credentials management for Google API access.

Supports two authentication modes:
1. ExtraSuite server - short-lived tokens via OAuth flow (v1 legacy)
   and session-token protocol (v2: one browser login per 30 days, then headless)
2. Service account file - direct credentials from JSON key file
"""

from __future__ import annotations

import contextlib
import hashlib
import http.server
import json
import os
import platform
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
import uuid
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
class Credential:
    """A single credential issued for a specific provider and operation.

    Mirrors the server-side ``Credential`` Pydantic model.  The ``kind`` field
    distinguishes SA tokens (``bearer_sa``) from DWD tokens (``bearer_dwd``).
    Provider-specific extras (e.g. ``service_account_email``) live in
    ``metadata`` so this class remains extensible to non-Google providers.
    """

    provider: str  # "google", "slack", …
    kind: str  # "bearer_sa" | "bearer_dwd" | "api_key" | …
    token: str
    expires_at: float  # Unix timestamp; 0 if non-expiring
    scopes: list[str]  # granted OAuth scope URLs (empty for SA tokens)
    metadata: dict[str, str]  # provider-specific extras

    @property
    def service_account_email(self) -> str:
        return self.metadata.get("service_account_email", "")

    def is_valid(self, buffer_seconds: int = 60) -> bool:
        """Check if credential is still valid with a safety buffer."""
        if self.expires_at == 0:
            return True
        return time.time() < self.expires_at - buffer_seconds

    def expires_in_seconds(self) -> int:
        """Return seconds until credential expires (0 if non-expiring)."""
        if self.expires_at == 0:
            return 0
        return max(0, int(self.expires_at - time.time()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "token": self.token,
            "expires_at": self.expires_at,
            "scopes": self.scopes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Credential:
        return cls(
            provider=data["provider"],
            kind=data["kind"],
            token=data["token"],
            expires_at=data["expires_at"],
            scopes=data.get("scopes", []),
            metadata=data.get("metadata", {}),
        )


# Token cache TTL constants
SA_TOKEN_CACHE_SECONDS = 3600  # 60 min for service account tokens
DWD_TOKEN_CACHE_SECONDS = 600  # 10 min for domain-wide delegation tokens

_GOOGLE_SCOPE_PREFIX = "https://www.googleapis.com/auth/"


def _parse_first_google_credential(
    response: dict[str, Any], cmd_type: str
) -> Credential:
    """Extract and normalise the first Google credential from a TokenResponse dict.

    Caps expiry at the appropriate client-side TTL so the cache lifetime is
    bounded regardless of what the server returns.
    """
    raw_creds: list[dict[str, Any]] = response.get("credentials", [])
    if not raw_creds:
        raise ValueError(
            f"Server returned no credentials for command type {cmd_type!r}"
        )

    # Pick the first Google credential (today there is always exactly one)
    raw = next(
        (c for c in raw_creds if c.get("provider", "google") == "google"), raw_creds[0]
    )

    expires_at_str: str = raw.get("expires_at", "")
    if expires_at_str:
        expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        raw_expires = expires_at_dt.timestamp()
    else:
        raw_expires = 0.0

    kind = raw.get("kind", "bearer_sa")
    cache_cap = (
        DWD_TOKEN_CACHE_SECONDS if kind == "bearer_dwd" else SA_TOKEN_CACHE_SECONDS
    )
    expires_at = min(raw_expires, time.time() + cache_cap) if raw_expires else 0.0

    return Credential(
        provider=raw.get("provider", "google"),
        kind=kind,
        token=raw["token"],
        expires_at=expires_at,
        scopes=raw.get("scopes", []),
        metadata=raw.get("metadata", {}),
    )


@dataclass
class SessionToken:
    """Long-lived (30-day) session token for headless agent access.

    Obtained once via browser OAuth flow; used to exchange for short-lived
    access tokens without further browser interaction (Phase 2).

    Attributes:
        raw_token: The raw session token string.
        email: User's email address.
        expires_at: Unix timestamp when the session expires.
    """

    raw_token: str
    email: str
    expires_at: float

    def is_valid(self, buffer_seconds: int = 300) -> bool:
        """Check if session token is still valid with a 5-minute buffer."""
        return time.time() < self.expires_at - buffer_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "raw_token": self.raw_token,
            "email": self.email,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionToken:
        """Create SessionToken from dictionary."""
        return cls(
            raw_token=data["raw_token"],
            email=data["email"],
            expires_at=data["expires_at"],
        )


class CredentialsManager:
    """Manages credentials for Google API access.

    Supports two authentication modes:
    1. ExtraSuite protocol - obtains short-lived tokens via OAuth flow
    2. Service account file - uses credentials from a JSON key file

    Precedence order for configuration:
    1. Constructor parameters
    2. Environment variables (EXTRASUITE_SERVER_URL, EXTRASUITE_AUTH_URL, etc.)
    3. ~/.config/extrasuite/gateway.json (created by install script)
    4. service_account_path constructor parameter / SERVICE_ACCOUNT_PATH env var

    Args:
        auth_url: URL to start authentication (e.g., "https://server.com/api/token/auth").
        exchange_url: URL to exchange auth code for token.
        delegation_auth_url: URL for delegation auth flow.
        delegation_exchange_url: URL to exchange delegation auth code.
        service_account_path: Path to service account JSON file (optional).
        token_cache_path: Path to cache tokens. Defaults to ~/.config/extrasuite/token.json
        gateway_config_path: Path to gateway.json. Defaults to ~/.config/extrasuite/gateway.json.
            If explicitly set and file doesn't exist, raises FileNotFoundError.
    """

    CREDENTIALS_CACHE_DIR = Path.home() / ".config" / "extrasuite" / "credentials"
    GATEWAY_CONFIG_PATH = Path.home() / ".config" / "extrasuite" / "gateway.json"
    SESSION_CACHE_PATH = Path.home() / ".config" / "extrasuite" / "session.json"
    DEFAULT_CALLBACK_TIMEOUT = 300  # 5 minutes for headless mode

    def __init__(
        self,
        auth_url: str | None = None,
        exchange_url: str | None = None,
        delegation_auth_url: str | None = None,
        delegation_exchange_url: str | None = None,
        service_account_path: str | Path | None = None,
        gateway_config_path: str | Path | None = None,
        headless: bool | None = None,
    ) -> None:
        # Store explicit gateway path (used by _load_gateway_config)
        self._gateway_config_path = (
            Path(gateway_config_path) if gateway_config_path else None
        )

        # Headless mode: no browser, print URL and prompt for code on stderr
        # Precedence: constructor param > EXTRASUITE_HEADLESS env var
        if headless is not None:
            self._headless = headless
        else:
            self._headless = os.environ.get("EXTRASUITE_HEADLESS", "").strip() == "1"

        # Resolve configuration with precedence: constructor > env var > gateway.json
        self._auth_url = auth_url or os.environ.get("EXTRASUITE_AUTH_URL")
        self._exchange_url = exchange_url or os.environ.get("EXTRASUITE_EXCHANGE_URL")
        self._delegation_auth_url = delegation_auth_url or os.environ.get(
            "EXTRASUITE_DELEGATION_AUTH_URL"
        )
        self._delegation_exchange_url = delegation_exchange_url or os.environ.get(
            "EXTRASUITE_DELEGATION_EXCHANGE_URL"
        )

        # Track whether explicit auth URLs were provided.  When True, gateway.json
        # may still fill in missing delegation URLs but must NOT activate v2 session
        # flow (server_base_url).  This prevents a developer's personal gateway.json
        # from silently enabling v2 in tests or scripts that pass explicit auth_url.
        #
        # Known limitation: if EXTRASUITE_AUTH_URL is set to a v2-capable server AND
        # a gateway.json with EXTRASUITE_SERVER_URL is also present, the v2 session
        # flow will NOT be activated (server_base_url stays None).  The caller must
        # set EXTRASUITE_SERVER_URL (or gateway.json) without also setting the
        # individual EXTRASUITE_AUTH_URL override to get v2 behaviour.
        _explicit_auth_urls = bool(self._auth_url)

        # Derived server base URL for new v2 endpoints (session exchange, access token)
        self._server_base_url: str | None = None

        # Check EXTRASUITE_SERVER_URL env var (derives all 4 URLs)
        server_url_env = os.environ.get("EXTRASUITE_SERVER_URL")
        if server_url_env:
            server_url_env = server_url_env.rstrip("/")
            self._server_base_url = server_url_env
            if not self._auth_url:
                self._auth_url = f"{server_url_env}/api/token/auth"
            if not self._exchange_url:
                self._exchange_url = f"{server_url_env}/api/token/exchange"
            if not self._delegation_auth_url:
                self._delegation_auth_url = f"{server_url_env}/api/delegation/auth"
            if not self._delegation_exchange_url:
                self._delegation_exchange_url = (
                    f"{server_url_env}/api/delegation/exchange"
                )

        # If not set, try gateway.json
        if (
            not self._auth_url
            or not self._exchange_url
            or not self._delegation_auth_url
            or not self._delegation_exchange_url
        ):
            gateway_urls = self._load_gateway_config()
            if gateway_urls:
                self._auth_url = self._auth_url or gateway_urls.get("auth_url")
                self._exchange_url = self._exchange_url or gateway_urls.get(
                    "exchange_url"
                )
                self._delegation_auth_url = (
                    self._delegation_auth_url or gateway_urls.get("delegation_auth_url")
                )
                self._delegation_exchange_url = (
                    self._delegation_exchange_url
                    or gateway_urls.get("delegation_exchange_url")
                )
                if (
                    not self._server_base_url
                    and not _explicit_auth_urls
                    and gateway_urls.get("server_base_url")
                ):
                    self._server_base_url = gateway_urls.get("server_base_url")

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
                "No authentication method configured.\n\n"
                "Fix with ONE of these options:\n"
                "  1. Pass --gateway /path/to/gateway.json (contains server URLs)\n"
                "  2. Pass --service-account /path/to/sa.json (direct Google credentials)\n"
                "  3. Set EXTRASUITE_SERVER_URL environment variable\n"
                "  4. Create ~/.config/extrasuite/gateway.json with:\n"
                '     {"EXTRASUITE_SERVER_URL": "https://your-server.example.com"}'
            )

        # ExtraSuite protocol takes precedence if both are configured
        self._use_extrasuite = has_extrasuite

    @property
    def auth_mode(self) -> str:
        """Return the active authentication mode."""
        return "extrasuite" if self._use_extrasuite else "service_account"

    def get_credential(
        self,
        *,
        command: dict[str, Any],
        reason: str,
        force_refresh: bool = False,
    ) -> Credential:
        """Exchange a session token for the credential(s) required by *command*.

        ``command`` must be a dict that matches one of the typed Command models
        on the server, e.g.::

            {"type": "sheet.pull", "file_url": "https://docs.google.com/..."}
            {"type": "gmail.compose", "subject": "Hello", "recipients": ["a@b.com"]}

        ``reason`` is agent-supplied user intent logged server-side for auditing.

        For ExtraSuite v2 mode: validates the session, POSTs to /api/auth/token,
        caches the first Google credential by command type.

        For service account file mode: generates a token directly from the SA key.
        Only meaningful for SA-backed command types; DWD is not supported in this mode.

        Args:
            command: Dict representation of a typed Command (must include ``type``).
            reason: Agent-supplied user intent (logged for auditing).
            force_refresh: If True, bypass the cache and re-exchange.

        Returns:
            A Credential object with ``token``, ``kind``, ``service_account_email``, etc.
        """
        cmd_type = command.get("type", "")

        if self._use_extrasuite:
            return self._get_extrasuite_credential(
                command=command,
                cmd_type=cmd_type,
                reason=reason,
                force_refresh=force_refresh,
            )
        else:
            return self._get_service_account_credential(
                cmd_type=cmd_type, force_refresh=force_refresh
            )

    def _credential_cache_path(self, cmd_type: str) -> Path:
        """Return the cache file path for a given command type."""
        # Sanitise cmd_type so it's safe as a filename (dots are fine, slashes aren't)
        safe = cmd_type.replace("/", "_")
        return self.CREDENTIALS_CACHE_DIR / f"{safe}.json"

    def _get_extrasuite_credential(
        self,
        *,
        command: dict[str, Any],
        cmd_type: str,
        reason: str,
        force_refresh: bool,
    ) -> Credential:
        """Get credential via ExtraSuite server (v2 session flow)."""
        cache_path = self._credential_cache_path(cmd_type)
        if not force_refresh:
            cached = self._load_cached_credential(cache_path)
            if cached and cached.is_valid():
                return cached

        if self._server_base_url:
            session = self._get_or_create_session_token()
            result = self._exchange_session_for_credential(
                session, command=command, reason=reason
            )
            # result["credentials"] is a list; pick the first Google credential
            cred = _parse_first_google_credential(result, cmd_type)
            self._save_credential(cache_path, cred)
            return cred

        # Legacy v1 flow — only SA commands are supported here
        cred = self._authenticate_extrasuite()
        self._save_credential(cache_path, cred)
        return cred

    def _get_service_account_credential(
        self, *, cmd_type: str, force_refresh: bool
    ) -> Credential:
        """Get credential from a service account JSON key file."""
        cache_path = self._credential_cache_path(cmd_type)
        if not force_refresh:
            cached = self._load_cached_credential(cache_path)
            if cached and cached.is_valid():
                return cached

        try:
            from google.auth.transport.requests import (  # type: ignore[import-not-found]
                Request,
            )
            from google.oauth2 import (  # type: ignore[import-not-found]
                service_account,
            )
        except ImportError:
            raise ImportError(  # noqa: B904
                "google-auth package is required for service account authentication. "
                "Install it with: pip install google-auth"
            )

        if not self._sa_path or not self._sa_path.exists():
            raise FileNotFoundError(f"Service account file not found: {self._sa_path}")

        credentials = service_account.Credentials.from_service_account_file(
            str(self._sa_path),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/presentations",
            ],
        )
        credentials.refresh(Request())

        cred = Credential(
            provider="google",
            kind="bearer_sa",
            token=credentials.token,
            expires_at=credentials.expiry.timestamp() if credentials.expiry else 0,
            scopes=[],
            metadata={"service_account_email": credentials.service_account_email},
        )
        self._save_credential(cache_path, cred)
        return cred

    def _load_cached_credential(self, cache_path: Path) -> Credential | None:
        """Load a cached credential if it exists."""
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text())
            return Credential.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def _write_secure_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON atomically with 0600 permissions from the start (no chmod race)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(stat.S_IRWXU)
        temp_path = path.with_suffix(".tmp")
        content = json.dumps(data, indent=2).encode()
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
        temp_path.rename(path)

    def _save_credential(self, cache_path: Path, cred: Credential) -> None:
        """Save credential to cache file with secure permissions."""
        self._write_secure_json(cache_path, cred.to_dict())

    def _load_gateway_config(self) -> dict[str, str] | None:
        """Load endpoint URLs from gateway.json if it exists.

        Supports these formats in gateway.json:
        - EXTRASUITE_SERVER_URL: Derives all 4 endpoints (preferred)
        - EXTRASUITE_AUTH_URL / EXTRASUITE_EXCHANGE_URL: Explicit token URLs
        - EXTRASUITE_DELEGATION_AUTH_URL / EXTRASUITE_DELEGATION_EXCHANGE_URL: Explicit delegation URLs

        Returns:
            Dictionary with up to 4 URL keys, or None if file not found.

        Raises:
            FileNotFoundError: If explicit gateway_config_path was set and doesn't exist.
        """
        config_path = self._gateway_config_path or self.GATEWAY_CONFIG_PATH

        if self._gateway_config_path and not config_path.exists():
            raise FileNotFoundError(f"Gateway config file not found: {config_path}")

        if not config_path.exists():
            return None
        try:
            data = json.loads(config_path.read_text())

            result: dict[str, str] = {}

            # Derive from EXTRASUITE_SERVER_URL if present
            server_url = data.get("EXTRASUITE_SERVER_URL")
            if server_url:
                server_url = server_url.rstrip("/")
                result["server_base_url"] = server_url
                result["auth_url"] = f"{server_url}/api/token/auth"
                result["exchange_url"] = f"{server_url}/api/token/exchange"
                result["delegation_auth_url"] = f"{server_url}/api/delegation/auth"
                result["delegation_exchange_url"] = (
                    f"{server_url}/api/delegation/exchange"
                )

            # Explicit URLs override server-derived values
            if data.get("EXTRASUITE_AUTH_URL"):
                result["auth_url"] = data["EXTRASUITE_AUTH_URL"]
            if data.get("EXTRASUITE_EXCHANGE_URL"):
                result["exchange_url"] = data["EXTRASUITE_EXCHANGE_URL"]
            if data.get("EXTRASUITE_DELEGATION_AUTH_URL"):
                result["delegation_auth_url"] = data["EXTRASUITE_DELEGATION_AUTH_URL"]
            if data.get("EXTRASUITE_DELEGATION_EXCHANGE_URL"):
                result["delegation_exchange_url"] = data[
                    "EXTRASUITE_DELEGATION_EXCHANGE_URL"
                ]

            return result if result else None
        except (json.JSONDecodeError, OSError):
            return None

    # =========================================================================
    # Session Token Methods (v2 Protocol)
    # =========================================================================

    @staticmethod
    def _collect_device_info() -> dict[str, str]:
        """Collect device fingerprint for session token issuance."""
        return {
            "device_mac": hex(uuid.getnode()),
            "device_hostname": socket.gethostname(),
            "device_os": platform.system(),
            "device_platform": platform.platform(),
        }

    def _load_session_token(self) -> SessionToken | None:
        """Load cached session token if it exists and is still valid."""
        if not self.SESSION_CACHE_PATH.exists():
            return None
        try:
            data = json.loads(self.SESSION_CACHE_PATH.read_text())
            token = SessionToken.from_dict(data)
            if token.is_valid():
                return token
            return None
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_session_token(self, token: SessionToken) -> None:
        """Save session token to cache file with secure permissions."""
        self._write_secure_json(self.SESSION_CACHE_PATH, token.to_dict())

    def _revoke_and_clear_session(self) -> None:
        """Revoke the current session server-side and clear the local session cache.

        Best-effort: prints a warning to stderr if the server call fails, but always
        removes the local cache file so the caller can proceed to issue a new session.
        """
        if not self.SESSION_CACHE_PATH.exists() or not self._server_base_url:
            return
        try:
            data = json.loads(self.SESSION_CACHE_PATH.read_text())
            raw_token = data.get("raw_token", "")
            if raw_token:
                token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                revoke_url = f"{self._server_base_url}/api/admin/sessions/{token_hash}"
                req = urllib.request.Request(
                    revoke_url,
                    headers={"Authorization": f"Bearer {raw_token}"},
                    method="DELETE",
                )
                try:
                    urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT)
                except Exception as e:
                    print(
                        f"Warning: server-side session revocation failed ({e}).\n"
                        "Local credentials cleared, but your session may still be active on the server.",
                        file=sys.stderr,
                    )
        except Exception:
            pass
        with contextlib.suppress(Exception):
            self.SESSION_CACHE_PATH.unlink(missing_ok=True)

    def login(self, *, force: bool = False) -> SessionToken:
        """Log in and obtain a 30-day session token.

        If a valid session already exists and force=False, returns it immediately
        (headless — no browser required).

        If force=True, revokes any existing session server-side before issuing a new
        one. This is the correct way to rotate credentials if a session may be
        compromised.

        Note: This call collects device fingerprint information (MAC address, hostname,
        OS, platform) that is sent to the ExtraSuite server for audit purposes.

        Args:
            force: If True, always create a new session even if one exists.

        Returns:
            A valid SessionToken.
        """
        if force:
            self._revoke_and_clear_session()
            # Clear short-lived credential caches so the new session starts fully fresh.
            cred_dir = self.CREDENTIALS_CACHE_DIR
            if cred_dir.exists():
                for path in cred_dir.glob("*.json"):
                    with contextlib.suppress(Exception):
                        path.unlink(missing_ok=True)
        return self._get_or_create_session_token(force=force)

    def logout(self) -> None:
        """Revoke the session token server-side and clear all local credential caches.

        Clears:
        - Session token (~/.config/extrasuite/session.json)
        - All cached credentials (~/.config/extrasuite/credentials/*.json)
        """
        self._revoke_and_clear_session()
        cred_dir = self.CREDENTIALS_CACHE_DIR
        if cred_dir.exists():
            for path in cred_dir.glob("*.json"):
                with contextlib.suppress(Exception):
                    path.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        """Return current authentication status.

        Returns:
            Dict with keys:
            - session: dict with {active, email, expires_at, days_remaining} or None
            - credentials: dict mapping command_type → {cached, expires_at, kind}
        """
        result: dict[str, Any] = {
            "session": None,
            "credentials": {},
        }

        session = self._load_session_token()
        if session:
            remaining = int(session.expires_at - time.time())
            result["session"] = {
                "active": True,
                "email": session.email,
                "expires_at": session.expires_at,
                "days_remaining": remaining // 86400,
            }

        cred_dir = self.CREDENTIALS_CACHE_DIR
        if cred_dir.exists():
            for cache_file in sorted(cred_dir.glob("*.json")):
                cmd_type = cache_file.stem.replace("_", ".", 1)  # restore first dot
                try:
                    data = json.loads(cache_file.read_text())
                    cred = Credential.from_dict(data)
                    result["credentials"][cmd_type] = {
                        "cached": cred.is_valid(),
                        "expires_at": cred.expires_at,
                        "kind": cred.kind,
                    }
                except Exception:
                    result["credentials"][cmd_type] = {"cached": False, "invalid": True}

        return result

    def _get_or_create_session_token(self, force: bool = False) -> SessionToken:
        """Get an existing valid session token or create a new one.

        If a valid session exists in the cache, returns it immediately (headless).
        Otherwise initiates Phase 1: browser/headless OAuth flow to get an auth code,
        then exchanges it for a 30-day session token.

        Args:
            force: If True, always create a new session (for `auth login` command).
        """
        if not force:
            cached = self._load_session_token()
            if cached:
                return cached

        # Fail fast before opening a browser: if server_base_url isn't set we cannot
        # complete the session exchange even if the user authenticates successfully.
        if self._server_base_url is None:
            raise RuntimeError(
                "server_base_url is not configured; cannot use v2 session flow. "
                "Set EXTRASUITE_SERVER_URL or add it to gateway.json."
            )

        # Run browser/headless flow to get auth code
        auth_code = self._run_browser_flow_for_session()
        session_exchange_url = f"{self._server_base_url}/api/auth/session/exchange"
        device_info = self._collect_device_info()
        body = json.dumps({"code": auth_code, **device_info}).encode("utf-8")

        req = urllib.request.Request(
            session_exchange_url,
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
            raise Exception(f"Session token exchange failed: {error_body}") from e
        except urllib.error.URLError as e:
            raise Exception(f"Failed to connect to server: {e}") from e

        expires_at_dt = datetime.fromisoformat(
            result["expires_at"].replace("Z", "+00:00")
        )
        session = SessionToken(
            raw_token=result["session_token"],
            email=result["email"],
            expires_at=expires_at_dt.timestamp(),
        )
        self._save_session_token(session)
        return session

    def _run_browser_flow(self, port: int, auth_url: str, display_msg: str) -> str:
        """Run browser-based OAuth flow and return the auth code.

        Starts a local HTTP callback server, opens the browser, and also accepts
        the code from stdin (interactive fallback). Raises on error or timeout.
        """
        result_holder: dict[str, Any] = {"code": None, "error": None, "done": False}
        result_lock = threading.Lock()

        handler_class = self._create_handler_class(result_holder, result_lock)
        server = http.server.HTTPServer(("127.0.0.1", port), handler_class)
        server.timeout = 1

        def serve_loop() -> None:
            start_time = time.time()
            while time.time() - start_time < self.DEFAULT_CALLBACK_TIMEOUT:
                with result_lock:
                    if result_holder["done"]:
                        break
                server.handle_request()
            server.server_close()

        server_thread = threading.Thread(target=serve_loop, daemon=True)
        server_thread.start()

        print(f"{display_msg}\n\n  {auth_url}\n")
        try:
            import webbrowser

            webbrowser.open(auth_url)
        except Exception:
            pass
        print("Waiting for authentication...")

        def read_stdin() -> None:
            try:
                if not sys.stdin.isatty():
                    return
                while True:
                    with result_lock:
                        if result_holder["done"]:
                            return
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
                pass

        stdin_thread = threading.Thread(target=read_stdin, daemon=True)
        stdin_thread.start()

        start_time = time.time()
        while time.time() - start_time < self.DEFAULT_CALLBACK_TIMEOUT:
            with result_lock:
                if result_holder["done"]:
                    break
            time.sleep(0.5)

        with result_lock:
            result_holder["done"] = True

        if result_holder.get("error"):
            raise Exception(f"Authentication failed: {result_holder['error']}")
        code = result_holder.get("code")
        if not code:
            raise Exception("Authentication timed out. Please try again.")
        return code

    def _run_browser_flow_for_session(self) -> str:
        """Run OAuth browser flow and return the auth code.

        In headless mode: prints URL to stderr and reads code from stdin with timeout.
        Otherwise: delegates to _run_browser_flow (HTTP callback + optional stdin).
        """
        port = self._find_free_port()
        auth_url = f"{self._auth_url}?port={port}&v=2"

        if self._headless:
            print(
                f"\nOpen this URL to authenticate:\n\n  {auth_url}\n", file=sys.stderr
            )
            print("Paste the auth code here: ", end="", flush=True, file=sys.stderr)
            code_holder: list[str] = []

            def _read_code() -> None:
                try:
                    line = sys.stdin.readline().strip()
                    if line:
                        code_holder.append(line)
                except Exception:
                    pass

            reader = threading.Thread(target=_read_code, daemon=True)
            reader.start()
            reader.join(timeout=self.DEFAULT_CALLBACK_TIMEOUT)

            if not code_holder:
                raise Exception(
                    f"No auth code provided within {self.DEFAULT_CALLBACK_TIMEOUT}s. Please try again."
                )
            return code_holder[0]

        return self._run_browser_flow(port, auth_url, "Open this URL to authenticate:")

    def _exchange_session_for_credential(
        self,
        session: SessionToken,
        *,
        command: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Exchange a session token for credential(s) via a typed Command (Phase 2).

        Returns the raw response dict:
        ``{"credentials": [...], "command_type": "..."}``
        """
        if self._server_base_url is None:
            raise RuntimeError(
                "server_base_url is not configured; cannot use v2 session flow"
            )
        access_token_url = f"{self._server_base_url}/api/auth/token"
        body = json.dumps({"command": command, "reason": reason}).encode("utf-8")

        req = urllib.request.Request(
            access_token_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                # Session token goes in Authorization header (not body) to avoid
                # it being recorded in server/proxy access logs.
                "Authorization": f"Bearer {session.raw_token}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, timeout=30, context=SSL_CONTEXT
            ) as response:
                return json.loads(response.read().decode("utf-8"))  # type: ignore[return-value]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            if e.code == 401:
                raise Exception(
                    "Session expired or revoked. Run: extrasuite auth login"
                ) from e
            raise Exception(f"Access token exchange failed: {error_body}") from e
        except urllib.error.URLError as e:
            raise Exception(f"Failed to connect to server: {e}") from e

    # =========================================================================
    # Legacy v1 Auth Methods (SA only — delegation removed)
    # =========================================================================

    def _authenticate_extrasuite(self) -> Credential:
        """Run the ExtraSuite authentication flow (legacy v1 SA path)."""
        port = self._find_free_port()
        auth_url = f"{self._auth_url}?port={port}"
        auth_code = self._run_browser_flow(
            port, auth_url, "Open this URL to authenticate:"
        )
        return self._exchange_auth_code(auth_code)

    def _exchange_auth_code(self, auth_code: str) -> Credential:
        """Exchange auth code for credential via POST request to server (legacy v1)."""
        if self._exchange_url is None:
            raise RuntimeError(
                "exchange_url is not configured; cannot exchange auth code"
            )
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

        expires_at_str = result["expires_at"]
        expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        expires_at = min(
            expires_at_dt.timestamp(), time.time() + SA_TOKEN_CACHE_SECONDS
        )

        return Credential(
            provider="google",
            kind="bearer_sa",
            token=result["token"],
            expires_at=expires_at,
            scopes=[],
            metadata={"service_account_email": result.get("service_account", "")},
        )

    @staticmethod
    def _find_free_port() -> int:
        """Find an available port on 127.0.0.1."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port: int = s.getsockname()[1]
            return port

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
