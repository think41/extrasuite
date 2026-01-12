"""Google Workspace Gateway Server.

Headless API server for CLI authentication and service account token exchange.
Entry point: CLI creates GoogleWorkspaceGateway instance and calls get_token()
"""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from gwg_server import auth, health, token_exchange
from gwg_server.config import get_settings
from gwg_server.database import Database
from gwg_server.logging import (
    clear_user_context,
    logger,
    request_id_ctx,
    setup_logging,
)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID and user context to logs."""

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = secrets.token_hex(8)
        request_id_ctx.set(request_id)

        # Log request
        logger.info(
            f"{request.method} {request.url.path}",
            extra={"method": request.method, "path": request.url.path},
        )

        try:
            response = await call_next(request)
            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code}",
                extra={"status_code": response.status_code},
            )
            return response
        except Exception as e:
            logger.exception(f"Request failed: {e}")
            raise
        finally:
            clear_user_context()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    # Setup logging
    setup_logging(
        json_logs=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )

    logger.info(f"Starting GWG server on port {settings.port}")
    logger.info(f"Environment: {settings.environment}")

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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
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
