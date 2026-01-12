"""Fabric - Think41 AI Executive Assistant API.

Headless API server for CLI authentication and service account token exchange.
Entry point: CLI calls get_token() from cli/fabric_auth.py
"""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from fabric import auth, health, token_exchange
from fabric.config import get_settings
from fabric.database import close_db, init_db
from fabric.logging import (
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
async def lifespan(_app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    # Setup logging
    setup_logging(
        json_logs=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )

    logger.info(f"Starting Fabric server on port {settings.port}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize database (sync)
    init_db()
    logger.info("Database initialized")

    yield

    # Close database connections (sync)
    close_db()
    logger.info("Shutting down Fabric server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Fabric",
        description="Headless CLI authentication service for AI Executive Assistant",
        version="0.1.0",
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
            "service": "fabric",
            "version": "0.1.0",
            "description": "Fabric API - Headless CLI authentication service",
            "docs": "/api/docs" if not settings.is_production else None,
        }

    return app


app = create_app()


# For running with uvicorn directly
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "fabric.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=not settings.is_production,
    )
