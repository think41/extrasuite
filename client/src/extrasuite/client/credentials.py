"""Credentials management for Google API access.

Supports two authentication modes:
1. ExtraSuite server - v2 session-token protocol
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
from typing import Any, Protocol

# Try to use certifi for SSL certificates (common on macOS)
try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

try:
    import keyring as _keyring

    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE = "extrasuite"
_DEFAULT_PROFILE = "default"
_GOOGLE_SCOPE_PREFIX = "https://www.googleapis.com/auth/"

# Client-side caps on returned token lifetimes
_SA_TOKEN_CAP_SECONDS = 3600  # 60 min for service account tokens
_DWD_TOKEN_CAP_SECONDS = 600  # 10 min for domain-wide delegation tokens


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


def _parse_first_google_credential(
    response: dict[str, Any], cmd_type: str
) -> Credential:
    """Extract and normalise the first Google credential from a TokenResponse dict.

    Caps expiry at the appropriate client-side TTL so the lifetime is bounded
    regardless of what the server returns.
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
    cap = _DWD_TOKEN_CAP_SECONDS if kind == "bearer_dwd" else _SA_TOKEN_CAP_SECONDS
    expires_at = min(raw_expires, time.time() + cap) if raw_expires else 0.0

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


class SessionStore(Protocol):
    """Protocol for session token storage backends."""

    def load(self, profile_name: str) -> SessionToken | None: ...
    def save(self, profile_name: str, token: SessionToken) -> None: ...
    def delete(self, profile_name: str) -> None: ...


class KeyringSessionStore:
    """Session token storage backed by the OS keyring."""

    def load(self, profile_name: str) -> SessionToken | None:
        raw = _keyring.get_password(_KEYRING_SERVICE, profile_name)
        if not raw:
            return None
        try:
            token = SessionToken.from_dict(json.loads(raw))
            return token if token.is_valid() else None
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, profile_name: str, token: SessionToken) -> None:
        _keyring.set_password(
            _KEYRING_SERVICE, profile_name, json.dumps(token.to_dict())
        )

    def delete(self, profile_name: str) -> None:
        with contextlib.suppress(Exception):
            _keyring.delete_password(_KEYRING_SERVICE, profile_name)


class InMemorySessionStore:
    """In-memory session token storage (for testing and non-persistent use)."""

    def __init__(self) -> None:
        self._tokens: dict[str, SessionToken] = {}

    def load(self, profile_name: str) -> SessionToken | None:
        token = self._tokens.get(profile_name)
        if token and token.is_valid():
            return token
        return None

    def save(self, profile_name: str, token: SessionToken) -> None:
        self._tokens[profile_name] = token

    def delete(self, profile_name: str) -> None:
        self._tokens.pop(profile_name, None)


class CredentialsManager:
    """Manages credentials for Google API access.

    Supports two authentication modes:
    1. ExtraSuite protocol - obtains short-lived tokens via the v2 session flow
    2. Service account file - uses credentials from a JSON key file

    Session tokens are stored in the OS keyring (macOS Keychain, Linux
    SecretService, Windows Credential Locker).  Access tokens are never
    written to disk.

    Profile metadata (name → email, active pointer) is kept in
    ``~/.config/extrasuite/profiles.json`` (0600). No tokens in that file.

    Precedence order for configuration:
    1. Constructor parameters
    2. Environment variables (EXTRASUITE_SERVER_URL)
    3. ~/.config/extrasuite/gateway.json (created by install script)
    4. service_account_path constructor parameter / SERVICE_ACCOUNT_PATH env var

    Args:
        server_url: Base URL for the ExtraSuite server
            (e.g., "https://server.com").
        service_account_path: Path to service account JSON file (optional).
        gateway_config_path: Path to gateway.json. Defaults to
            ~/.config/extrasuite/gateway.json.  If explicitly set and file
            doesn't exist, raises FileNotFoundError.
        profile: Profile name to use.  Defaults to the active profile in
            profiles.json, or "default" if no active profile is set.
    """

    GATEWAY_CONFIG_PATH = Path.home() / ".config" / "extrasuite" / "gateway.json"
    DEFAULT_CALLBACK_TIMEOUT = 300  # 5 minutes for headless mode

    def __init__(
        self,
        server_url: str | None = None,
        service_account_path: str | Path | None = None,
        gateway_config_path: str | Path | None = None,
        headless: bool | None = None,
        profile: str | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        # Store explicit gateway path (used by _load_gateway_config)
        self._gateway_config_path = (
            Path(gateway_config_path) if gateway_config_path else None
        )

        # Profile name override (None = use active from profiles.json)
        self._profile_name = profile

        # Headless mode: no browser, print URL and prompt for code on stderr
        # Precedence: constructor param > EXTRASUITE_HEADLESS env var
        if headless is not None:
            self._headless = headless
        else:
            self._headless = os.environ.get("EXTRASUITE_HEADLESS", "").strip() == "1"

        # Resolve configuration with precedence: constructor > env var > gateway.json
        self._server_base_url = (
            server_url or os.environ.get("EXTRASUITE_SERVER_URL") or None
        )
        if self._server_base_url:
            self._server_base_url = self._server_base_url.rstrip("/")

        if not self._server_base_url:
            gateway_urls = self._load_gateway_config()
            if gateway_urls:
                self._server_base_url = gateway_urls.get("server_base_url")

        sa_path = service_account_path or os.environ.get("SERVICE_ACCOUNT_PATH")
        self._sa_path = Path(sa_path) if sa_path else None

        # Validate that at least one auth method is configured
        has_extrasuite = bool(self._server_base_url)
        if not has_extrasuite and not self._sa_path:
            raise ValueError(
                "No authentication method configured.\n\n"
                "Fix with ONE of these options:\n"
                "  1. Pass --gateway /path/to/gateway.json (contains EXTRASUITE_SERVER_URL)\n"
                "  2. Pass --service-account /path/to/sa.json (direct Google credentials)\n"
                "  3. Set EXTRASUITE_SERVER_URL environment variable\n"
                "  4. Create ~/.config/extrasuite/gateway.json with:\n"
                '     {"EXTRASUITE_SERVER_URL": "https://your-server.example.com"}'
            )

        # ExtraSuite protocol takes precedence if both are configured
        self._use_extrasuite = has_extrasuite

        if session_store is not None:
            self._session_store: SessionStore = session_store
        elif self._use_extrasuite:
            if not _KEYRING_AVAILABLE:
                raise RuntimeError(
                    "keyring package is required but is not installed.\n"
                    "Install it with: pip install keyring"
                )
            self._session_store = KeyringSessionStore()
        else:
            self._session_store = InMemorySessionStore()

        # Migrate legacy plain-text files from pre-keyring versions
        self._migrate_legacy_files()

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

        For ExtraSuite mode: validates the session, POSTs to /api/auth/token and
        returns the credential.  Access tokens are never written to disk.

        For service account file mode: generates a token directly from the SA key.
        Only meaningful for SA-backed command types; DWD is not supported in this
        mode.

        Args:
            command: Dict representation of a typed Command (must include ``type``).
            reason: Agent-supplied user intent (logged for auditing).
            force_refresh: Accepted for API compatibility; has no effect since
                access tokens are no longer cached.

        Returns:
            A Credential object with ``token``, ``kind``, ``service_account_email``, etc.
        """
        cmd_type = command.get("type", "")

        if self._use_extrasuite:
            return self._get_extrasuite_credential(
                command=command,
                cmd_type=cmd_type,
                reason=reason,
            )
        else:
            return self._get_service_account_credential()

    # =========================================================================
    # Profile helpers
    # =========================================================================

    def _profiles_path(self) -> Path:
        return Path.home() / ".config" / "extrasuite" / "profiles.json"

    def _load_profiles(self) -> dict[str, Any]:
        """Read profiles.json; return empty structure if absent or invalid."""
        path = self._profiles_path()
        if not path.exists():
            return {"profiles": {}, "active": None}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"profiles": {}, "active": None}

    def _save_profiles(self, data: dict[str, Any]) -> None:
        """Write profiles.json with 0600 permissions."""
        self._write_secure_json(self._profiles_path(), data)

    def _resolve_profile(self) -> str:
        """Return the profile name to use for this operation."""
        if self._profile_name:
            return self._profile_name
        data = self._load_profiles()
        active = data.get("active")
        return active if active else _DEFAULT_PROFILE

    # =========================================================================
    # Session Token Methods (keyring-backed)
    # =========================================================================

    def _load_session_token(
        self, profile_name: str | None = None
    ) -> SessionToken | None:
        """Load session token for the given profile."""
        name = profile_name if profile_name is not None else self._resolve_profile()
        return self._session_store.load(name)

    def _save_session_token(self, token: SessionToken, profile_name: str) -> None:
        """Save session token and update profile email in profiles.json."""
        self._session_store.save(profile_name, token)
        data = self._load_profiles()
        data.setdefault("profiles", {})[profile_name] = token.email
        self._save_profiles(data)

    def _revoke_server_side(self, raw_token: str) -> None:
        """Revoke a session token on the server.  Best-effort; logs warning on failure."""
        if not self._server_base_url:
            return
        try:
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

    def _delete_session_token(self, profile_name: str) -> None:
        """Remove the session token for a profile from storage."""
        self._session_store.delete(profile_name)

    def _migrate_legacy_files(self) -> None:
        """Delete legacy plain-text session/credential files from pre-keyring versions."""
        legacy_session = Path.home() / ".config" / "extrasuite" / "session.json"
        legacy_creds_dir = Path.home() / ".config" / "extrasuite" / "credentials"
        with contextlib.suppress(Exception):
            legacy_session.unlink(missing_ok=True)
        if legacy_creds_dir.exists():
            for path in legacy_creds_dir.glob("*.json"):
                with contextlib.suppress(Exception):
                    path.unlink(missing_ok=True)
            with contextlib.suppress(Exception):
                legacy_creds_dir.rmdir()

    # =========================================================================
    # Public auth commands
    # =========================================================================

    def login(self, *, force: bool = False, profile: str | None = None) -> SessionToken:
        """Log in and obtain a 30-day session token.

        If a valid session already exists and force=False, returns it immediately.

        If force=True, revokes any existing session server-side before issuing a
        new one.  This is the correct way to rotate credentials if a session may
        be compromised.

        Note: This call collects device fingerprint information (MAC address,
        hostname, OS, platform) that is sent to the ExtraSuite server for audit.

        Args:
            force: If True, always create a new session even if one exists.
            profile: Profile name to log in to.  Defaults to the active profile,
                or "default" if none is set.

        Returns:
            A valid SessionToken.
        """
        profile_name = profile if profile is not None else self._resolve_profile()
        if force:
            existing = self._load_session_token(profile_name)
            if existing:
                self._revoke_server_side(existing.raw_token)
            self._delete_session_token(profile_name)
        session = self._get_or_create_session_token(
            force=force, profile_name=profile_name
        )
        # Set this profile as active
        data = self._load_profiles()
        data["active"] = profile_name
        self._save_profiles(data)
        return session

    def logout(self, *, profile: str | None = None) -> None:
        """Revoke the session server-side and remove it from the OS keyring.

        Args:
            profile: Profile to log out.  Defaults to the active profile.
        """
        profile_name = profile if profile is not None else self._resolve_profile()
        session = self._load_session_token(profile_name)
        if session:
            self._revoke_server_side(session.raw_token)
        self._delete_session_token(profile_name)
        data = self._load_profiles()
        data.get("profiles", {}).pop(profile_name, None)
        if data.get("active") == profile_name:
            data["active"] = None
        self._save_profiles(data)

    def activate(self, profile_name: str) -> None:
        """Set the active profile (no network call).

        Args:
            profile_name: Name of an existing profile to activate.

        Raises:
            ValueError: If the profile is not found in profiles.json.
        """
        data = self._load_profiles()
        if profile_name not in data.get("profiles", {}):
            raise ValueError(
                f"Profile '{profile_name}' not found. "
                f"Run: extrasuite auth login --profile {profile_name}"
            )
        data["active"] = profile_name
        self._save_profiles(data)

    def status(self) -> dict[str, Any]:
        """Return current authentication status.

        Returns:
            Dict with keys:
            - profiles: mapping of profile name → {email, active, expires_at,
              days_remaining} or {email, active=False, expired=True}
            - active: name of the active profile, or None
        """
        if not self._use_extrasuite:
            return {"profiles": {}, "active": None}

        data = self._load_profiles()
        profiles: dict[str, Any] = data.get("profiles", {})
        active = data.get("active")

        result: dict[str, Any] = {"profiles": {}, "active": active}
        for name, email in profiles.items():
            session = self._load_session_token(name)
            if session:
                remaining = int(session.expires_at - time.time())
                result["profiles"][name] = {
                    "email": email,
                    "active": True,
                    "expires_at": session.expires_at,
                    "days_remaining": remaining // 86400,
                }
            else:
                result["profiles"][name] = {
                    "email": email,
                    "active": False,
                    "expired": True,
                }
        return result

    # =========================================================================
    # Credential exchange (no disk caching)
    # =========================================================================

    def _get_extrasuite_credential(
        self,
        *,
        command: dict[str, Any],
        cmd_type: str,
        reason: str,
    ) -> Credential:
        """Get credential via ExtraSuite server (v2 session flow).

        Always fetches fresh — access tokens are never written to disk.
        """
        session = self._get_or_create_session_token()
        result = self._exchange_session_for_credential(
            session, command=command, reason=reason
        )
        return _parse_first_google_credential(result, cmd_type)

    def _get_service_account_credential(self) -> Credential:
        """Get credential from a service account JSON key file.

        Generates a fresh token on every call — no disk caching.
        """
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

        return Credential(
            provider="google",
            kind="bearer_sa",
            token=credentials.token,
            expires_at=credentials.expiry.timestamp() if credentials.expiry else 0,
            scopes=[],
            metadata={"service_account_email": credentials.service_account_email},
        )

    def _load_gateway_config(self) -> dict[str, str] | None:
        """Load endpoint URLs from gateway.json if it exists.

        Supports this format in gateway.json:
        - EXTRASUITE_SERVER_URL: Base URL for the server (preferred)

        Returns:
            Dictionary with the resolved server base URL, or None if file not found.

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

            server_url = data.get("EXTRASUITE_SERVER_URL")
            if server_url:
                server_url = server_url.rstrip("/")
                result["server_base_url"] = server_url

            return result if result else None
        except (json.JSONDecodeError, OSError):
            return None

    # =========================================================================
    # Session Token Creation (v2 Protocol)
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

    def _get_or_create_session_token(
        self, force: bool = False, profile_name: str | None = None
    ) -> SessionToken:
        """Get an existing valid session token or create a new one.

        If a valid session exists in the keyring, returns it immediately.
        Otherwise initiates Phase 1: browser/headless OAuth flow to get an auth
        code, then exchanges it for a 30-day session token.

        Args:
            force: If True, always create a new session (skips cache check).
            profile_name: Profile to load/store token for.  Defaults to
                _resolve_profile().
        """
        name = profile_name if profile_name is not None else self._resolve_profile()
        if not force:
            cached = self._load_session_token(name)
            if cached:
                return cached

        # Fail fast before opening a browser: if server_base_url isn't set we cannot
        # complete the session exchange even if the user authenticates successfully.
        if self._server_base_url is None:
            raise RuntimeError(
                "server_base_url is not configured; cannot use session flow. "
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
            if e.code == 400:
                raise Exception(
                    "Auth code invalid or expired. Please re-authenticate: extrasuite auth login"
                ) from e
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
        self._save_session_token(session, name)
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

        In headless mode: calls /api/token/auth (no port), which shows the auth
        code on an HTML page instead of redirecting to localhost. Prints the URL
        to stderr and reads the code from stdin — no local callback server needed.

        Otherwise: starts a local HTTP callback server, opens the browser, and
        waits for the redirect from the ExtraSuite server.
        """
        if self._headless:
            auth_url = f"{self._server_base_url}/api/token/auth"
            print(
                f"\nOpen this URL to authenticate:\n\n  {auth_url}\n",
                file=sys.stderr,
            )
            print(
                "After authenticating, copy the code shown on the page and paste it here: ",
                end="",
                flush=True,
                file=sys.stderr,
            )
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

        port = self._find_free_port()
        auth_url = f"{self._server_base_url}/api/token/auth?port={port}"
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
                "server_base_url is not configured; cannot use session flow"
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
