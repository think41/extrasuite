"""Database configuration and models for OAuth credential storage."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

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


# Database engine (async)
_async_engine = None
_async_session_factory = None


def get_database_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    return getattr(settings, "database_url", "sqlite+aiosqlite:///./fabric.db")


async def get_async_engine():
    """Get or create async database engine."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            get_database_url(),
            echo=get_settings().debug,
        )
    return _async_engine


async def get_session_factory():
    """Get or create async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = await get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    factory = await get_session_factory()
    async with factory() as session:
        yield session


async def init_db():
    """Initialize database tables."""
    engine = await get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    global _async_engine, _async_session_factory
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
