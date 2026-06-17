"""Connection health, cookie validation, and client refresh tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp import client as mod_client
from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.errors import AuthenticationError
from amazon_photos_mcp.server import _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("check_connection"))
@_tool
def check_connection() -> dict[str, Any]:
    """Test connection to Amazon Photos and report storage usage and cookie health."""
    advice = mod_client.cookie_advice()
    age_hours = mod_client._cookie_age_hours()
    age_days = age_hours / 24 if age_hours is not None else None
    warnings: list[str] = []

    if age_hours is None or age_hours >= mod_client._COOKIE_EXPIRED_AFTER_HOURS:
        warnings.append(advice)
    elif age_hours >= mod_client._COOKIE_WARN_AFTER_HOURS:
        warnings.append(advice)

    ap = _get_client()
    usage = ap.usage()
    data: dict[str, Any] = usage if isinstance(usage, dict) else {"usage": str(usage)}
    data["status"] = "connected"
    data["cookie_health"] = advice
    if age_days is not None:
        data["cookie_age_days"] = round(age_days, 1)
    if warnings:
        data["warnings"] = warnings
    return data


@mcp.tool(annotations=_tool_annotations("refresh_client"))
@_tool
def refresh_client() -> dict[str, Any]:
    """Force a fresh client connection. Use after updating cookies.json."""
    _get_client(force_refresh=True)
    return check_connection()


@mcp.tool(annotations=_tool_annotations("validate_cookies"))
@_tool
def validate_cookies() -> dict[str, Any]:
    """Check whether stored cookies are still accepted by Amazon."""
    age_hours = mod_client._cookie_age_hours()
    if age_hours is None or age_hours >= mod_client._COOKIE_EXPIRED_AFTER_HOURS:
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": mod_client.cookie_advice(),
        }
    try:
        ap = _get_client()
        ap.usage()  # 401 raises AuthenticationError in _request_with_retry
        return {
            "valid": True,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": mod_client.cookie_advice(),
        }
    except AuthenticationError:
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": mod_client.cookie_advice(),
            "error": "Auth rejected by Amazon -- cookies expired.",
        }
    except Exception as e:
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": mod_client.cookie_advice(),
            "error": str(e),
        }
