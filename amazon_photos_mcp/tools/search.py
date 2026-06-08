"""Photo/video search and browse tools."""

from __future__ import annotations

import re
from typing import Any

from amazon_photos_mcp import _get_client, _safe_df_to_result, _tool, _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("search_photos"))
@_tool
def search_photos(query: str, max_results: int = 25) -> dict[str, Any]:
    """Search Amazon Photos by query string with optional filters (type, things, dates, etc.)."""
    ap = _get_client()
    df = ap.query(query)
    return _safe_df_to_result(df, min(max_results, 200))


@mcp.tool(annotations=_tool_annotations("get_photos"))
@_tool
def get_photos(max_results: int = 25) -> dict[str, Any]:
    """Get recent photos from your Amazon Photos library."""
    ap = _get_client()
    df = ap.photos()
    return _safe_df_to_result(df, min(max_results, 200), slim=True)


@mcp.tool(annotations=_tool_annotations("get_videos"))
@_tool
def get_videos(max_results: int = 25) -> dict[str, Any]:
    """Get recent videos from your Amazon Photos library."""
    ap = _get_client()
    df = ap.videos()
    return _safe_df_to_result(df, min(max_results, 200), slim=True)


@mcp.tool(annotations=_tool_annotations("search_by_date"))
@_tool
def search_by_date(
    year: int,
    month: int | None = None,
    day: int | None = None,
    media_type: str = "PHOTOS",
    max_results: int = 25,
) -> dict[str, Any]:
    """Search photos/videos by date range."""
    ap = _get_client()
    parts = [f"type:({media_type})", f"timeYear:({year})"]
    if month:
        parts.append(f"timeMonth:({month})")
    if day:
        parts.append(f"timeDay:({day})")
    df = ap.query(" ".join(parts))
    return _safe_df_to_result(df, min(max_results, 200))


@mcp.tool(annotations=_tool_annotations("search_by_things"))
@_tool
def search_by_things(
    things: str,
    media_type: str = "PHOTOS",
    max_results: int = 25,
) -> dict[str, Any]:
    """Search photos by auto-detected labels (e.g. 'beach', 'dog AND park')."""
    ap = _get_client()
    df = ap.query(f"type:({media_type}) things:({things})")
    return _safe_df_to_result(df, min(max_results, 200))


@mcp.tool(annotations=_tool_annotations("search_by_person"))
@_tool
def search_by_person(person: str, max_results: int = 50) -> dict[str, Any]:
    """Search photos containing a specific person by name or cluster ID."""
    ap = _get_client()
    max_results = min(max_results, 200)
    cluster_id = None
    people = ap.aggregations("allPeople", out="")
    for entry in people:
        cname = entry.get("searchData", {}).get("clusterName", "")
        if cname and cname.lower() == person.lower():
            cluster_id = entry["value"]
            break
    if cluster_id is None:
        cluster_id = person
    df = ap.query(f"type:(PHOTOS) clusterId:({cluster_id})")
    return _safe_df_to_result(df, max_results)


@mcp.tool(annotations=_tool_annotations("advanced_search"))
@_tool
def advanced_search(
    content_type: str = "",
    date_from: str = "",
    date_to: str = "",
    min_size: int = 0,
    max_size: int = 0,
    has_location: bool | None = None,
    is_favorite: bool | None = None,
    is_hidden: bool | None = None,
    person: str = "",
    things: str = "",
    sort_by: str = "date",
    sort_order: str = "desc",
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Amazon Photos with structured filter criteria.

    Builds the Amazon Photos query string from structured parameters.
    Use this instead of writing raw query strings.

    Args:
        content_type: "image/jpeg", "image/png", "video/mp4", etc.
        date_from: ISO date string (e.g. "2024-01-01") for start of range
        date_to: ISO date string for end of range
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes
        has_location: Only return items with/without GPS location
        is_favorite: Filter by favorite status
        is_hidden: Filter by hidden status
        person: Name or cluster ID for face search
        things: Comma-separated thing labels ("beach, dog")
        sort_by: "date", "size", or "name"
        sort_order: "asc" or "desc"
        max_results: Maximum results to return (capped at 200)
    """
    ap = _get_client()
    parts: list[str] = []

    # Content type
    if content_type:
        parts.append(f"type:({content_type})")
    else:
        parts.append("type:(PHOTOS)")

    def _validate_date(d: str) -> str | None:
        if not d:
            return None
        # Accept YYYYMMDD or YYYY-MM-DD; reject anything else
        if re.match(r"^\d{8}$", d):
            return d
        if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            return d.replace("-", "")
        return None

    date_from_clean = _validate_date(date_from)
    date_to_clean = _validate_date(date_to)

    if (date_from and not date_from_clean) or (date_to and not date_to_clean):
        return {
            "error": True,
            "code": "INVALID_ARGS",
            "message": "Invalid date format. Use YYYY-MM-DD or YYYYMMDD.",
        }

    # Date range — Amazon Photos uses createdDate:[YYYYMMDD TO YYYYMMDD] syntax
    if date_from_clean and date_to_clean:
        parts.append(
            f"createdDate:[{date_from_clean} TO {date_to_clean}]"
        )
    elif date_from_clean:
        parts.append(f"createdDate:[{date_from_clean} TO]")
    elif date_to_clean:
        parts.append(f"createdDate:[ TO {date_to_clean}]")

    # Things
    if things:
        parts.append(f"things:({things})")

    # Person
    if person:
        cluster_id = None
        people = ap.aggregations("allPeople", out="")
        for entry in people:
            cname = entry.get("searchData", {}).get("clusterName", "")
            if cname and cname.lower() == person.lower():
                cluster_id = entry["value"]
                break
        if cluster_id is None:
            cluster_id = person
        parts.append(f"clusterId:({cluster_id})")

    # Build query and execute
    query_str = " ".join(p for p in parts if p)
    df = ap.query(query_str)

    if df is None or (hasattr(df, "empty") and df.empty):
        return _safe_df_to_result(df, max_results)

    # Post-filtering for criteria Amazon query syntax doesn't support
    # Size filter
    if min_size > 0 and "size" in df.columns:
        df = df[df["size"] >= min_size]
    if max_size > 0 and "size" in df.columns:
        df = df[df["size"] <= max_size]

    # Location filter
    if has_location is True and "location.latitude" in df.columns:
        df = df[df["location.latitude"].notna()]
    elif has_location is False and "location.latitude" in df.columns:
        df = df[df["location.latitude"].isna()]

    # Favorite filter
    if is_favorite is True and "settings.favorite" in df.columns:
        df = df[df["settings.favorite"] == True]  # noqa: E712
    elif is_favorite is False and "settings.favorite" in df.columns:
        df = df[df["settings.favorite"] != True]  # noqa: E712

    # Hidden filter
    if is_hidden is True and "settings.hidden" in df.columns:
        df = df[df["settings.hidden"] == True]  # noqa: E712
    elif is_hidden is False and "settings.hidden" in df.columns:
        df = df[df["settings.hidden"] != True]  # noqa: E712

    # Sort
    if sort_by == "size" and "size" in df.columns:
        df = df.sort_values("size", ascending=(sort_order == "asc"))
    elif sort_by == "name" and "name" in df.columns:
        df = df.sort_values("name", ascending=(sort_order == "asc"))
    elif "createdDate" in df.columns:
        df = df.sort_values("createdDate", ascending=(sort_order == "asc"))

    result = _safe_df_to_result(df, min(max_results, 200))
    result["query_used"] = query_str
    result["filters_applied"] = {
        "content_type": content_type,
        "date_from": date_from,
        "date_to": date_to,
        "min_size": min_size,
        "max_size": max_size,
        "has_location": has_location,
        "is_favorite": is_favorite,
        "is_hidden": is_hidden,
        "person": person,
        "things": things,
    }
    return result
