"""Fabric - Think41 AI Executive Assistant Portal.

Main FastAPI application entry point.
"""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from fabric import auth, health, service_account, token_exchange
from fabric.config import get_settings
from fabric.database import close_db, init_db
from fabric.logging import (
    clear_user_context,
    logger,
    request_id_ctx,
    set_user_context,
    setup_logging,
)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID and user context to logs."""

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = secrets.token_hex(8)
        request_id_ctx.set(request_id)

        # Try to extract user from session cookie (if present)
        session_cookie = request.cookies.get("fabric_session")
        if session_cookie:
            try:
                from fabric.auth.api import get_serializer
                from fabric.config import get_settings

                settings = get_settings()
                serializer = get_serializer(settings)
                data = serializer.loads(session_cookie, max_age=86400)
                set_user_context(email=data.get("email"), name=data.get("name"))
            except Exception:
                pass  # Invalid/expired session, continue without user context

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
        description="Think41 AI Executive Assistant Portal",
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
    app.include_router(service_account.router, prefix="/api")
    app.include_router(token_exchange.router, prefix="/api")

    # Serve static files in production
    static_dir = Path(__file__).parent.parent.parent / "static"
    if static_dir.exists() and settings.is_production:
        # Mount static assets
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        # Serve index.html for all non-API routes (SPA routing)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Don't serve index.html for API routes
            if full_path.startswith("api/"):
                return {"error": "Not found"}

            # Try to serve the exact file if it exists
            file_path = static_dir / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)

            # Otherwise serve index.html for SPA routing
            return FileResponse(static_dir / "index.html")

    else:
        # Development mode - just return API info at root
        @app.get("/")
        async def root():
            return {"service": "fabric", "status": "running"}

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
