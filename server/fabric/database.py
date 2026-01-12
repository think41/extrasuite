"""Database configuration and models for OAuth credential storage.

Uses synchronous SQLAlchemy with SQLite for simplicity.
Database operations are infrequent (OAuth storage/retrieval only).
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from fabric.config import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class UserOAuthCredential(Base):
    """Store OAuth credentials for users (server-side only)."""

    __tablename__ = "user_oauth_credentials"

    # Primary key is the user's email
    email = Column(String(255), primary_key=True)

    # OAuth tokens
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_uri = Column(String(255), default="https://oauth2.googleapis.com/token")

    # Scopes granted
    scopes = Column(Text, nullable=False)  # JSON array of scopes

    # Service account mapping
    service_account_email = Column(String(255), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


# Database engine and session factory
_engine = None
_session_factory = None


def get_database_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    # Use sync SQLite URL (not aiosqlite)
    url = getattr(settings, "database_url", "sqlite:///./fabric.db")
    # Convert async URL to sync if needed
    return url.replace("sqlite+aiosqlite:", "sqlite:")


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            echo=get_settings().debug,
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine)
    return _session_factory


def get_db() -> Session:
    """Get a database session."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def close_db():
    """Close database connections."""
    global _engine, _session_factory
    if _engine:
        _engine.dispose()
        _engine = None
        _session_factory = None
