"""Fabric - Think41 AI Executive Assistant Portal.

Main FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fabric import auth, health, service_account
from fabric.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    print(f"Starting Fabric server on port {settings.port}")
    print(f"Environment: {settings.environment}")
    yield
    print("Shutting down Fabric server")


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
