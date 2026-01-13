"""Rate limiting configuration.

This module provides rate limiting for API endpoints using slowapi.
Uses per-instance memory storage (suitable for single-instance deployments).

Note: This is a separate module to avoid circular imports. The `limiter` instance
is imported by both main.py and route modules (google_auth.py, token_exchange.py).
Moving it to main.py would cause circular dependencies since main.py imports those routes.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter with per-instance memory storage
limiter = Limiter(key_func=get_remote_address)


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
