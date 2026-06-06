"""Folder listing and tree display tools."""

from __future__ import annotations

import contextlib
import io
from typing import Any

from amazon_photos_mcp import _get_client, _safe_df_to_result, _stdout_lock, _tool, _tool_annotations, mcp


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
    ap = _get_client()
    buf = io.StringIO()
    with _stdout_lock, contextlib.redirect_stdout(buf):
        ap.print_tree()
    return {"tree": buf.getvalue() or "No folder tree available."}
