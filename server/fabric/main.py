"""Fabric - Think41 AI Executive Assistant Portal.

Main FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    # Root endpoint
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
