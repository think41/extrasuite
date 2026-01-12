"""Logging configuration using loguru with user context support."""

import sys
from contextvars import ContextVar
from typing import Any

from loguru import logger

# Context variables for request-scoped data
user_email_ctx: ContextVar[str | None] = ContextVar("user_email", default=None)
user_name_ctx: ContextVar[str | None] = ContextVar("user_name", default=None)
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_user_context() -> dict[str, Any]:
    """Get current user context for logging."""
    return {
        "user_email": user_email_ctx.get(),
        "user_name": user_name_ctx.get(),
        "request_id": request_id_ctx.get(),
    }


def format_record(_record: dict) -> str:
    """Format log record with user context."""
    user_email = user_email_ctx.get()
    request_id = request_id_ctx.get()

    # Build context string
    context_parts = []
    if request_id:
        context_parts.append(f"req={request_id[:8]}")
    if user_email:
        context_parts.append(f"user={user_email}")

    context_str = " ".join(context_parts)
    if context_str:
        context_str = f"[{context_str}] "

    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        f"{context_str}"
        "<level>{message}</level>\n"
        "{exception}"
    )


def setup_logging(json_logs: bool = False, log_level: str = "INFO") -> None:
    """Configure loguru for the application.

    Args:
        json_logs: If True, output logs as JSON (useful for production)
        log_level: Minimum log level to output
    """
    # Remove default handler
    logger.remove()

    if json_logs:
        # JSON format for production (structured logging)
        logger.add(
            sys.stdout,
            format="{message}",
            level=log_level,
            serialize=True,
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stdout,
            format=format_record,
            level=log_level,
            colorize=True,
        )


def set_user_context(email: str | None = None, name: str | None = None) -> None:
    """Set user context for the current request."""
    if email:
        user_email_ctx.set(email)
    if name:
        user_name_ctx.set(name)


def clear_user_context() -> None:
    """Clear user context after request completes."""
    user_email_ctx.set(None)
    user_name_ctx.set(None)
    request_id_ctx.set(None)


# Re-export logger for convenience
__all__ = [
    "logger",
    "setup_logging",
    "set_user_context",
    "clear_user_context",
    "request_id_ctx",
    "user_email_ctx",
    "user_name_ctx",
]
