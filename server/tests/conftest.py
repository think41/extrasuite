"""Shared pytest fixtures for server tests.

Provides a minimal FastAPI test app wired to FakeDatabase and FakeSettings,
and an async httpx client that hits it directly (no real network calls).
"""

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from tests.fakes import FakeDatabase, FakeSettings

# These env vars must be set before any extrasuite.server module is imported,
# because main.py calls create_app() at module level which reads Settings.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

# Deferred imports: these trigger main.py's module-level create_app() call,
# so they must come after the env vars are set above.
from extrasuite.server import api
from extrasuite.server.config import get_settings
from extrasuite.server.database import get_database


def make_test_app(db: FakeDatabase, settings: FakeSettings) -> FastAPI:
    """Build a minimal FastAPI app with dependency overrides.

    Uses the real api.router (all real endpoint logic) but injects FakeDatabase
    and FakeSettings so no Firestore or Google API calls are made.
    """
    from extrasuite.server.main import (
        rate_limit_exceeded_handler,
        unhandled_exception_handler,
    )

    app = FastAPI()
    app.state.limiter = api.limiter
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key-for-testing-only")
    app.include_router(api.router, prefix="/api")

    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings

    return app


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def fake_settings() -> FakeSettings:
    return FakeSettings(admin_emails=["admin@example.com"])


@pytest.fixture
async def client(
    fake_db: FakeDatabase, fake_settings: FakeSettings
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async httpx client wired to the test app via ASGITransport (no real HTTP)."""
    app = make_test_app(fake_db, fake_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
