"""Folder listing and tree display tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp
from amazon_photos_mcp.utils import _safe_df_to_result


@mcp.tool(annotations=_tool_annotations("list_folders"))
@_tool
def list_folders() -> dict[str, Any]:
    """List all folders in your Amazon Photos library."""
    ap = _get_client()
    df = ap.get_folders()
    return _safe_df_to_result(df, max_results=500)


@mcp.tool(annotations=_tool_annotations("get_folder_tree"))
@_tool
def get_folder_tree() -> dict[str, Any]:
    """Display the folder tree of your Amazon Photos library."""
    return {"tree": "Folder tree printing is deprecated in the native API client. Use list_folders instead."}
