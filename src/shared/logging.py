"""Structured logging setup for MCP Platform.

Uses structlog for consistent, machine-parseable log output.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor


def add_log_level(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def setup_logging(log_level: str = "INFO", json_output: bool = False) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON; otherwise, use colored console output
    """
    # Shared processors for both development and production
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]
    
    if json_output:
        # Production: JSON output
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Colored console output
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Also configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.BoundLogger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically module name)
        **initial_context: Initial context values to bind to logger
    
    Returns:
        A bound structlog logger instance
    """
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


def bind_context(**context: Any) -> None:
    """Bind context values to all loggers in the current context."""
    structlog.contextvars.bind_contextvars(**context)


def clear_context() -> None:
    """Clear all bound context values."""
    structlog.contextvars.clear_contextvars()
