"""Structured JSON logging configuration for Google Cloud Logging.

Configures loguru to output JSON-formatted logs compatible with Google Cloud Run
and Cloud Logging. In development, uses human-readable colored output.
"""

import json
import logging
import sys
import traceback
from typing import Any

from loguru import logger


def _cloud_logging_serializer(record: dict[str, Any]) -> str:
    """Serialize log record to Google Cloud Logging JSON format.

    Cloud Logging expects specific field names:
    - severity: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - message: The log message
    - time: ISO format timestamp

    Additional fields from `extra` are included at the top level.
    """
    # Map loguru levels to Cloud Logging severity
    level = record["level"].name
    severity_map = {
        "TRACE": "DEBUG",
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "SUCCESS": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    # Build the log entry
    log_entry: dict[str, Any] = {
        "severity": severity_map.get(level, "INFO"),
        "message": record["message"],
        "time": record["time"].isoformat(),
    }

    # Add location info for errors
    if record["level"].no >= 40:  # ERROR and above
        log_entry["logging.googleapis.com/sourceLocation"] = {
            "file": record["file"].path,
            "line": str(record["line"]),
            "function": record["function"],
        }

    # Add exception info if present
    if record["exception"] is not None:
        exc_info = record["exception"]
        tb_str = None
        if exc_info.traceback:
            tb_str = "".join(
                traceback.format_exception(exc_info.type, exc_info.value, exc_info.traceback)
            )
        log_entry["exception"] = {
            "type": exc_info.type.__name__ if exc_info.type else None,
            "value": str(exc_info.value) if exc_info.value else None,
            "traceback": tb_str,
        }

    # Include extra fields at the top level
    extra = record.get("extra", {})
    for key, value in extra.items():
        # Skip internal loguru keys
        if not key.startswith("_"):
            log_entry[key] = value

    return json.dumps(log_entry, default=str)


def _json_sink(message: Any) -> None:
    """Sink that writes serialized JSON to stdout."""
    record = message.record
    serialized = _cloud_logging_serializer(record)
    sys.stdout.write(serialized + "\n")
    sys.stdout.flush()


def configure_logging(*, is_production: bool, log_level: str = "INFO") -> None:
    """Configure loguru for the application.

    Args:
        is_production: If True, output JSON for Cloud Logging. If False, use
            human-readable colored output for development.
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    # Remove default handler
    logger.remove()

    if is_production:
        # JSON output for Cloud Logging
        logger.add(
            _json_sink,
            level=log_level,
            format="{message}",  # Format is handled by the sink
            backtrace=False,  # Don't include backtrace in format (handled in serializer)
            diagnose=False,  # Don't include variable values in production
        )
    else:
        # Human-readable colored output for development
        logger.add(
            sys.stderr,
            level=log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
                "{exception}"
            ),
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # Intercept standard library logging (for uvicorn, etc.)
    _intercept_standard_logging(log_level)


def _intercept_standard_logging(log_level: str) -> None:
    """Intercept standard library logging and route to loguru.

    This captures logs from uvicorn, httpx, and other libraries.
    """

    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding loguru level
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where the logged message originated
            frame, depth = logging.currentframe(), 2
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    # Configure root logger to use our handler
    logging.basicConfig(handlers=[InterceptHandler()], level=log_level, force=True)

    # Set specific library log levels
    for name in ["uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"]:
        logging.getLogger(name).setLevel(log_level)
        logging.getLogger(name).handlers = [InterceptHandler()]
