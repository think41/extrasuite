"""Google Workspace Gateway Server.

Headless API server for CLI authentication and service account token exchange.
Entry point: CLI creates GoogleWorkspaceGateway instance and calls get_token()
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from gwg_server import google_auth, health, token_exchange
from gwg_server.config import get_settings
from gwg_server.database import Database
from gwg_server.rate_limit import limiter, rate_limit_exceeded_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    logger.info(f"Starting GWG server on port {settings.port}")

    # Initialize database and store in app.state for dependency injection
    database = Database(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    app.state.database = database

    yield

    await database.close()
    logger.info("Shutting down GWG server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Google Workspace Gateway",
        description="Headless CLI authentication service for Google Workspace APIs",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Session middleware for signed cookie sessions
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="gwg_session",
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
            "service": "gwg-server",
            "version": "1.0.0",
            "description": "Google Workspace Gateway - Headless CLI authentication service",
            "docs": "/api/docs" if not settings.is_production else None,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "gwg_server.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=not settings.is_production,
    )
