"""Decorators for Amazon Photos MCP."""

import functools
import os
import traceback
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from amazon_photos_mcp.errors import (
    AuthenticationError,
    RateLimitError,
    ResourceNotFoundError,
)

P = ParamSpec("P")
R = TypeVar("R")


def _tool(fn: Callable[P, R]) -> Callable[P, R | dict[str, Any]]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except AuthenticationError as e:
            # One implicit retry: force refresh client and retry once
            try:
                from amazon_photos_mcp.client import _get_client

                _get_client(force_refresh=True)
                return fn(*args, **kwargs)
            except Exception:
                pass
            return {
                "error": True,
                "code": e.code,
                "message": str(e),
                "suggestion": "Update cookies.json and call refresh_client.",
            }
        except RateLimitError as e:
            return {
                "error": True,
                "code": e.code,
                "message": str(e),
                "retry_after_seconds": e.retry_after,
            }
        except ResourceNotFoundError as e:
            return {
                "error": True,
                "code": e.code,
                "message": str(e),
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
            }
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            debug = os.environ.get("AMAZON_PHOTOS_DEBUG", "").lower() in ("1", "true", "yes")
            error_dict: dict[str, Any] = {
                "error": True,
                "code": "UNEXPECTED_ERROR",
                "message": str(e),
                "tool": fn.__name__,
            }
            if debug:
                error_dict["traceback"] = traceback.format_exc()
            return error_dict

    return wrapper
