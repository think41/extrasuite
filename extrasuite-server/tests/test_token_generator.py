"""Unit tests for TokenGenerator."""

from datetime import UTC, datetime, timedelta

import pytest
from google.auth.exceptions import RefreshError

from extrasuite_server.token_generator import (
    GeneratedToken,
    ImpersonationError,
    ServiceAccountCreationError,
    TokenGenerator,
    sanitize_email_for_account_id,
)
from tests.fakes import (
    FakeDatabase,
    FakeIAMAsyncClient,
    FakeSettings,
    create_fake_impersonated_credentials_class,
)


class TestSanitizeEmailForAccountId:
    """Tests for sanitize_email_for_account_id function."""

    def test_simple_email(self) -> None:
        """Simple email produces valid account ID with domain suffix."""
        result = sanitize_email_for_account_id("john@example.com", "ex")
        assert result == "john-ex"

    def test_email_with_dots(self) -> None:
        """Dots in email are replaced with hyphens."""
        result = sanitize_email_for_account_id("john.doe@example.com", "ex")
        assert result == "john-doe-ex"

    def test_email_with_plus(self) -> None:
        """Plus signs are replaced with hyphens."""
        result = sanitize_email_for_account_id("john+test@example.com", "ex")
        assert result == "john-test-ex"

    def test_email_with_numbers_at_start(self) -> None:
        """Numbers at start get u prefix."""
        result = sanitize_email_for_account_id("123user@example.com", "ex")
        assert result.startswith("u")
        assert "123" in result
        assert result.endswith("-ex")

    def test_short_email(self) -> None:
        """Short email is padded to minimum length."""
        result = sanitize_email_for_account_id("ab@example.com", "ex")
        assert len(result) >= 6

    def test_long_email(self) -> None:
        """Long email is truncated to 30 characters."""
        result = sanitize_email_for_account_id(
            "verylongemailaddressthatexceeds30chars@example.com", "ex"
        )
        assert len(result) <= 30

    def test_uppercase_converted(self) -> None:
        """Uppercase letters are converted to lowercase."""
        result = sanitize_email_for_account_id("John.Doe@Example.com", "EX")
        assert result == result.lower()

    def test_consecutive_special_chars(self) -> None:
        """Consecutive special chars become single hyphen."""
        result = sanitize_email_for_account_id("john..doe@example.com", "ex")
        assert "--" not in result

    def test_domain_abbreviation_included(self) -> None:
        """Domain abbreviation is included in the result."""
        result = sanitize_email_for_account_id("sripathi@recruit41.com", "r41")
        assert result == "sripathi-r41"

    def test_different_domains_different_results(self) -> None:
        """Same local part with different domain abbreviations produce different results."""
        result1 = sanitize_email_for_account_id("sripathi@recruit41.com", "r41")
        result2 = sanitize_email_for_account_id("sripathi@think41.com", "t41")
        assert result1 != result2
        assert result1 == "sripathi-r41"
        assert result2 == "sripathi-t41"


class TestTokenGenerator:
    """Tests for TokenGenerator class."""

    @pytest.fixture
    def fake_db(self) -> FakeDatabase:
        """Create a fake database."""
        return FakeDatabase()

    @pytest.fixture
    def fake_settings(self) -> FakeSettings:
        """Create fake settings with domain abbreviations."""
        return FakeSettings(
            google_cloud_project="test-project",
            domain_abbreviations={
                "example.com": "ex",
                "recruit41.com": "r41",
                "think41.com": "t41",
            },
        )

    @pytest.fixture
    def fake_iam(self) -> FakeIAMAsyncClient:
        """Create a fake IAM client."""
        return FakeIAMAsyncClient(project_id="test-project")

    @pytest.fixture
    def generator(
        self, fake_db: FakeDatabase, fake_settings: FakeSettings, fake_iam: FakeIAMAsyncClient
    ) -> TokenGenerator:
        """Create a TokenGenerator with fake dependencies."""
        FakeCreds = create_fake_impersonated_credentials_class()
        return TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

    # Happy path tests

    @pytest.mark.asyncio
    async def test_generate_token_new_user_creates_sa(
        self,
        generator: TokenGenerator,
        fake_db: FakeDatabase,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """New user should get a new service account created."""
        result = await generator.generate_token("newuser@example.com", "New User")

        assert result.token == "fake-sa-token-12345"
        assert result.service_account_email.startswith("newuser-ex@")
        assert result.expires_at > datetime.now(UTC)

        # SA should be created in IAM
        assert len(fake_iam.service_accounts) == 1

        # SA email should be stored in database
        sa_email = fake_db.users.get("newuser@example.com")
        assert sa_email is not None
        assert sa_email == result.service_account_email

    @pytest.mark.asyncio
    async def test_generate_token_existing_user_reuses_sa(
        self,
        generator: TokenGenerator,
        fake_db: FakeDatabase,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """Existing user should reuse their service account."""
        # Setup: user already has SA
        existing_sa = "existing-ex@test-project.iam.gserviceaccount.com"
        fake_db.users["existing@example.com"] = existing_sa

        result = await generator.generate_token("existing@example.com")

        assert result.service_account_email == existing_sa
        # No new SA should be created
        assert len(fake_iam.service_accounts) == 0

    @pytest.mark.asyncio
    async def test_expires_at_is_absolute_time(self, generator: TokenGenerator) -> None:
        """expires_at should be an absolute datetime, not relative seconds."""
        before = datetime.now(UTC)
        result = await generator.generate_token("user@example.com")
        after = datetime.now(UTC)

        # Should be approximately 1 hour in the future
        expected_min = before + timedelta(hours=1) - timedelta(seconds=10)
        expected_max = after + timedelta(hours=1) + timedelta(seconds=10)

        assert expected_min <= result.expires_at <= expected_max

    @pytest.mark.asyncio
    async def test_returns_generated_token_dataclass(self, generator: TokenGenerator) -> None:
        """Result should be a GeneratedToken instance."""
        result = await generator.generate_token("user@example.com")

        assert isinstance(result, GeneratedToken)
        assert hasattr(result, "token")
        assert hasattr(result, "expires_at")
        assert hasattr(result, "service_account_email")

    # Domain abbreviation tests

    @pytest.mark.asyncio
    async def test_domain_abbreviation_used_in_sa_name(
        self,
        generator: TokenGenerator,
    ) -> None:
        """Service account name should include domain abbreviation."""
        result = await generator.generate_token("sripathi@recruit41.com")

        assert "-r41@" in result.service_account_email

    @pytest.mark.asyncio
    async def test_different_domains_get_different_sa(
        self,
        fake_db: FakeDatabase,
        fake_settings: FakeSettings,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """Users with same local part but different domains get different SAs."""
        FakeCreds = create_fake_impersonated_credentials_class()
        generator = TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

        result1 = await generator.generate_token("sripathi@recruit41.com")
        result2 = await generator.generate_token("sripathi@think41.com")

        assert result1.service_account_email != result2.service_account_email
        assert "-r41@" in result1.service_account_email
        assert "-t41@" in result2.service_account_email

    @pytest.mark.asyncio
    async def test_unknown_domain_uses_hash(
        self,
        fake_db: FakeDatabase,
        fake_settings: FakeSettings,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """Unknown domain should use hash fallback."""
        FakeCreds = create_fake_impersonated_credentials_class()
        generator = TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

        result = await generator.generate_token("user@unknowndomain.org")

        # Should have a hash suffix (4 characters)
        sa_name = result.service_account_email.split("@")[0]
        # The last segment should be the 4-char hash
        assert len(sa_name.split("-")[-1]) == 4  # 4-char hash

    # Error handling tests

    @pytest.mark.asyncio
    async def test_sa_creation_failure_raises_error(
        self,
        fake_db: FakeDatabase,
        fake_settings: FakeSettings,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """SA creation failure should raise ServiceAccountCreationError."""
        fake_iam.should_fail_create = True

        FakeCreds = create_fake_impersonated_credentials_class()
        generator = TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

        with pytest.raises(ServiceAccountCreationError) as exc_info:
            await generator.generate_token("user@example.com")

        assert exc_info.value.user_email == "user@example.com"
        assert exc_info.value.cause is not None

    @pytest.mark.asyncio
    async def test_impersonation_failure_raises_error(
        self,
        fake_db: FakeDatabase,
        fake_settings: FakeSettings,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """Impersonation failure should raise ImpersonationError."""
        # Pre-create SA so we skip creation and go straight to impersonation
        sa_email = "user-ex@test-project.iam.gserviceaccount.com"
        fake_db.users["user@example.com"] = sa_email

        # Configure fake to fail on impersonation
        FakeCreds = create_fake_impersonated_credentials_class(
            should_fail=True,
            fail_with=RefreshError("Simulated refresh error"),
        )
        generator = TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

        with pytest.raises(ImpersonationError) as exc_info:
            await generator.generate_token("user@example.com")

        assert exc_info.value.sa_email == sa_email

    @pytest.mark.asyncio
    async def test_sa_get_failure_raises_error(
        self,
        fake_db: FakeDatabase,
        fake_settings: FakeSettings,
        fake_iam: FakeIAMAsyncClient,
    ) -> None:
        """Non-NotFound error when checking SA existence should raise ServiceAccountCreationError."""
        fake_iam.should_fail_get = True
        fake_iam.get_failure_exception = Exception("Permission denied")

        FakeCreds = create_fake_impersonated_credentials_class()
        generator = TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

        with pytest.raises(ServiceAccountCreationError):
            await generator.generate_token("user@example.com")

    # Edge cases

    @pytest.mark.asyncio
    async def test_user_without_name(self, generator: TokenGenerator) -> None:
        """User without name should use email in SA description."""
        result = await generator.generate_token("noname@example.com")

        assert result.token is not None
        assert result.service_account_email is not None

    @pytest.mark.asyncio
    async def test_database_stores_sa_mapping(
        self, generator: TokenGenerator, fake_db: FakeDatabase
    ) -> None:
        """SA email should be stored in database for new users."""
        await generator.generate_token("newuser@example.com")

        sa_email = fake_db.users.get("newuser@example.com")
        assert sa_email is not None
        assert sa_email.endswith("@test-project.iam.gserviceaccount.com")


class TestTokenGeneratorWithCustomToken:
    """Tests for TokenGenerator with custom token values."""

    @pytest.mark.asyncio
    async def test_custom_token_returned(self) -> None:
        """Custom token value should be returned."""
        fake_db = FakeDatabase()
        fake_settings = FakeSettings()
        fake_iam = FakeIAMAsyncClient(project_id="test-project")
        custom_token = "my-custom-token-xyz"

        FakeCreds = create_fake_impersonated_credentials_class(token=custom_token)
        generator = TokenGenerator(
            database=fake_db,
            settings=fake_settings,
            iam_client=fake_iam,  # type: ignore[arg-type]
            impersonated_credentials_class=FakeCreds,
        )

        result = await generator.generate_token("user@example.com")

        assert result.token == custom_token


class TestFakeSettings:
    """Tests for FakeSettings domain abbreviation behavior."""

    def test_configured_domain_returns_abbreviation(self) -> None:
        """Configured domain returns its abbreviation."""
        settings = FakeSettings(domain_abbreviations={"recruit41.com": "r41", "think41.com": "t41"})

        assert settings.get_domain_abbreviation("recruit41.com") == "r41"
        assert settings.get_domain_abbreviation("think41.com") == "t41"

    def test_unconfigured_domain_returns_hash(self) -> None:
        """Unconfigured domain returns hash fallback."""
        settings = FakeSettings(domain_abbreviations={})

        result = settings.get_domain_abbreviation("unknown.com")
        assert len(result) == 4  # 4-char hash

    def test_domain_lookup_is_case_insensitive(self) -> None:
        """Domain lookup should be case-insensitive."""
        settings = FakeSettings(domain_abbreviations={"example.com": "ex"})

        assert settings.get_domain_abbreviation("Example.COM") == "ex"
        assert settings.get_domain_abbreviation("EXAMPLE.com") == "ex"
