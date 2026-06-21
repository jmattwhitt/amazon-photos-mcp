"""Storage usage and aggregation tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("get_storage_usage"))
@_tool
async def get_storage_usage() -> dict[str, Any]:
    """Get Amazon Photos storage usage (plan, space used, photo/video counts)."""
    ap = _get_client()
    usage = await ap.usage()
    return usage if isinstance(usage, dict) else {"usage": str(usage)}


@mcp.tool(annotations=_tool_annotations("get_aggregations"))
@_tool
async def get_aggregations(category: str = "all") -> dict[str, Any]:
    """Get auto-generated aggregations: people, things, locations, dates."""
    ap = _get_client()
    result = await ap.aggregations(category)
    return {"items": result, "count": len(result)}
