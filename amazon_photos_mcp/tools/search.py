"""Photo/video search and browse tools."""

from __future__ import annotations

import re
from typing import Annotated, Any

import pandas as pd
from pydantic import Field

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp
from amazon_photos_mcp.utils import _safe_df_to_result


def _sanitize_query_value(value: str) -> str:
    """Strip dangerous characters from Amazon Photos query values."""
    # Remove parentheses and double-quotes.
    value = re.sub(r'[()"]', "", value)
    # Remove logical operators with word-boundary anchors.
    value = re.sub(r"\b(AND|OR|NOT)\b", "", value, flags=re.IGNORECASE)
    # Collapse runs of whitespace left by removed tokens
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _resolve_person_cluster(ap: Any, person: str) -> str | None:
    """Resolve a person name to a cluster ID. Returns the cluster ID or None."""
    people = ap.aggregations("allPeople")
    for entry in people:
        cname = entry.get("searchData", {}).get("clusterName", "")
        if cname and cname.lower() == person.lower():
            return entry.get("value")
    return None


def _validate_date(d: str) -> str | None:
    """Validate and normalize an ISO date string. Returns YYYYMMDD or None."""
    if not d:
        return None
    # Accept YYYYMMDD or YYYY-MM-DD; reject anything else
    if re.match(r"^\d{8}$", d):
        return d
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d.replace("-", "")
    return None


@mcp.tool(annotations=_tool_annotations("search_photos"))
@_tool
def search_photos(
    query: Annotated[str, Field(description="The search string (e.g., 'sunset', 'beach')")],
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of results to return")] = 25,
) -> dict[str, Any]:
    """Search Amazon Photos by query string with optional filters (type, things, dates, etc.)."""
    ap = _get_client()
    query_clean = _sanitize_query_value(query)
    if not query_clean:
        return {"error": True, "code": "INVALID_ARGS", "message": "query parameter cannot be empty after sanitization."}
    items = ap.query(query_clean)
    df = pd.json_normalize(items) if items else pd.DataFrame()
    return _safe_df_to_result(df, min(max_results, 200))


@mcp.tool(annotations=_tool_annotations("get_photos"))
@_tool
def get_photos(
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of photos to return")] = 25,
) -> dict[str, Any]:
    """Get recent photos from your Amazon Photos library."""
    ap = _get_client()
    items = ap.photos()
    df = pd.json_normalize(items) if items else pd.DataFrame()
    return _safe_df_to_result(df, min(max_results, 200), slim=True)


@mcp.tool(annotations=_tool_annotations("get_videos"))
@_tool
def get_videos(
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of videos to return")] = 25,
) -> dict[str, Any]:
    """Get recent videos from your Amazon Photos library."""
    ap = _get_client()
    items = ap.videos()
    df = pd.json_normalize(items) if items else pd.DataFrame()
    return _safe_df_to_result(df, min(max_results, 200), slim=True)


@mcp.tool(annotations=_tool_annotations("search_by_date"))
@_tool
def search_by_date(
    year: Annotated[int, Field(ge=1990, le=2100, description="The 4-digit year")],
    month: Annotated[int | None, Field(ge=1, le=12, description="The month (1-12)")] = None,
    day: Annotated[int | None, Field(ge=1, le=31, description="The day of the month (1-31)")] = None,
    media_type: Annotated[str, Field(description="Media type filter ('PHOTOS' or 'VIDEOS')")] = "PHOTOS",
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of results")] = 25,
) -> dict[str, Any]:
    """Search photos/videos by date range."""
    if month is not None and not (1 <= month <= 12):
        return {"error": True, "code": "INVALID_ARGS", "message": f"month must be 1-12, got {month}"}
    if day is not None and not (1 <= day <= 31):
        return {"error": True, "code": "INVALID_ARGS", "message": f"day must be 1-31, got {day}"}
    ap = _get_client()
    media_type_clean = _sanitize_query_value(media_type)
    parts = [f"type:({media_type_clean})", f"timeYear:({year})"]
    if month:
        parts.append(f"timeMonth:({month})")
    if day:
        parts.append(f"timeDay:({day})")
    items = ap.query(" ".join(parts))
    df = pd.json_normalize(items) if items else pd.DataFrame()
    return _safe_df_to_result(df, min(max_results, 200))


@mcp.tool(annotations=_tool_annotations("search_by_things"))
@_tool
def search_by_things(
    things: Annotated[str, Field(description="Comma-separated labels (e.g. 'beach', 'dog')")],
    media_type: Annotated[str, Field(description="Media type filter ('PHOTOS' or 'VIDEOS')")] = "PHOTOS",
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of results")] = 25,
) -> dict[str, Any]:
    """Search photos by auto-detected labels (e.g. 'beach', 'dog AND park')."""
    ap = _get_client()
    media_type_clean = _sanitize_query_value(media_type)
    things_clean = _sanitize_query_value(things)
    if not things_clean:
        return {
            "error": True,
            "code": "INVALID_ARGS",
            "message": "things parameter cannot be empty after sanitization.",
        }
    items = ap.query(f"type:({media_type_clean}) things:({things_clean})")
    df = pd.json_normalize(items) if items else pd.DataFrame()
    return _safe_df_to_result(df, min(max_results, 200))


@mcp.tool(annotations=_tool_annotations("search_by_person"))
@_tool
def search_by_person(
    person: Annotated[str, Field(description="Name or cluster ID of the person to search for")],
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of results")] = 50,
) -> dict[str, Any]:
    """Search photos containing a specific person by name or cluster ID."""
    ap = _get_client()
    max_results = min(max_results, 200)
    person_clean = _sanitize_query_value(person)
    cluster_id = _resolve_person_cluster(ap, person_clean)
    if cluster_id is None:
        cluster_id = person_clean
    items = ap.query(f"type:(PHOTOS) clusterId:({cluster_id})")
    df = pd.json_normalize(items) if items else pd.DataFrame()
    return _safe_df_to_result(df, max_results)


@mcp.tool(annotations=_tool_annotations("advanced_search"))
@_tool
def advanced_search(
    content_type: Annotated[str, Field(description="E.g., 'image/jpeg', 'image/png', 'video/mp4'")] = "",
    date_from: Annotated[str, Field(description="ISO date string (e.g. '2024-01-01')")] = "",
    date_to: Annotated[str, Field(description="ISO date string (e.g. '2024-12-31')")] = "",
    min_size: Annotated[int, Field(ge=0, description="Minimum file size in bytes")] = 0,
    max_size: Annotated[int, Field(ge=0, description="Maximum file size in bytes")] = 0,
    has_location: Annotated[bool | None, Field(description="Filter by presence of GPS location")] = None,
    is_favorite: Annotated[bool | None, Field(description="Filter by favorite status")] = None,
    is_hidden: Annotated[bool | None, Field(description="Filter by hidden status")] = None,
    person: Annotated[str, Field(description="Name or cluster ID of the person")] = "",
    things: Annotated[str, Field(description="Comma-separated labels (e.g., 'beach, dog')")] = "",
    sort_by: Annotated[str, Field(description="Sort key ('date', 'size', or 'name')")] = "date",
    sort_order: Annotated[str, Field(description="Sort direction ('asc' or 'desc')")] = "desc",
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum results to return")] = 50,
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
        content_type_clean = _sanitize_query_value(content_type)
        if content_type_clean:
            parts.append(f"type:({content_type_clean})")
        else:
            parts.append("type:(PHOTOS)")
    else:
        parts.append("type:(PHOTOS)")

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
        parts.append(f"createdDate:[{date_from_clean} TO {date_to_clean}]")
    elif date_from_clean:
        parts.append(f"createdDate:[{date_from_clean} TO]")
    elif date_to_clean:
        parts.append(f"createdDate:[ TO {date_to_clean}]")

    # Things
    if things:
        things_clean = _sanitize_query_value(things)
        if things_clean:
            parts.append(f"things:({things_clean})")

    # Person
    if person:
        person_clean = _sanitize_query_value(person)
        cluster_id = _resolve_person_cluster(ap, person_clean)
        if cluster_id is None:
            cluster_id = person_clean
        parts.append(f"clusterId:({cluster_id})")

    # Build query and execute
    query_str = " ".join(p for p in parts if p)
    items = ap.query(query_str)
    df = pd.json_normalize(items) if items else pd.DataFrame()

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
        df = df[df["settings.favorite"]]
    elif is_favorite is False and "settings.favorite" in df.columns:
        df = df[~df["settings.favorite"]]

    # Hidden filter
    if is_hidden is True and "settings.hidden" in df.columns:
        df = df[df["settings.hidden"]]
    elif is_hidden is False and "settings.hidden" in df.columns:
        df = df[~df["settings.hidden"]]

    # Sort
    if sort_by == "size" and "size" in df.columns:
        df = df.sort_values("size", ascending=(sort_order == "asc"))
    elif sort_by == "name" and "name" in df.columns:
        df = df.sort_values("name", ascending=(sort_order == "asc"))
    elif "createdDate" in df.columns:
        df = df.sort_values("createdDate", ascending=(sort_order == "asc"))

    result = _safe_df_to_result(df, min(max_results, 200))
    result["query_used"] = query_str
    # Surface which post-filters were active (helps diagnose zero-result responses)
    active_post_filters = []
    if min_size > 0:
        active_post_filters.append(f"min_size>={min_size}")
    if max_size > 0:
        active_post_filters.append(f"max_size<={max_size}")
    if has_location is True:
        active_post_filters.append("has_location=True")
    if has_location is False:
        active_post_filters.append("has_location=False")
    if is_favorite is not None:
        active_post_filters.append(f"is_favorite={is_favorite}")
    if is_hidden is not None:
        active_post_filters.append(f"is_hidden={is_hidden}")
    if active_post_filters:
        result["post_filters_applied"] = active_post_filters
        if result["total"] == 0 and result["items"] == []:
            result["note"] = (
                "No results matched after post-filtering. Try relaxing size, location, favorite, or hidden filters."
            )
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
