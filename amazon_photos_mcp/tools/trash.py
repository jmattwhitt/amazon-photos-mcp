"""Trash management tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp
from amazon_photos_mcp.utils import _safe_df_to_result


@mcp.tool(annotations=_tool_annotations("trash_items"))
@_tool
def trash_items(node_ids: list[str]) -> dict[str, Any]:
    """Move items to the trash (recoverable for 30 days)."""
    ap = _get_client()
    ap.trash(node_ids)
    return {"status": "ok", "action": "trashed", "count": len(node_ids), "node_ids": node_ids}


@mcp.tool(annotations=_tool_annotations("list_trashed"))
@_tool
def list_trashed(within_days: int = 0) -> dict[str, Any]:
    """List items in the Amazon Photos trash.

    Args:
        within_days: If > 0, only show items trashed in the last N days (max 30).
                     Default 0 shows all trashed items.
    """
    ap = _get_client()
    data = ap.trashed()

    if not data:
        return _safe_df_to_result(None, max_results=200)

    if within_days > 0:
        within_days = min(within_days, 30)
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)

        def _parse_md(item: dict[str, Any]) -> datetime | None:
            md = item.get("modifiedDate")
            if not md or not isinstance(md, str):
                return None
            try:
                return datetime.fromisoformat(md.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        filtered = []
        for item in data:
            d = _parse_md(item)
            if d is not None and d >= cutoff:
                filtered.append(item)
        filtered.sort(key=lambda i: i.get("modifiedDate") or "", reverse=True)
        data = filtered

    return _safe_df_to_result(data, max_results=200)


@mcp.tool(annotations=_tool_annotations("restore_items"))
@_tool
def restore_items(node_ids: list[str]) -> dict[str, Any]:
    """Restore items from the trash back to the library."""
    ap = _get_client()
    ap.restore(node_ids)
    return {"status": "ok", "action": "restored", "count": len(node_ids), "node_ids": node_ids}


@mcp.tool(annotations=_tool_annotations("permanently_delete"))
@_tool
def permanently_delete(node_ids: list[str], confirm: bool = False) -> dict[str, Any]:
    """Permanently delete items (bypasses trash — irreversible). Requires confirm=True."""
    if not confirm:
        return {
            "status": "aborted",
            "message": (
                f"Refusing to permanently delete {len(node_ids)} item(s). "
                "Pass confirm=True to proceed. This is irreversible."
            ),
        }
    ap = _get_client()
    result = ap.delete(node_ids)
    if isinstance(result, dict):
        return result
    return {"status": "ok", "action": "permanently_deleted", "count": len(node_ids), "node_ids": node_ids}


# Deprecated — use list_trashed(within_days=N)
@mcp.tool(annotations=_tool_annotations("list_recently_deleted"))
@_tool
def list_recently_deleted(within_days: int = 7) -> dict[str, Any]:
    """DEPRECATED: Use list_trashed(within_days=N) instead."""
    return list_trashed(within_days=within_days)
