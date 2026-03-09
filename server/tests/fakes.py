"""Fake implementations for testing TokenGenerator.

These fakes allow us to control the behavior of external dependencies
(Database, Settings, IAM client, impersonated credentials) during unit tests.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from google.api_core.exceptions import NotFound
from google.auth.exceptions import RefreshError

from extrasuite.server.database import RefreshTokenNotFound, RefreshTokenRecord

# Auth code TTL matching the real database
AUTH_CODE_TTL = timedelta(seconds=120)


class FakeDatabase:
    """In-memory fake database for testing.

    Provides controllable behavior for all database operations.
    """

    def __init__(self) -> None:
        # Simple mapping: email -> service_account_email
        self.users: dict[str, str] = {}
        self.oauth_states: dict[str, dict[str, Any]] = {}
        self.auth_codes: dict[str, dict[str, Any]] = {}
        self.session_tokens: dict[str, dict[str, Any]] = {}
        self.access_logs: list[dict[str, Any]] = []
        # email -> {encrypted_token, scopes}
        self._refresh_tokens: dict[str, dict[str, str]] = {}
        self._should_fail_get_sa: bool = False
        self._should_fail_set_sa: bool = False

    async def get_service_account_email(self, email: str) -> str | None:
        """Get service account email for a user."""
        if self._should_fail_get_sa:
            raise TimeoutError("Simulated database timeout")
        return self.users.get(email)

    async def set_service_account_email(self, email: str, service_account_email: str) -> None:
        """Set the service account email for a user."""
        if self._should_fail_set_sa:
            raise TimeoutError("Simulated database timeout")
        self.users[email] = service_account_email

    async def save_state(self, state: str, redirect_url: str) -> None:
        """Save OAuth state token with redirect URL."""
        self.oauth_states[state] = {"redirect_url": redirect_url}

    async def retrieve_state(self, state: str) -> dict[str, Any] | None:
        """Retrieve AND delete OAuth state."""
        return self.oauth_states.pop(state, None)

    async def save_auth_code(
        self, auth_code: str, service_account_email: str, user_email: str
    ) -> None:
        """Save auth code with associated service account and user email."""
        self.auth_codes[auth_code] = {
            "service_account_email": service_account_email,
            "user_email": user_email,
            "expires_at": datetime.now(UTC) + AUTH_CODE_TTL,
        }

    async def retrieve_auth_code(self, auth_code: str) -> dict[str, str] | None:
        """Retrieve AND delete auth code. Returns {service_account_email, user_email} or None."""
        if auth_code not in self.auth_codes:
            return None

        data = self.auth_codes[auth_code]

        expires_at = data.get("expires_at")
        if not expires_at or datetime.now(UTC) > expires_at:
            self.auth_codes.pop(auth_code)
            return None

        self.auth_codes.pop(auth_code)
        return {
            "service_account_email": data.get("service_account_email", ""),
            "user_email": data.get("user_email", ""),
        }

    async def save_session_token(
        self,
        token_hash: str,
        email: str,
        device_ip: str = "",
        device_mac: str = "",
        device_hostname: str = "",
        device_os: str = "",
        device_platform: str = "",
        expiry_days: int = 30,
    ) -> None:
        """Save a session token."""
        now = datetime.now(UTC)
        self.session_tokens[token_hash] = {
            "email": email,
            "created_at": now,
            "revoked_at": None,
            "active_expires_at": now + timedelta(days=expiry_days),
            "device_ip": device_ip,
            "device_mac": device_mac,
            "device_hostname": device_hostname,
            "device_os": device_os,
            "device_platform": device_platform,
        }

    async def validate_session_token(self, token_hash: str) -> dict | None:
        """Validate a session token."""
        data = self.session_tokens.get(token_hash)
        if not data:
            return None
        if data.get("revoked_at") is not None:
            return None
        if datetime.now(UTC) > data["active_expires_at"]:
            return None
        return {"email": data["email"], "created_at": data["created_at"]}

    async def revoke_session_token(self, token_hash: str, expected_email: str = "") -> bool:
        """Revoke a session token. Returns False if not found or email mismatch."""
        if token_hash not in self.session_tokens:
            return False
        if expected_email:
            stored_email = self.session_tokens[token_hash].get("email", "")
            if stored_email.lower() != expected_email.lower():
                return False
        self.session_tokens[token_hash]["revoked_at"] = datetime.now(UTC)
        return True

    async def revoke_all_session_tokens(self, email: str) -> int:
        """Revoke all sessions for email."""
        count = 0
        now = datetime.now(UTC)
        for data in self.session_tokens.values():
            if (
                data["email"] == email
                and data["revoked_at"] is None
                and data["active_expires_at"] > now
            ):
                data["revoked_at"] = now
                count += 1
        return count

    async def list_session_tokens(self, email: str) -> list[dict]:
        """List active sessions for email."""
        now = datetime.now(UTC)
        return [
            {
                "session_hash": h,
                "session_hash_prefix": h[:16],
                "created_at": d["created_at"],
                "active_expires_at": d["active_expires_at"],
                "device_hostname": d.get("device_hostname", ""),
                "device_os": d.get("device_os", ""),
                "device_ip": d.get("device_ip", ""),
                "is_active": True,
            }
            for h, d in self.session_tokens.items()
            if d["email"] == email and d["revoked_at"] is None and d["active_expires_at"] > now
        ]

    async def log_access_token_request(
        self,
        email: str,
        session_hash_prefix: str,
        command_type: str,
        command_context: dict,
        reason: str,
        ip: str,
        credential_kind: str = "",
    ) -> None:
        """Log an access token request."""
        self.access_logs.append(
            {
                "email": email,
                "session_hash_prefix": session_hash_prefix,
                "command_type": command_type,
                "command_context": command_context,
                "reason": reason,
                "ip": ip,
                "credential_kind": credential_kind,
                "timestamp": datetime.now(UTC),
            }
        )

    async def get_refresh_token(self, email: str) -> RefreshTokenRecord:
        """Get the stored refresh token record for a user.

        Raises:
            RefreshTokenNotFound: If no token is stored for this user.
        """
        user_data = self._refresh_tokens.get(email)
        if user_data is None:
            raise RefreshTokenNotFound(email)
        encrypted = user_data.get("encrypted_token", "")
        if not encrypted:
            raise RefreshTokenNotFound(email)
        scopes_str = user_data.get("scopes", "")
        scopes = tuple(scopes_str.split()) if scopes_str else ()
        return RefreshTokenRecord(encrypted_token=encrypted, scopes=scopes)

    async def set_refresh_token(self, email: str, encrypted: str, scopes: str) -> None:
        """Store encrypted refresh token for a user."""
        self._refresh_tokens[email] = {"encrypted_token": encrypted, "scopes": scopes}

    async def delete_refresh_token(self, email: str) -> None:
        """Remove refresh token for a user."""
        self._refresh_tokens.pop(email, None)


class FakeSettings:
    """Fake settings for testing.

    Provides controllable behavior for settings.
    """

    def __init__(
        self,
        google_cloud_project: str = "test-project",
        domain_abbreviations: dict[str, str] | None = None,
        token_expiry_minutes: int = 60,
        delegation_enabled: bool = False,
        delegation_scopes: list[str] | None = None,
        session_token_expiry_days: int = 30,
        admin_emails: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        credential_mode: str = "sa+dwd",
        oauth_scopes: str = "",
        oauth_token_encryption_key: str = "",
        google_client_id: str = "test-client-id",
        google_client_secret: str = "test-client-secret",
    ) -> None:
        _ = delegation_enabled
        self.google_cloud_project = google_cloud_project
        self._domain_abbreviations = domain_abbreviations or {}
        self.token_expiry_minutes = token_expiry_minutes
        self._delegation_scopes = delegation_scopes or []
        self.session_token_expiry_days = session_token_expiry_days
        self._admin_emails = [e.lower() for e in (admin_emails or [])]
        self._allowed_domains = [d.lower() for d in (allowed_domains or [])]
        self.credential_mode = credential_mode
        self.oauth_scopes = oauth_scopes
        self.oauth_token_encryption_key = oauth_token_encryption_key
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret

    @property
    def uses_oauth(self) -> bool:
        return self.credential_mode != "sa+dwd"

    def get_oauth_scope_urls(self) -> list[str]:
        if not self.oauth_scopes:
            return []
        prefix = "https://www.googleapis.com/auth/"
        return [f"{prefix}{s.strip()}" for s in self.oauth_scopes.split(",") if s.strip()]

    def get_domain_abbreviation(self, domain: str) -> str:
        """Get abbreviation for a domain."""
        if domain.lower() in self._domain_abbreviations:
            return self._domain_abbreviations[domain.lower()]
        # Fallback: 4-char hash of domain
        return hashlib.sha256(domain.lower().encode()).hexdigest()[:4]

    def get_delegation_scopes(self) -> list[str]:
        """Get configured delegation scopes."""
        return self._delegation_scopes

    def is_scope_allowed(self, scope_url: str) -> bool:
        """Check if a scope is allowed."""
        if not self._delegation_scopes:
            return True
        return scope_url in self._delegation_scopes

    def is_email_domain_allowed(self, email: str) -> bool:
        """Check if an email's domain is allowed.

        Returns True if no domain restriction is configured, or if the email's
        domain matches one of the allowed domains.
        """
        if not self._allowed_domains:
            return True
        if "@" not in email:
            return False
        domain = email.split("@")[-1].lower()
        return domain in self._allowed_domains

    def get_admin_emails(self) -> list[str]:
        """Get list of admin email addresses."""
        return list(self._admin_emails)


class FakeImpersonatedCredentials:
    """Fake impersonated credentials for testing.

    Can be configured to succeed or fail with various errors.
    """

    def __init__(
        self,
        source_credentials: Any,
        target_principal: str,
        target_scopes: list[str],
        lifetime: int,
        *,
        # Test control parameters (set via class attribute before instantiation)
        _should_fail: bool = False,
        _fail_with: Exception | None = None,
        _token: str = "fake-sa-token-12345",
    ) -> None:
        self.source_credentials = source_credentials
        self.target_principal = target_principal
        self.target_scopes = target_scopes
        self.lifetime = lifetime
        self.token: str | None = None
        self._should_fail = _should_fail
        self._fail_with = _fail_with
        self._token = _token

    def refresh(self, _request: Any) -> None:
        """Refresh credentials to get a token."""
        if self._should_fail:
            if self._fail_with:
                raise self._fail_with
            raise RefreshError("Fake refresh error")
        self.token = self._token


def create_fake_impersonated_credentials_class(
    *,
    should_fail: bool = False,
    fail_with: Exception | None = None,
    token: str = "fake-sa-token-12345",
) -> type:
    """Factory to create a FakeImpersonatedCredentials class with preset behavior.

    Usage:
        FakeCreds = create_fake_impersonated_credentials_class(should_fail=True)
        generator = TokenGenerator(db, settings, impersonated_credentials_class=FakeCreds)
    """

    class ConfiguredFakeImpersonatedCredentials(FakeImpersonatedCredentials):
        def __init__(
            self,
            source_credentials: Any,
            target_principal: str,
            target_scopes: list[str],
            lifetime: int,
        ) -> None:
            super().__init__(
                source_credentials,
                target_principal,
                target_scopes,
                lifetime,
                _should_fail=should_fail,
                _fail_with=fail_with,
                _token=token,
            )

    return ConfiguredFakeImpersonatedCredentials


@dataclass
class FakeServiceAccount:
    """Fake service account returned by IAM client."""

    email: str
    display_name: str = ""
    description: str = ""


class FakeIAMAsyncClient:
    """Fake async IAM client for testing service account operations.

    Simulates the Google IAM Admin API for service account creation and management.
    """

    def __init__(self, project_id: str = "test-project") -> None:
        self.project_id = project_id
        self.service_accounts: dict[str, FakeServiceAccount] = {}
        self.iam_policies: dict[str, Any] = {}
        self.should_fail_create: bool = False
        self.should_fail_get: bool = False
        self.should_fail_get_iam_policy: bool = False
        self.should_fail_set_iam_policy: bool = False
        self.create_failure_exception: Exception | None = None
        self.get_failure_exception: Exception | None = None

    async def get_service_account(self, request: Any) -> FakeServiceAccount:
        """Get a service account."""
        if self.should_fail_get:
            if self.get_failure_exception:
                raise self.get_failure_exception
            raise Exception("Simulated get failure")

        # Extract SA email from name like "projects/proj/serviceAccounts/sa@proj.iam..."
        name = request.name
        sa_email = name.split("/")[-1]

        if sa_email not in self.service_accounts:
            raise NotFound(f"Service account {sa_email} not found")

        return self.service_accounts[sa_email]

    async def create_service_account(self, request: Any) -> FakeServiceAccount:
        """Create a service account."""
        if self.should_fail_create:
            if self.create_failure_exception:
                raise self.create_failure_exception
            raise Exception("Simulated create failure")

        account_id = request.account_id
        # Extract project from name like "projects/proj"
        project_id = request.name.split("/")[1]
        sa_email = f"{account_id}@{project_id}.iam.gserviceaccount.com"

        sa = FakeServiceAccount(
            email=sa_email,
            display_name=request.service_account.display_name if request.service_account else "",
            description=request.service_account.description if request.service_account else "",
        )
        self.service_accounts[sa_email] = sa
        return sa

    async def get_iam_policy(self, request: Any) -> Any:
        """Get IAM policy for a resource."""
        if self.should_fail_get_iam_policy:
            raise Exception("Simulated getIamPolicy failure")

        resource = request.resource

        # Return a fake policy object with bindings list
        class FakePolicy:
            def __init__(self, bindings: list[Any] | None = None):
                self.bindings = bindings or []

        return self.iam_policies.get(resource, FakePolicy())

    async def set_iam_policy(self, request: Any) -> Any:
        """Set IAM policy for a resource."""
        if self.should_fail_set_iam_policy:
            raise Exception("Simulated setIamPolicy failure")

        resource = request.resource
        self.iam_policies[resource] = request.policy
        return request.policy
