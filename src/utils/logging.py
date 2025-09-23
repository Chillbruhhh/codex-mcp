"""
Structured logging configuration for the Codex CLI MCP Server.

This module sets up structured JSON logging with correlation IDs to track
MCP requests through their entire lifecycle including container operations.
"""

import logging
import sys
import uuid
from typing import Any, Dict, Optional
from contextvars import ContextVar
from datetime import datetime

import structlog


# Context variable for correlation ID
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            add_timestamp,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # Reduce noise from external libraries
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def add_correlation_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add correlation ID to log entries."""
    cid = correlation_id.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def add_timestamp(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add ISO timestamp to log entries."""
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


def set_correlation_id(cid: Optional[str] = None) -> str:
    """
    Set correlation ID for the current context.

    Args:
        cid: Optional correlation ID, generates one if not provided

    Returns:
        str: The correlation ID that was set
    """
    if not cid:
        cid = str(uuid.uuid4())
    correlation_id.set(cid)
    return cid


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return correlation_id.get()


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name, typically __name__

    Returns:
        structlog.BoundLogger: Configured logger instance
    """
    return structlog.get_logger(name)


# Common logger instances
logger = get_logger(__name__)


class LogContext:
    """Context manager for setting correlation ID."""

    def __init__(self, cid: Optional[str] = None):
        self.cid = cid
        self.old_cid = None

    def __enter__(self) -> str:
        self.old_cid = correlation_id.get()
        return set_correlation_id(self.cid)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        correlation_id.set(self.old_cid)