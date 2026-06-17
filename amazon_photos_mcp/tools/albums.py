"""Album management tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp
from amazon_photos_mcp.utils import _safe_df_to_result


@mcp.tool(annotations=_tool_annotations("list_albums"))
@_tool
def list_albums(max_results: int = 100) -> dict[str, Any]:
    """List all albums in your Amazon Photos library."""
    ap = _get_client()
    result = ap.albums()
    return _safe_df_to_result(result, max_results)


@mcp.tool(annotations=_tool_annotations("create_album"))
@_tool
def create_album(name: str) -> dict[str, Any]:
    """Create a new album in Amazon Photos."""
    ap = _get_client()
    result = ap.create_album(name)
    return result if isinstance(result, dict) else {"status": "created", "name": name, "result": str(result)}


@mcp.tool(annotations=_tool_annotations("add_to_album"))
@_tool
def add_to_album(album_id: str, node_ids: list[str]) -> dict[str, Any]:
    """Add photos/videos to an existing album."""
    ap = _get_client()
    result = ap.add_to_album(album_id, node_ids)
    return result if isinstance(result, dict) else {"status": "added", "album_id": album_id, "count": len(node_ids)}


@mcp.tool(annotations=_tool_annotations("remove_from_album"))
@_tool
def remove_from_album(album_id: str, node_ids: list[str]) -> dict[str, Any]:
    """Remove photos/videos from an album (does not delete files)."""
    ap = _get_client()
    result = ap.remove_from_album(album_id, node_ids)
    return result if isinstance(result, dict) else {"status": "removed", "album_id": album_id, "count": len(node_ids)}
