"""ExtraSuite Server.

Headless API server for CLI authentication and service account token exchange.
Entry point: CLI creates ExtraSuiteClient instance and calls get_token()
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from extrasuite_server import google_auth, health, token_exchange
from extrasuite_server.config import get_settings
from extrasuite_server.database import Database
from extrasuite_server.logging import configure_logging
from extrasuite_server.rate_limit import limiter, rate_limit_exceeded_handler


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    logger.info(f"Starting ExtraSuite server on port {settings.port}")

    # Initialize database and store in app.state for dependency injection
    database = Database(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    app.state.database = database

    yield

    await database.close()
    logger.info("Shutting down ExtraSuite server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Configure structured JSON logging for Cloud Logging
    configure_logging(
        is_production=settings.is_production,
        log_level=settings.log_level,
    )

    app = FastAPI(
        title="ExtraSuite",
        description="Headless CLI authentication service for Google Workspace APIs",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    # Exception handlers
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Rate limiting
    app.state.limiter = limiter

    # Session middleware for signed cookie sessions
    # Note: type: ignore needed because Starlette's _MiddlewareFactory Protocol
    # doesn't properly type class-based middleware (only function factories)
    app.add_middleware(
        SessionMiddleware,  # type: ignore[arg-type]
        secret_key=settings.secret_key,
        session_cookie="extrasuite_session",
        max_age=30 * 24 * 60 * 60,  # 30 days in seconds
        same_site="lax",
        https_only=settings.is_production,
    )

    # Register API routers
    app.include_router(health.router, prefix="/api")
    app.include_router(google_auth.router, prefix="/api")
    app.include_router(token_exchange.router, prefix="/api")

    @app.get("/")
    async def root():
        return {
            "service": "extrasuite-server",
            "version": "1.0.0",
            "description": "ExtraSuite - Headless CLI authentication service",
            "docs": "/api/docs" if not settings.is_production else None,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "extrasuite_server.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=not settings.is_production,
    )
