"""Fake implementations for testing TokenGenerator.

These fakes allow us to control the behavior of external dependencies
(Database, Settings, IAM client, impersonated credentials) during unit tests.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from google.api_core.exceptions import NotFound
from google.auth.exceptions import RefreshError


@dataclass
class FakeUserCredentials:
    """Fake user credentials for testing."""

    email: str
    access_token: str = "fake-access-token"
    refresh_token: str = "fake-refresh-token"
    scopes: list[str] = field(default_factory=list)
    service_account_email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FakeDatabase:
    """In-memory fake database for testing.

    Provides controllable behavior for all database operations.
    """

    def __init__(self) -> None:
        self.users: dict[str, FakeUserCredentials] = {}
        self.oauth_states: dict[str, str] = {}
        self._should_fail_get_user: bool = False
        self._should_fail_update_sa: bool = False

    async def get_user_credentials(self, email: str) -> FakeUserCredentials | None:
        """Get user credentials by email."""
        if self._should_fail_get_user:
            raise TimeoutError("Simulated database timeout")
        return self.users.get(email)

    async def store_user_credentials(
        self,
        email: str,
        access_token: str,
        refresh_token: str,
        scopes: list[str],
        service_account_email: str | None = None,
    ) -> FakeUserCredentials:
        """Store or update user OAuth credentials."""
        now = datetime.now(UTC)
        creds = FakeUserCredentials(
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            service_account_email=service_account_email,
            created_at=self.users.get(email, FakeUserCredentials(email=email)).created_at or now,
            updated_at=now,
        )
        self.users[email] = creds
        return creds

    async def update_service_account_email(self, email: str, service_account_email: str) -> None:
        """Update the service account email for a user."""
        if self._should_fail_update_sa:
            raise TimeoutError("Simulated database timeout")
        if email in self.users:
            self.users[email].service_account_email = service_account_email
        else:
            # Create minimal user record if it doesn't exist
            self.users[email] = FakeUserCredentials(
                email=email,
                service_account_email=service_account_email,
            )

    async def save_state(self, state: str, redirect_url: str) -> None:
        """Save OAuth state token with redirect URL."""
        self.oauth_states[state] = redirect_url

    async def retrieve_state(self, state: str) -> str | None:
        """Retrieve AND delete OAuth state."""
        return self.oauth_states.pop(state, None)


class FakeSettings:
    """Fake settings for testing.

    Provides controllable behavior for settings.
    """

    def __init__(
        self,
        google_cloud_project: str = "test-project",
        domain_abbreviations: dict[str, str] | None = None,
    ) -> None:
        self.google_cloud_project = google_cloud_project
        self._domain_abbreviations = domain_abbreviations or {}

    def get_domain_abbreviation(self, domain: str) -> str:
        """Get abbreviation for a domain."""
        if domain.lower() in self._domain_abbreviations:
            return self._domain_abbreviations[domain.lower()]
        # Fallback: 4-char hash of domain
        return hashlib.sha256(domain.lower().encode()).hexdigest()[:4]


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
