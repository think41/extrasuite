"""Application configuration using pydantic-settings.

All sensitive configuration must come from environment variables.
The application will fail to start if required configuration is missing.
"""

import hashlib
import json
import secrets
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Required environment variables:
    - SECRET_KEY: For signing session cookies (must be set in production)
    - GOOGLE_CLIENT_ID: OAuth client ID
    - GOOGLE_CLIENT_SECRET: OAuth client secret
    - GOOGLE_CLOUD_PROJECT: GCP project for service accounts and Firestore
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined in Settings
    )

    # Server
    port: int = 8001
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Security - must be set via environment variable
    secret_key: str = ""

    # Google OAuth - must be set via environment variables
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8001/api/auth/callback"

    # Google Cloud Project - must be set via environment variable
    google_cloud_project: str = ""

    # Firestore database name
    firestore_database: str = "(default)"

    # Email domain allowlist (comma-separated, e.g., "example.com,foo.org")
    # If empty, all domains are allowed
    allowed_email_domains: str = ""

    # Domain abbreviations for service account naming (JSON format)
    # Example: {"recruit41.com": "r41", "think41.com": "t41", "mindlap.dev": "mlap"}
    # If domain not in map, falls back to 4-char hash of domain
    domain_abbreviations: str = ""

    # Default skills URL (public GitHub release)
    # Used when no bundled skills.zip is present in the Docker image
    default_skills_url: str = (
        "https://github.com/think41/extrasuite/releases/latest/download/skills.zip"
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    def get_allowed_domains(self) -> list[str]:
        """Get list of allowed email domains.

        Returns empty list if no domain restriction is configured.
        """
        if not self.allowed_email_domains:
            return []
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    def is_email_domain_allowed(self, email: str) -> bool:
        """Check if an email's domain is in the allowlist.

        Returns True if:
        - No domain restriction is configured (allowlist is empty)
        - Email domain matches one of the allowed domains
        """
        allowed = self.get_allowed_domains()
        if not allowed:
            return True  # No restriction

        if "@" not in email:
            return False

        domain = email.split("@")[-1].lower()
        return domain in allowed

    def get_domain_abbreviation(self, domain: str) -> str:
        """Get abbreviation for a domain.

        Looks up the domain in the configured abbreviations map.
        Falls back to a 4-char hash of the domain if not configured.

        Args:
            domain: Email domain (e.g., "example.com")

        Returns:
            Abbreviation string (e.g., "r41" or "a1b2")
        """
        if self.domain_abbreviations:
            try:
                abbrevs = json.loads(self.domain_abbreviations)
                if domain.lower() in abbrevs:
                    return abbrevs[domain.lower()]
            except json.JSONDecodeError:
                pass

        # Fallback: 4-char hash of domain
        return hashlib.sha256(domain.lower().encode()).hexdigest()[:4]

    @model_validator(mode="after")
    def validate_required_settings(self) -> "Settings":
        """Validate that required settings are configured."""
        errors = []

        # In production, secret_key must be explicitly set
        if self.is_production and not self.secret_key:
            errors.append("SECRET_KEY must be set in production")

        # Generate a random secret key for development if not set
        if not self.secret_key:
            # This is only for development - logs a warning
            object.__setattr__(self, "secret_key", secrets.token_urlsafe(32))

        # OAuth credentials are always required
        if not self.google_client_id:
            errors.append("GOOGLE_CLIENT_ID must be set")

        if not self.google_client_secret:
            errors.append("GOOGLE_CLIENT_SECRET must be set")

        if not self.google_cloud_project:
            errors.append("GOOGLE_CLOUD_PROJECT must be set")

        if errors:
            raise ValueError("Configuration errors:\n  - " + "\n  - ".join(errors))

        return self

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is a known value."""
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of: {allowed}")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port is in valid range."""
        if not 1 <= v <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a known value."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of: {allowed}")
        return v_upper


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Settings are loaded once and cached for the lifetime of the application.
    """
    return Settings()
