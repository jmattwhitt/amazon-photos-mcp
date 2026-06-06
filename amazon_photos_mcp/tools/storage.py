"""Storage usage and aggregation tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp import _get_client, _tool, _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("get_storage_usage"))
@_tool
def get_storage_usage() -> dict[str, Any]:
    """Get Amazon Photos storage usage (plan, space used, photo/video counts)."""
    ap = _get_client()
    usage = ap.usage()
    if hasattr(usage, "json"):
        return usage.json()  # type: ignore[no-any-return]
    return {"usage": str(usage)}


@mcp.tool(annotations=_tool_annotations("get_aggregations"))
@_tool
def get_aggregations(category: str = "all") -> dict[str, Any]:
    """Get auto-generated aggregations: people, things, locations, dates."""
    ap = _get_client()
    result = ap.aggregations(category, out="")
    if isinstance(result, dict):
        return result
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    if hasattr(result, "to_dict"):
        return result.to_dict()  # type: ignore[no-any-return]
    return {"aggregations": str(result)}
