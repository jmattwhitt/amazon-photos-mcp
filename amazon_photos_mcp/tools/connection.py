"""Connection health, cookie validation, and client refresh tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp import (
    _COOKIE_EXPIRED_AFTER_HOURS,
    _COOKIE_WARN_AFTER_HOURS,
    _cookie_advice,
    _cookie_age_hours,
    _get_client,
    _tool,
    _tool_annotations,
    mcp,
)


@mcp.tool(annotations=_tool_annotations("check_connection"))
@_tool
def check_connection() -> dict[str, Any]:
    """Test connection to Amazon Photos and report storage usage and cookie health."""
    advice = _cookie_advice()
    age_hours = _cookie_age_hours()
    age_days = age_hours / 24 if age_hours is not None else None
    warnings: list[str] = []

    if age_hours is None or age_hours >= _COOKIE_EXPIRED_AFTER_HOURS:
        warnings.append(advice)
    elif age_hours >= _COOKIE_WARN_AFTER_HOURS:
        warnings.append(advice)

    ap = _get_client()
    usage = ap.usage()
    data: dict[str, Any] = usage.json() if hasattr(usage, "json") else {"usage": str(usage)}
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
    age_hours = _cookie_age_hours()
    if age_hours is None or age_hours >= _COOKIE_EXPIRED_AFTER_HOURS:
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": _cookie_advice(),
        }
    try:
        ap = _get_client()
        result = ap.usage()
        ok = not (hasattr(result, "status_code") and result.status_code in (401, 403))
        return {
            "valid": ok,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": _cookie_advice(),
        }
    except Exception as e:
        s = str(e).lower()
        auth_fail = any(x in s for x in ("401", "403", "unauthorized", "forbidden", "expired"))
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": _cookie_advice(),
            "error": str(e) if not auth_fail else "Auth rejected by Amazon — cookies expired.",
        }
