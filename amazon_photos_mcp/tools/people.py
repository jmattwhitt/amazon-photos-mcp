"""Face cluster / people management tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("list_people"))
@_tool
async def list_people() -> dict[str, Any]:
    """List all face clusters (people) recognized in your Amazon Photos library."""
    ap = _get_client()
    people = await ap.aggregations("allPeople")
    results: list[dict[str, Any]] = []
    for entry in people:
        name = entry.get("searchData", {}).get("clusterName") or "(unnamed)"
        results.append(
            {
                "name": name,
                "cluster_id": entry.get("value"),
                "count": entry.get("count", 0),
                "node_id": entry.get("searchData", {}).get("nodeId"),
            }
        )
    results.sort(key=lambda x: x["count"], reverse=True)
    return {"items": results, "has_more": False, "total": len(results)}


@mcp.tool(annotations=_tool_annotations("name_person"))
@_tool
async def name_person(cluster_id: str, name: str) -> dict[str, Any]:
    """Assign a name to an unidentified face cluster."""
    ap = _get_client()
    result = await ap.update_cluster_name(cluster_id, name)
    return result if isinstance(result, (dict, list)) else {"status": "named", "cluster_id": cluster_id, "name": name}


@mcp.tool(annotations=_tool_annotations("merge_people"))
@_tool
async def merge_people(source_cluster_ids: list[str], target_cluster_id: str) -> dict[str, Any]:
    """Merge face clusters into one (same person recognized multiple ways)."""
    ap = _get_client()
    result = await ap.merge_clusters(target_cluster_id, source_cluster_ids)
    return (
        result
        if isinstance(result, (dict, list))
        else {
            "status": "merged",
            "target": target_cluster_id,
            "sources_merged": len(source_cluster_ids),
        }
    )
