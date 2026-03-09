"""ExtraSuite Server.

Headless API server for CLI session establishment and credential exchange.
"""

import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from extrasuite.server import api, skills
from extrasuite.server.config import get_settings
from extrasuite.server.credential_router import CommandCredentialRouter
from extrasuite.server.crypto import RefreshTokenEncryptor
from extrasuite.server.database import Database
from extrasuite.server.firestore_setup import ensure_firestore_setup
from extrasuite.server.logging import configure_logging
from extrasuite.server.token_generator import TokenGenerator


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global handler for unhandled exceptions."""
    logger.exception(
        "Unhandled exception",
        extra={"path": request.url.path, "error": str(exc)},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def rate_limit_exceeded_handler(request: Request, _exc: Exception) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    logger.warning(
        "Rate limit exceeded",
        extra={"path": request.url.path, "client": get_remote_address(request)},
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    logger.info("Starting ExtraSuite server")

    # Set the default thread pool executor used by asyncio.to_thread().
    # Controls max concurrency for blocking I/O: DWD JWT signing, SA impersonation,
    # OAuth token exchange, and token revocation.
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.thread_pool_size,
        thread_name_prefix="extrasuite-blocking-io",
    )
    asyncio.get_event_loop().set_default_executor(executor)

    # Initialize database and store in app.state for dependency injection
    database = Database(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    app.state.database = database

    # Build the credential router (once at startup; no mode checks at runtime)
    encryptor = None
    if settings.uses_oauth:
        encryptor = RefreshTokenEncryptor(settings.oauth_token_encryption_key)

    token_generator = TokenGenerator(
        database=database,
        settings=settings,
        encryptor=encryptor,
    )
    app.state.token_generator = token_generator
    credential_router = CommandCredentialRouter.from_settings(
        settings, token_generator, database, encryptor
    )
    app.state.credential_router = credential_router

    # Ensure Firestore TTL policies and composite indexes exist (fire-and-forget).
    # Task reference kept to prevent premature GC (RUF006).
    _setup_task = ensure_firestore_setup(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )

    yield

    _setup_task.cancel()

    await token_generator.close()
    await database.close()
    executor.shutdown(wait=False)
    logger.info("Shutting down ExtraSuite server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Configure structured JSON logging for Cloud Logging
    configure_logging(log_level=settings.log_level)

    app = FastAPI(
        title="ExtraSuite",
        description="Headless CLI authentication service for Google Workspace APIs",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Exception handlers
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Rate limiting - use the limiter from api module
    app.state.limiter = api.limiter

    # Session middleware for signed cookie sessions
    # Note: type: ignore needed because Starlette's _MiddlewareFactory Protocol
    # doesn't properly type class-based middleware (only function factories)
    app.add_middleware(
        SessionMiddleware,  # type: ignore[arg-type]
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        max_age=settings.session_cookie_expiry_minutes * 60,  # Convert minutes to seconds
        same_site=settings.session_cookie_same_site,
        https_only=settings.session_cookie_https_only,
        domain=settings.effective_session_cookie_domain,
    )

    # Register API router (all endpoints consolidated)
    app.include_router(api.router, prefix="/api")

    # Register skills download router
    app.include_router(skills.router, prefix="/api/skills")

    # Static pages directory
    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    async def home():
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/privacy")
    async def privacy():
        return FileResponse(static_dir / "privacy.html", media_type="text/html")

    @app.get("/terms")
    async def terms():
        return FileResponse(static_dir / "terms.html", media_type="text/html")

    @app.get("/security")
    async def security():
        return FileResponse(static_dir / "security.html", media_type="text/html")

    @app.get("/faq")
    async def faq():
        return FileResponse(static_dir / "faq.html", media_type="text/html")

    @app.get("/robots.txt")
    async def robots():
        return FileResponse(static_dir / "robots.txt", media_type="text/plain")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "extrasuite_server.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
