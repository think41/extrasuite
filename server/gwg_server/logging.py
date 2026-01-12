"""Logging configuration using loguru with GCP Cloud Run support.

Provides:
- Structured JSON logging for production (GCP Cloud Logging compatible)
- Human-readable logging for development
- Request context tracking (request_id, user_email)
- Audit logging for security-relevant events
"""

import json
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from loguru import logger

# Context variables for request-scoped data
user_email_ctx: ContextVar[str | None] = ContextVar("user_email", default=None)
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Map loguru levels to GCP severity levels
LEVEL_TO_SEVERITY = {
    "TRACE": "DEBUG",
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "SUCCESS": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}


def _gcp_json_formatter(record: dict) -> str:
    """Format log record as GCP Cloud Logging compatible JSON.

    GCP Cloud Logging expects:
    - severity: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - message: The log message
    - timestamp: ISO 8601 format
    - Additional fields are indexed automatically
    """
    # Get context
    request_id = request_id_ctx.get()
    user_email = user_email_ctx.get()

    # Build log entry
    log_entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": LEVEL_TO_SEVERITY.get(record["level"].name, "INFO"),
        "message": record["message"],
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add context if available
    if request_id:
        log_entry["request_id"] = request_id
    if user_email:
        log_entry["user_email"] = user_email

    # Add any extra fields from the record
    if record.get("extra"):
        for key, value in record["extra"].items():
            if key not in log_entry:
                log_entry[key] = value

    # Add exception info if present
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
            "traceback": record["exception"].traceback if record["exception"].traceback else None,
        }

    return json.dumps(log_entry, default=str) + "\n"


def _dev_formatter(_record: dict) -> str:
    """Format log record for development (human-readable)."""
    request_id = request_id_ctx.get()
    user_email = user_email_ctx.get()

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
        + context_str
        + "<level>{message}</level>\n"
        "{exception}"
    )


def setup_logging(json_logs: bool = False, log_level: str = "INFO") -> None:
    """Configure loguru for the application.

    Args:
        json_logs: If True, output GCP-compatible JSON logs
        log_level: Minimum log level to output
    """
    # Remove default handler
    logger.remove()

    if json_logs:
        # GCP-compatible JSON format for production
        logger.add(
            sys.stdout,
            format=_gcp_json_formatter,
            level=log_level,
            serialize=False,  # We handle serialization in the formatter
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stdout,
            format=_dev_formatter,
            level=log_level,
            colorize=True,
        )


def set_request_context(request_id: str | None = None, email: str | None = None) -> None:
    """Set context for the current request."""
    if request_id:
        request_id_ctx.set(request_id)
    if email:
        user_email_ctx.set(email)


def clear_request_context() -> None:
    """Clear request context after request completes."""
    user_email_ctx.set(None)
    request_id_ctx.set(None)


# =============================================================================
# Audit Logging
# =============================================================================


def audit_auth_started(email: str | None, port: int) -> None:
    """Log when OAuth flow is initiated."""
    logger.info(
        "OAuth flow started",
        extra={
            "audit_event": "auth_started",
            "email": email,
            "cli_port": port,
        },
    )


def audit_auth_success(email: str, service_account: str) -> None:
    """Log successful authentication."""
    logger.info(
        "Authentication successful",
        extra={
            "audit_event": "auth_success",
            "email": email,
            "service_account": service_account,
        },
    )


def audit_auth_failed(email: str | None, reason: str) -> None:
    """Log failed authentication."""
    logger.warning(
        "Authentication failed",
        extra={
            "audit_event": "auth_failed",
            "email": email,
            "reason": reason,
        },
    )


def audit_token_refresh(email: str, service_account: str) -> None:
    """Log successful token refresh."""
    logger.info(
        "Token refreshed via session",
        extra={
            "audit_event": "token_refresh",
            "email": email,
            "service_account": service_account,
        },
    )


def audit_token_refresh_failed(email: str, reason: str) -> None:
    """Log failed token refresh."""
    logger.warning(
        "Token refresh failed",
        extra={
            "audit_event": "token_refresh_failed",
            "email": email,
            "reason": reason,
        },
    )


def audit_service_account_created(email: str, service_account: str) -> None:
    """Log service account creation."""
    logger.info(
        "Service account created",
        extra={
            "audit_event": "sa_created",
            "email": email,
            "service_account": service_account,
        },
    )


def audit_oauth_state_invalid(state: str, reason: str) -> None:
    """Log invalid OAuth state token."""
    logger.warning(
        "Invalid OAuth state token",
        extra={
            "audit_event": "oauth_state_invalid",
            "state_prefix": state[:8] if state else None,
            "reason": reason,
        },
    )


# Re-export logger for convenience
__all__ = [
    "logger",
    "setup_logging",
    "set_request_context",
    "clear_request_context",
    "request_id_ctx",
    "user_email_ctx",
    # Audit functions
    "audit_auth_started",
    "audit_auth_success",
    "audit_auth_failed",
    "audit_token_refresh",
    "audit_token_refresh_failed",
    "audit_service_account_created",
    "audit_oauth_state_invalid",
]
