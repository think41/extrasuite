"""Shared pytest fixtures for server tests.

Provides a minimal FastAPI test app wired to FakeDatabase and FakeSettings,
and an async httpx client that hits it directly (no real network calls).
"""

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

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
from extrasuite.server.api import get_credential_router
from extrasuite.server.command_registry import (
    _DWD_COMMAND_SCOPES,
    _SA_COMMAND_TYPES,
    Credential,
)
from extrasuite.server.config import get_settings
from extrasuite.server.credential_router import CommandCredentialRouter
from extrasuite.server.database import get_database
from extrasuite.server.token_generator import GeneratedToken

_SA_EMAIL = "user-abc@test-project.iam.gserviceaccount.com"
_FAKE_TOKEN = "fake-access-token-xyz"


def _fake_generated_token(sa_email: str = _SA_EMAIL, token: str = _FAKE_TOKEN) -> GeneratedToken:
    return GeneratedToken(
        token=token,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        service_account_email=sa_email,
    )


def make_mock_credential_router(
    sa_email: str = _SA_EMAIL,
    token: str = _FAKE_TOKEN,
    *,
    session_establishment_error: Exception | None = None,
) -> MagicMock:
    """Build a MagicMock CommandCredentialRouter with sensible default behavior.

    The mock router:
    - on_session_establishment: succeeds (or raises session_establishment_error if set)
    - on_google_auth_callback: no-op
    - on_logout: no-op
    - resolve: returns bearer_sa for SA commands, bearer_dwd for DWD commands

    Returns the mock so tests can configure additional behavior.
    """
    mock_router = MagicMock(spec=CommandCredentialRouter)
    mock_router.on_google_auth_callback = AsyncMock()
    mock_router.on_logout = AsyncMock()

    if session_establishment_error:
        mock_router.on_session_establishment = AsyncMock(side_effect=session_establishment_error)
    else:
        mock_router.on_session_establishment = AsyncMock()

    async def _resolve(command, _email: str) -> list[Credential]:
        cmd_type = command.type
        if cmd_type in _SA_COMMAND_TYPES:
            return [
                Credential(
                    provider="google",
                    kind="bearer_sa",
                    token=token,
                    expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    scopes=[],
                    metadata={"service_account_email": sa_email},
                )
            ]
        if cmd_type in _DWD_COMMAND_SCOPES:
            scopes = _DWD_COMMAND_SCOPES[cmd_type]
            return [
                Credential(
                    provider="google",
                    kind="bearer_dwd",
                    token=token,
                    expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    scopes=scopes,
                    metadata={},
                )
            ]
        from fastapi import HTTPException

        raise HTTPException(400, f"Unknown command type: {cmd_type!r}")

    mock_router.resolve = AsyncMock(side_effect=_resolve)
    return mock_router


def make_test_app(
    db: FakeDatabase,
    settings: FakeSettings,
    credential_router: MagicMock | CommandCredentialRouter | None = None,
) -> FastAPI:
    """Build a minimal FastAPI app with dependency overrides.

    Uses the real api.router (all real endpoint logic) but injects FakeDatabase,
    FakeSettings, and a mock CommandCredentialRouter so no Firestore or Google
    API calls are made.
    """
    from extrasuite.server.main import (
        rate_limit_exceeded_handler,
        unhandled_exception_handler,
    )

    if credential_router is None:
        credential_router = make_mock_credential_router()

    app = FastAPI()
    app.state.limiter = api.limiter
    app.state.credential_router = credential_router
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key-for-testing-only")
    app.include_router(api.router, prefix="/api")

    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_credential_router] = lambda: credential_router

    return app


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Reset the module-level rate limiter storage between tests.

    api.limiter is a module-level singleton whose in-memory state persists
    across tests. Without this reset, tests that call rate-limited endpoints
    can exhaust the limit and cause later tests to receive unexpected 429s.
    """
    api.limiter.reset()


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def fake_settings() -> FakeSettings:
    return FakeSettings(admin_emails=["admin@example.com"])


@pytest.fixture
def fake_router() -> MagicMock:
    """A mock CommandCredentialRouter with sensible defaults."""
    return make_mock_credential_router()


@pytest.fixture
async def client(
    fake_db: FakeDatabase, fake_settings: FakeSettings, fake_router: MagicMock
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async httpx client wired to the test app via ASGITransport (no real HTTP)."""
    app = make_test_app(fake_db, fake_settings, fake_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
