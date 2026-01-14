"""Health check API endpoints."""

from fastapi import APIRouter

from extrasuite_server.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "extrasuite-server"}


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness check for Kubernetes/Cloud Run."""
    settings = get_settings()
    return {
        "status": "ready",
        "service": "extrasuite-server",
        "environment": settings.environment,
    }
