"""Favorite and hide/show visibility tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp import _get_client, _tool, _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("set_favorite"))
@_tool
def set_favorite(node_ids: list[str], favorite: bool = True) -> dict[str, Any]:
    """Mark photos/videos as favorites or remove them from favorites.

    Args:
        node_ids: List of Amazon Photos node IDs
        favorite: True to favorite, False to unfavorite
    """
    ap = _get_client()
    if favorite:
        result = ap.favorite(node_ids)
        action = "favorited"
    else:
        result = ap.unfavorite(node_ids)
        action = "unfavorited"
    if hasattr(result, "json"):
        data: dict[str, Any] = result.json()
        data.setdefault("action", action)
        data.setdefault("count", len(node_ids))
        return data
    return {"status": "ok", "action": action, "count": len(node_ids), "node_ids": node_ids}


@mcp.tool(annotations=_tool_annotations("favorite_items"))
@_tool
def favorite_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_favorite(node_ids, favorite=True) instead."""
    return set_favorite(node_ids, favorite=True)


@mcp.tool(annotations=_tool_annotations("unfavorite_items"))
@_tool
def unfavorite_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_favorite(node_ids, favorite=False) instead."""
    return set_favorite(node_ids, favorite=False)


@mcp.tool(annotations=_tool_annotations("set_hidden"))
@_tool
def set_hidden(node_ids: list[str], hidden: bool = True) -> dict[str, Any]:
    """Hide or unhide photos/videos in the main library view.

    Args:
        node_ids: List of Amazon Photos node IDs
        hidden: True to hide, False to unhide (make visible)
    """
    ap = _get_client()
    if hidden:
        result = ap.hide(node_ids)
        action = "hidden"
    else:
        result = ap.unhide(node_ids)
        action = "unhidden"
    if hasattr(result, "json"):
        data: dict[str, Any] = result.json()
        data.setdefault("action", action)
        data.setdefault("count", len(node_ids))
        return data
    return {"status": "ok", "action": action, "count": len(node_ids), "node_ids": node_ids}


@mcp.tool(annotations=_tool_annotations("hide_items"))
@_tool
def hide_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_hidden(node_ids, hidden=True) instead."""
    return set_hidden(node_ids, hidden=True)


@mcp.tool(annotations=_tool_annotations("unhide_items"))
@_tool
def unhide_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_hidden(node_ids, hidden=False) instead."""
    return set_hidden(node_ids, hidden=False)
