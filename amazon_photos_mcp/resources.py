"""MCP Resources for Amazon Photos."""

import json

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.server import mcp
from amazon_photos_mcp.utils import _safe_df_to_result


@mcp.resource("amazon-photos://albums")
async def list_albums_resource() -> str:
    """List all albums as a JSON resource."""
    ap = _get_client()
    try:
        result = await ap.albums()
        items = _safe_df_to_result(result, 500).get("items", [])
        return json.dumps(items, indent=2)
    except Exception as e:
        return f'{{"error": "{str(e)}"}}\n'


@mcp.resource("amazon-photos://folders")
async def list_folders_resource() -> str:
    """List all folders as a JSON resource."""
    ap = _get_client()
    try:
        df = await ap.get_folders()
        items = _safe_df_to_result(df, 500).get("items", [])
        return json.dumps(items, indent=2)
    except Exception as e:
        return f'{{"error": "{str(e)}"}}\n'
