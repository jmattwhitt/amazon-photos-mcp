"""Structured logging for amazon-photos-mcp.

Configured via environment variables:
  AMAZON_PHOTOS_LOG_LEVEL  — DEBUG, INFO, WARNING, ERROR (default: INFO)
  AMAZON_PHOTOS_LOG_FILE   — file path for log output (default: stderr only)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    """Return the module-level logger, configuring it on first call."""
    global _logger
    if _logger is not None:
        return _logger

    level_name = os.environ.get("AMAZON_PHOTOS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    _logger = logging.getLogger("amazon-photos-mcp")
    _logger.setLevel(level)

    if not _logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler: logging.Handler
        log_file = os.environ.get("AMAZON_PHOTOS_LOG_FILE", "")
        if log_file:
            from pathlib import Path

            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(fmt)
        _logger.addHandler(handler)

    _logger.debug("Logger initialized (level=%s)", level_name)
    return _logger


def log_request(method: str, url: str, status: int, elapsed_ms: float) -> None:
    """Log an HTTP request/response cycle for performance debugging."""
    log = get_logger()
    log.debug("HTTP %s %s -> %d in %.0fms", method, url, status, elapsed_ms)


def log_tool_call(tool_name: str, duration_ms: float, succeeded: bool = True) -> None:
    """Log a tool invocation with timing."""
    log = get_logger()
    status = "OK" if succeeded else "FAIL"
    log.info("Tool %s %s (%.0fms)", tool_name, status, duration_ms)


def timed_tool(fn: Any) -> Any:
    """Decorator to log tool execution time. Apply as innermost decorator.

    IMPORTANT: MUST be the innermost decorator — apply AFTER @mcp.tool()
    and @_tool. Correct order: @mcp.tool() -> @_tool -> @timed_tool.
    Applying @timed_tool before @_tool will log FAIL for all exceptions,
    even though @_tool converts them to structured error dicts.

    Note: When stacked correctly with @_tool (which catches all exceptions),
    this decorator detects failures by checking result.get("error") on
    the returned dict rather than relying on the except branch.
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        result: Any = None
        succeeded = False
        try:
            result = fn(*args, **kwargs)
            succeeded = not (isinstance(result, dict) and result.get("error"))
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            log_tool_call(fn.__name__, elapsed_ms, succeeded=succeeded)
        return result

    return wrapper


# Replace print(..., file=sys.stderr) calls in tool modules.
# The main module still uses print() for startup messages which is intentional.
def log_warning(msg: str, *args: Any) -> None:
    get_logger().warning(msg, *args)


def log_error(msg: str, *args: Any) -> None:
    get_logger().error(msg, *args)


def log_info(msg: str, *args: Any) -> None:
    get_logger().info(msg, *args)
