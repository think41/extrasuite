"""Google Workspace Gateway Server.

Headless API server for CLI authentication and service account token exchange.
Entry point: CLI creates GoogleWorkspaceGateway instance and calls get_token()
"""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from gwg_server import google_auth, health, token_exchange
from gwg_server.config import get_settings
from gwg_server.database import Database
from gwg_server.logging import (
    clear_request_context,
    logger,
    set_request_context,
    setup_logging,
)
from gwg_server.session import get_session_middleware_config


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID and logging context."""

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = secrets.token_hex(8)
        set_request_context(request_id=request_id)

        # Log request
        logger.info(
            "Request started",
            extra={"method": request.method, "path": request.url.path},
        )

        try:
            response = await call_next(request)
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            )
            return response
        except Exception:
            logger.exception("Request failed")
            raise
        finally:
            clear_request_context()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    # Setup logging
    setup_logging(
        json_logs=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )

    logger.info(
        "Starting GWG server",
        extra={"port": settings.port, "environment": settings.environment},
    )

    # Initialize database and store in app.state for dependency injection
    database = Database(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    database.verify_connection()
    app.state.database = database
    logger.info("Database initialized")

    yield

    # Close database connection
    database.close()
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

    # Logging middleware (must be added first to wrap everything)
    app.add_middleware(LoggingMiddleware)

    # Session middleware for signed cookie sessions
    session_config = get_session_middleware_config(settings.secret_key, settings.is_production)
    app.add_middleware(SessionMiddleware, **session_config)

    # Register API routers
    app.include_router(health.router, prefix="/api")
    app.include_router(google_auth.router, prefix="/api")
    app.include_router(token_exchange.router, prefix="/api")

    # Root endpoint
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


# For running with uvicorn directly
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "gwg_server.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=not settings.is_production,
    )
