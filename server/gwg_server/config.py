"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Server
    port: int = 8001
    environment: str = "development"
    debug: bool = False

    # Security
    secret_key: str = "change-me-in-production"

    # CORS (not strictly needed for headless API, but useful for health checks)
    allowed_origins: str = "http://localhost:8001"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8001/api/auth/callback"

    # Google Cloud Project (for creating service accounts and Bigtable)
    google_cloud_project: str = ""

    # Bigtable
    bigtable_instance: str = "gwg-auth"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
