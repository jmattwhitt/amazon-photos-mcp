"""Face cluster / people management tools."""

from __future__ import annotations

from typing import Any

from amazon_photos_mcp import _get_client, _safe_df_to_result, _tool, _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("list_people"))
@_tool
def list_people() -> dict[str, Any]:
    """List all face clusters (people) recognized in your Amazon Photos library."""
    ap = _get_client()
    people = ap.aggregations("allPeople", out="")
    results: list[dict[str, Any]] = []
    for entry in people:
        name = entry.get("searchData", {}).get("clusterName") or "(unnamed)"
        results.append({
            "name": name,
            "cluster_id": entry["value"],
            "count": entry["count"],
            "node_id": entry.get("searchData", {}).get("nodeId"),
        })
    results.sort(key=lambda x: x["count"], reverse=True)
    return {"items": results, "has_more": False, "total": len(results)}


@mcp.tool(annotations=_tool_annotations("name_person"))
@_tool
def name_person(cluster_id: str, name: str) -> dict[str, Any]:
    """Assign a name to an unidentified face cluster."""
    ap = _get_client()
    result = ap.update_cluster_name(cluster_id, name)
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    return {"status": "named", "cluster_id": cluster_id, "name": name}


@mcp.tool(annotations=_tool_annotations("merge_people"))
@_tool
def merge_people(source_cluster_ids: list[str], target_cluster_id: str) -> dict[str, Any]:
    """Merge face clusters into one (same person recognized multiple ways)."""
    ap = _get_client()
    result = ap.merge_clusters(target_cluster_id, source_cluster_ids)
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    return {
        "status": "merged",
        "target": target_cluster_id,
        "sources_merged": len(source_cluster_ids),
    }
