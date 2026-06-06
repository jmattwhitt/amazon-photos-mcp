"""FastMCP Amazon Photos Server — search, browse, and manage your Amazon Photos library."""

from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import pandas as pd
from fastmcp import FastMCP

mcp = FastMCP("amazon-photos")

# Tool annotations per MCP 2025-11-25 spec
_READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "check_connection", "refresh_client", "validate_cookies",
    "get_storage_usage", "get_aggregations",
    "search_photos", "get_photos", "get_videos",
    "search_by_date", "search_by_things",
    "get_photo_url", "get_exif_data",
    "list_folders", "get_folder_tree",
    "list_albums", "list_people", "search_by_person",
    "find_duplicates", "preview_duplicate_group",
    "find_near_duplicates",
    "check_db_integrity",
})

_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "permanently_delete", "trash_items", "trash_duplicates",
    "keep_specific", "merge_people",
})

_IDEMPOTENT_TOOLS: frozenset[str] = frozenset({
    "create_album", "add_to_album", "remove_from_album",
    "set_favorite", "favorite_items", "unfavorite_items",
    "set_hidden", "hide_items", "unhide_items",
    "name_person", "restore_items", "upload_file", "upload_folder",
    "list_trashed", "list_recently_deleted",
    "download", "download_files", "download_by_date", "download_for_pipeline",
    "download_library",
})


def _tool_annotations(tool_name: str) -> dict[str, bool]:
    """Return MCP tool annotations for the given tool name."""
    annotations: dict[str, bool] = {}
    if tool_name in _READ_ONLY_TOOLS:
        annotations["readOnlyHint"] = True
    if tool_name in _DESTRUCTIVE_TOOLS:
        annotations["destructiveHint"] = True
    if tool_name in _IDEMPOTENT_TOOLS:
        annotations["idempotentHint"] = True
    return annotations

PIPELINE_DEFAULT_DIR = os.environ.get(
    "AMAZON_PHOTOS_PIPELINE_DIR",
    str(Path.home() / "Downloads" / "amazon-photos-pipeline"),
)

SLIM_FIELDS = {
    "id", "name", "createdDate", "modifiedDate", "contentType", "size", "md5",
    "settings.favorite", "settings.hidden", "image.width", "image.height",
    "location.latitude", "location.longitude",
}


class MCPError(Exception):
    """Base MCP error with machine-readable code."""

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        self.code = code
        super().__init__(message)


class AuthenticationError(MCPError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="AUTH_REQUIRED")


class ResourceNotFoundError(MCPError):
    def __init__(self, resource_type: str, resource_id: str) -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} not found: {resource_id}", code="NOT_FOUND")


class RateLimitError(MCPError):
    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s.", code="RATE_LIMITED")


_AMAZON_COOKIE_PATH = Path.home() / ".config" / "amazon-photos-mcp" / "cookies.json"
_COOKIE_EXPIRED_AFTER_HOURS = 72.0
_COOKIE_WARN_AFTER_HOURS = 48.0
_COOKIE_STAT_CACHE_TTL = 300.0

_cookie_last_stat: float = 0.0
_cookie_cached_mtime: float | None = None


def _cookie_age_hours() -> float | None:
    global _cookie_last_stat, _cookie_cached_mtime
    now = time.time()
    mtime: float | None
    if now - _cookie_last_stat < _COOKIE_STAT_CACHE_TTL and _cookie_cached_mtime is not None:
        # Cache hit — but the file could have been deleted since it was cached.
        # If the cache mtime points to a now-missing file, treat it as missing.
        mtime = _cookie_cached_mtime
    else:
        try:
            _cookie_cached_mtime = _AMAZON_COOKIE_PATH.stat().st_mtime
        except FileNotFoundError:
            _cookie_cached_mtime = None
        _cookie_last_stat = now
        mtime = _cookie_cached_mtime
    if mtime is None:
        return None
    return (time.time() - mtime) / 3600


def _cookie_advice() -> str:
    h = _cookie_age_hours()
    if h is None:
        return "Cookie file not found. Create ~/.config/amazon-photos-mcp/cookies.json."
    if h >= _COOKIE_EXPIRED_AFTER_HOURS:
        return f"Cookies expired ({h:.0f}h old). Refresh immediately and call refresh_client."
    if h >= _COOKIE_WARN_AFTER_HOURS:
        return f"Cookies stale ({h:.0f}h old). Consider refreshing soon."
    return f"Cookies fresh ({h:.0f}h old)."


def _invalidate_cookie_cache() -> None:
    global _cookie_last_stat, _cookie_cached_mtime
    _cookie_last_stat = 0.0
    _cookie_cached_mtime = None


P = ParamSpec("P")
R = TypeVar("R")


def _tool(fn: Callable[P, R]) -> Callable[P, R | dict[str, Any]]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except AuthenticationError as e:
            return {
                "error": True,
                "code": e.code,
                "message": str(e),
                "suggestion": "Update cookies.json and call refresh_client.",
            }
        except RateLimitError as e:
            return {
                "error": True,
                "code": e.code,
                "message": str(e),
                "retry_after_seconds": e.retry_after,
            }
        except ResourceNotFoundError as e:
            return {
                "error": True,
                "code": e.code,
                "message": str(e),
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
            }
        except Exception as e:
            return {
                "error": True,
                "code": "UNEXPECTED_ERROR",
                "message": str(e),
                "tool": fn.__name__,
                "traceback": traceback.format_exc(),
            }

    return wrapper


_client_lock = threading.Lock()
_stdout_lock = threading.Lock()
_client: Any = None


def _normalize_cookies(raw: dict[str, Any]) -> dict[str, Any]:
    # The library's determine_tld() checks for keys ending with '_main' to detect
    # .com domains, but Amazon's HTTP API expects hyphenated names (ubid-main,
    # at-main). Keep both formats so TLD detection and auth both work.
    normalized = dict(raw)
    pairs = [("ubid-main", "ubid_main"), ("at-main", "at_main")]
    for hyphen, underscore in pairs:
        if hyphen in normalized and underscore not in normalized:
            normalized[underscore] = normalized[hyphen]
        elif underscore in normalized and hyphen not in normalized:
            normalized[hyphen] = normalized[underscore]
    return normalized


def _load_cookies() -> dict[str, Any] | None:
    env_cookies = os.environ.get("AMAZON_PHOTOS_COOKIES")
    if env_cookies:
        return _normalize_cookies(json.loads(env_cookies))
    from amazon_photos_mcp.crypto import load_encrypted_cookies

    cookies = load_encrypted_cookies(_AMAZON_COOKIE_PATH)
    if cookies is not None:
        return _normalize_cookies(cookies)
    return None


def _get_client(force_refresh: bool = False) -> Any:
    global _client
    with _client_lock:
        if force_refresh:
            _client = None
            _invalidate_cookie_cache()
        if _client is not None:
            return _client

        from amazon_photos import AmazonPhotos

        cookies = _load_cookies()
        if not cookies:
            raise AuthenticationError(
                "No Amazon cookies configured. Create "
                "~/.config/amazon-photos-mcp/cookies.json with keys: "
                "ubid-main, at-main, session-id  (or set AMAZON_PHOTOS_COOKIES env var)"
            )

        db_path = os.environ.get(
            "AMAZON_PHOTOS_DB",
            str(_AMAZON_COOKIE_PATH.parent / "ap.parquet"),
        )
        db_path_obj = Path(db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # If no parquet exists, create an empty one so load_db() reads from
        # the file instead of fetching all photos during client init (which
        # can fail on large libraries with 100K+ items due to concurrent
        # async pagination exhausting retries).
        if not db_path_obj.exists():
            import pandas as pd
            pd.DataFrame().to_parquet(db_path_obj)

        # AmazonPhotos.__init__ makes three slow/heavy API calls on construction:
        #   get_root()     -> 1 sync request
        #   get_folders()  -> recursive async requests (can take minutes for large libraries)
        #   build_tree()   -> CPU-bound, depends on root/folders
        # These cause MCP handshake timeouts on large libraries.
        # Patch them to no-ops for construction; tools that need root/folders/tree
        # call the real methods on-demand via the client instance.
        _orig_get_root = AmazonPhotos.get_root
        _orig_get_folders = AmazonPhotos.get_folders
        _orig_build_tree = AmazonPhotos.build_tree
        try:
            AmazonPhotos.get_root = lambda self: {"id": "", "ownerId": ""}
            AmazonPhotos.get_folders = lambda self: []
            AmazonPhotos.build_tree = lambda self, folders=None: {}
            _client = AmazonPhotos(cookies=cookies, db_path=db_path)
        finally:
            AmazonPhotos.get_root = _orig_get_root
            AmazonPhotos.get_folders = _orig_get_folders
            AmazonPhotos.build_tree = _orig_build_tree

        _wrap_http_errors(_client)

        return _client


def _wrap_http_errors(client: Any) -> None:
    """Wrap the client's httpx session to detect rate limiting."""
    from amazon_photos_mcp.rate_limiter import check_rate_limit

    if hasattr(client, "_session"):
        session = client._session
        orig_request = session.request

        def _patched_request(method: str, url: str, **kwargs: Any) -> Any:
            check_rate_limit()
            resp = orig_request(method, url, **kwargs)
            if hasattr(resp, "status_code"):
                if resp.status_code == 429:
                    raise RateLimitError(
                        retry_after=int(resp.headers.get("Retry-After", 60))
                    )
                if resp.status_code == 503:
                    raise RateLimitError(retry_after=30)
            return resp

        session.request = _patched_request


def _is_nan(v: Any) -> bool:
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (None if _is_nan(v) else v) for k, v in row.items()}


def _safe_df_to_list(df: Any, max_results: int = 50, slim: bool = False) -> list[dict[str, Any]]:
    if df is None:
        return []
    if isinstance(df, list):
        return df[:max_results]
    if hasattr(df, "empty") and df.empty:
        return []
    if hasattr(df, "columns") and "id" in df.columns:
        df = df.drop_duplicates(subset=["id"])
    if not hasattr(df, "to_dict"):
        return [{"value": str(df)}]
    records = df.head(max_results).to_dict(orient="records")
    result = [_clean_row(r) for r in records]
    if slim:
        result = [{k: v for k, v in r.items() if k in SLIM_FIELDS} for r in result]
    return result


def _safe_df_to_result(df: Any, max_results: int = 50, slim: bool = False) -> dict[str, Any]:
    """Like _safe_df_to_list but returns dict with truncation metadata."""
    if df is None:
        return {"items": [], "has_more": False, "total": 0}
    if isinstance(df, list):
        total = len(df)
        items = df[:max_results]
        return {"items": items, "has_more": total > max_results, "total": total}
    if hasattr(df, "empty") and df.empty:
        return {"items": [], "has_more": False, "total": 0}
    total = len(df)
    if hasattr(df, "columns") and "id" in df.columns:
        df = df.drop_duplicates(subset=["id"])
    if not hasattr(df, "to_dict"):
        return {"items": [{"value": str(df)}], "has_more": False, "total": 1}
    items = df.head(max_results).to_dict(orient="records")
    items = [_clean_row(r) for r in items]
    if slim:
        items = [{k: v for k, v in r.items() if k in SLIM_FIELDS} for r in items]
    return {"items": items, "has_more": total > max_results, "total": total}


@mcp.tool(annotations=_tool_annotations("check_connection"))
@_tool
def check_connection() -> dict[str, Any]:
    """Test connection to Amazon Photos and report storage usage and cookie health."""
    advice = _cookie_advice()
    age_hours = _cookie_age_hours()
    age_days = age_hours / 24 if age_hours is not None else None
    warnings: list[str] = []

    if age_hours is None or age_hours >= _COOKIE_EXPIRED_AFTER_HOURS:
        warnings.append(advice)
    elif age_hours >= _COOKIE_WARN_AFTER_HOURS:
        warnings.append(advice)

    ap = _get_client()
    usage = ap.usage()
    data: dict[str, Any] = usage.json() if hasattr(usage, "json") else {"usage": str(usage)}
    data["status"] = "connected"
    data["cookie_health"] = advice
    if age_days is not None:
        data["cookie_age_days"] = round(age_days, 1)
    if warnings:
        data["warnings"] = warnings
    return data


@mcp.tool(annotations=_tool_annotations("refresh_client"))
@_tool
def refresh_client() -> dict[str, Any]:
    """Force a fresh client connection. Use after updating cookies.json."""
    _get_client(force_refresh=True)
    return check_connection()


@mcp.tool(annotations=_tool_annotations("validate_cookies"))
@_tool
def validate_cookies() -> dict[str, Any]:
    """Check whether stored cookies are still accepted by Amazon."""
    age_hours = _cookie_age_hours()
    if age_hours is None or age_hours >= _COOKIE_EXPIRED_AFTER_HOURS:
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": _cookie_advice(),
        }
    try:
        ap = _get_client()
        result = ap.usage()
        ok = not (hasattr(result, "status_code") and result.status_code in (401, 403))
        return {
            "valid": ok,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": _cookie_advice(),
        }
    except Exception as e:
        s = str(e).lower()
        auth_fail = any(x in s for x in ("401", "403", "unauthorized", "forbidden", "expired"))
        return {
            "valid": False,
            "cookie_age_hours": round(age_hours, 1) if age_hours is not None else None,
            "advice": _cookie_advice(),
            "error": str(e) if not auth_fail else "Auth rejected by Amazon — cookies expired.",
        }


@mcp.tool(annotations=_tool_annotations("get_storage_usage"))
@_tool
def get_storage_usage() -> dict[str, Any]:
    """Get Amazon Photos storage usage (plan, space used, photo/video counts)."""
    ap = _get_client()
    usage = ap.usage()
    if hasattr(usage, "json"):
        return usage.json()  # type: ignore[no-any-return]
    return {"usage": str(usage)}


@mcp.tool(annotations=_tool_annotations("get_aggregations"))
@_tool
def get_aggregations(category: str = "all") -> dict[str, Any]:
    """Get auto-generated aggregations: people, things, locations, dates."""
    ap = _get_client()
    result = ap.aggregations(category, out="")
    if isinstance(result, dict):
        return result
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    if hasattr(result, "to_dict"):
        return result.to_dict()  # type: ignore[no-any-return]
    return {"aggregations": str(result)}


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


@mcp.tool(annotations=_tool_annotations("get_photo_url"))
@_tool
def get_photo_url(node_id: str) -> dict[str, Any]:
    """Get the direct download URL for a photo/video by node ID."""
    ap = _get_client()
    result = ap.get_file(node_id)
    url = None
    if hasattr(result, "json"):
        data = result.json()
        url = (
            data.get("tempLink")
            or data.get("contentUrl")
            or data.get("url")
        )
    return {
        "node_id": node_id,
        "url": url,
        "raw": str(result)[:500] if url is None else None,
    }


@mcp.tool(annotations=_tool_annotations("get_exif_data"))
@_tool
def get_exif_data(node_id: str) -> dict[str, Any]:
    """Get EXIF metadata for a photo by node ID. Falls back to local parquet DB if API doesn't expose EXIF."""
    ap = _get_client()

    try:
        result = ap.get_file(node_id)
        if hasattr(result, "json"):
            data = result.json()
            exif: dict[str, Any] = {}
            for section in ("image", "video", "exifData", "media"):
                if section in data:
                    exif.update(data[section])
            if exif:
                return {"node_id": node_id, "source": "api", "exif": exif}
    except Exception:
        pass

    db = ap.db
    if db is not None and "id" in db.columns:
        rows = db[db["id"] == node_id]
        if not rows.empty:
            row = _clean_row(rows.iloc[0].to_dict())
            exif_keys = [k for k in row if any(
                prefix in k.lower()
                for prefix in ("image.", "camera", "exif", "gps", "iso", "exposure", "aperture", "focal")
            )]
            return {
                "node_id": node_id,
                "source": "local_db",
                "exif": {k: row[k] for k in exif_keys if row.get(k) is not None},
                "note": "Upstream library did not return EXIF via API; showing indexed fields from local cache.",
            }

    return {"node_id": node_id, "exif": {}, "note": "No EXIF data found."}


@mcp.tool(annotations=_tool_annotations("list_folders"))
@_tool
def list_folders() -> dict[str, Any]:
    """List all folders in your Amazon Photos library."""
    ap = _get_client()
    df = ap.get_folders()
    return _safe_df_to_result(df, max_results=500)


@mcp.tool(annotations=_tool_annotations("get_folder_tree"))
@_tool
def get_folder_tree() -> str:
    """Display the folder tree of your Amazon Photos library."""
    ap = _get_client()
    buf = io.StringIO()
    with _stdout_lock, contextlib.redirect_stdout(buf):
        ap.print_tree()
    return buf.getvalue() or "No folder tree available."


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
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    return {"status": "created", "name": name, "result": str(result)}


@mcp.tool(annotations=_tool_annotations("add_to_album"))
@_tool
def add_to_album(album_id: str, node_ids: list[str]) -> dict[str, Any]:
    """Add photos/videos to an existing album."""
    ap = _get_client()
    result = ap.add_to_album(album_id, node_ids)
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    return {"status": "added", "album_id": album_id, "count": len(node_ids)}


@mcp.tool(annotations=_tool_annotations("remove_from_album"))
@_tool
def remove_from_album(album_id: str, node_ids: list[str]) -> dict[str, Any]:
    """Remove photos/videos from an album (does not delete files)."""
    ap = _get_client()
    result = ap.remove_from_album(album_id, node_ids)
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    return {"status": "removed", "album_id": album_id, "count": len(node_ids)}


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


@mcp.tool(annotations=_tool_annotations("trash_items"))
@_tool
def trash_items(node_ids: list[str]) -> dict[str, Any]:
    """Move items to the trash (recoverable for 30 days)."""
    ap = _get_client()
    result = ap.trash(node_ids)
    if hasattr(result, "json"):
        resp: dict[str, Any] = result.json()
        resp.setdefault("action", "trashed")
        resp.setdefault("count", len(node_ids))
        resp.setdefault("node_ids", node_ids)
        return resp
    return {"status": "ok", "action": "trashed", "count": len(node_ids), "node_ids": node_ids}


@mcp.tool(annotations=_tool_annotations("list_trashed"))
@_tool
def list_trashed(within_days: int = 0) -> dict[str, Any]:
    """List items in the Amazon Photos trash.

    Args:
        within_days: If > 0, only show items trashed in the last N days (max 30).
                     Default 0 shows all trashed items.
    """
    import pandas as pd

    ap = _get_client()
    df = ap.trashed()

    if df is None or (hasattr(df, "empty") and df.empty):
        return _safe_df_to_result(df, max_results=200)

    if within_days > 0 and "modifiedDate" in df.columns:
        within_days = min(within_days, 30)
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=within_days)
        try:
            df["modifiedDate"] = pd.to_datetime(df["modifiedDate"], utc=True, errors="coerce")
            df = df[df["modifiedDate"] >= cutoff]
            df = df.sort_values("modifiedDate", ascending=False)
        except (TypeError, ValueError):
            pass

    return _safe_df_to_result(df, max_results=200)


# Deprecated — use list_trashed(within_days=N)
@mcp.tool(annotations=_tool_annotations("list_recently_deleted"))
@_tool
def list_recently_deleted(within_days: int = 7) -> dict[str, Any]:
    """DEPRECATED: Use list_trashed(within_days=N) instead."""
    return list_trashed(within_days=within_days)


@mcp.tool(annotations=_tool_annotations("restore_items"))
@_tool
def restore_items(node_ids: list[str]) -> dict[str, Any]:
    """Restore items from the trash back to the library."""
    ap = _get_client()
    result = ap.restore(node_ids)
    if hasattr(result, "json"):
        resp: dict[str, Any] = result.json()
        resp.setdefault("action", "restored")
        resp.setdefault("count", len(node_ids))
        resp.setdefault("node_ids", node_ids)
        return resp
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
    if hasattr(result, "json"):
        return result.json()  # type: ignore[no-any-return]
    return {"status": "ok", "action": "permanently_deleted", "count": len(node_ids), "node_ids": node_ids}


@mcp.tool(annotations=_tool_annotations("download"))
@_tool
def download(
    node_ids: list[str] | None = None,
    query: str = "",
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    media_type: str = "PHOTOS",
    output_dir: str = "",
    max_items: int = 500,
) -> dict[str, Any]:
    """Download photos/videos from Amazon Photos.

    Can download by node IDs, by search query, or by date range.
    One of node_ids, query, or year must be provided.

    Args:
        node_ids: Specific node IDs to download
        query: Amazon Photos query string (e.g., "type:(PHOTOS) AND things:(beach)")
        year: Year filter (requires at least year, optionally month/day)
        month: Month filter (1-12)
        day: Day filter (1-31)
        media_type: "PHOTOS" or "VIDEOS"
        output_dir: Custom output directory (auto-generated if empty)
        max_items: Maximum items to download (capped at 2000)
    """
    ap = _get_client()

    # Resolve what to download
    if node_ids is not None:
        ids = node_ids
        if not output_dir:
            output_dir = str(Path.home() / "Downloads" / "amazon-photos")
    elif year is not None:
        parts = [f"type:({media_type})", f"timeYear:({year})"]
        if month:
            parts.append(f"timeMonth:({month})")
        if day:
            parts.append(f"timeDay:({day})")
        df = ap.query(" ".join(parts))
        items = _safe_df_to_list(df, min(max_items, 2000))
        if not items:
            return {"status": "no_results", "query": " ".join(parts), "count": 0, "node_ids": []}
        ids = [item["id"] for item in items if item.get("id")]
        if not output_dir:
            date_str = f"{year:04d}" + (f"-{month:02d}" if month else "") + (f"-{day:02d}" if day else "")
            output_dir = str(Path.home() / "Downloads" / "amazon-photos" / date_str)
    elif query:
        df = ap.query(query)
        items = _safe_df_to_list(df, min(max_items, 2000))
        if not items:
            return {"status": "no_results", "query": query, "count": 0, "node_ids": []}
        ids = [item["id"] for item in items if item.get("id")]
        if not output_dir:
            slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in query)[:40]
            output_dir = str(Path(PIPELINE_DEFAULT_DIR) / slug / "raw")
    else:
        return {
            "error": True,
            "code": "INVALID_ARGS",
            "message": "Provide node_ids, query, or year to specify what to download.",
        }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    try:
        ap.download(ids, out=str(out))
    except TypeError:
        original_dir = os.getcwd()
        try:
            os.chdir(str(out))
            ap.download(ids)
        finally:
            os.chdir(original_dir)

    return {
        "status": "ok",
        "action": "downloaded",
        "downloaded": len(ids),
        "output_dir": str(out),
        "node_ids": ids,
    }


# Deprecated wrappers
@mcp.tool(annotations=_tool_annotations("download_files"))
@_tool
def download_files(node_ids: list[str], output_dir: str = "") -> dict[str, Any]:
    """DEPRECATED: Use download(node_ids=[...]) instead."""
    return download(node_ids=node_ids, output_dir=output_dir)


@mcp.tool(annotations=_tool_annotations("download_by_date"))
@_tool
def download_by_date(
    year: int,
    month: int | None = None,
    day: int | None = None,
    output_dir: str = "",
    media_type: str = "PHOTOS",
    max_items: int = 500,
) -> dict[str, Any]:
    """DEPRECATED: Use download(year=..., month=..., day=...) instead."""
    return download(year=year, month=month, day=day, output_dir=output_dir,
                    media_type=media_type, max_items=max_items)


@mcp.tool(annotations=_tool_annotations("download_for_pipeline"))
@_tool
def download_for_pipeline(
    query: str,
    output_dir: str = "",
    max_items: int = 200,
) -> dict[str, Any]:
    """DEPRECATED: Use download(query=...) instead."""
    return download(query=query, output_dir=output_dir, max_items=max_items)


@mcp.tool(annotations=_tool_annotations("download_library"))
@_tool
def download_library(
    output_dir: str = "",
    media_type: str = "PHOTOS",
    max_items: int = 5000,
    organize_by: str = "year_month",
) -> dict[str, Any]:
    """Download your entire Amazon Photos library for backup or migration.

    Organizes photos into subdirectories by date for easy import into
    Immich, PhotoPrism, or other self-hosted solutions.

    Args:
        output_dir: Root directory for downloads. Defaults to ~/Downloads/amazon-photos-export/
        media_type: "PHOTOS" or "VIDEOS"
        max_items: Maximum total items to download (capped at 10000)
        organize_by: "year_month" (2024/01/) or "flat" (single directory)
    """
    ap = _get_client()
    max_items = min(max_items, 10000)

    if not output_dir:
        output_dir = str(Path.home() / "Downloads" / "amazon-photos-export")

    # Get all items
    if media_type == "VIDEOS":
        df = ap.videos()
    else:
        df = ap.photos()

    if df is None or (hasattr(df, "empty") and df.empty):
        return {"status": "no_data", "message": f"No {media_type.lower()} found in library."}

    items = _safe_df_to_list(df, max_items)
    if not items:
        return {"status": "no_items", "message": "No items after processing."}

    node_ids = [item["id"] for item in items if item.get("id")]

    out = Path(output_dir)

    # Download in batches with per-date subdirectories
    batch_size = 200
    downloaded = 0
    failed: list[str] = []

    for i in range(0, len(node_ids), batch_size):
        batch = node_ids[i:i + batch_size]

        if organize_by == "year_month":
            batch_items = items[i:i + batch_size]
            for j, nid in enumerate(batch):
                if j < len(batch_items):
                    created = batch_items[j].get("createdDate", "")
                else:
                    created = "unknown"
                date_dir = "unknown"
                if isinstance(created, str) and len(created) >= 7:
                    date_dir = f"{created[:4]}/{created[5:7]}"
                elif created:
                    date_dir = str(created)[:7].replace("-", "/")
                batch_out = out / date_dir
                batch_out.mkdir(parents=True, exist_ok=True)
        else:
            batch_out = out
            batch_out.mkdir(parents=True, exist_ok=True)

        try:
            ap.download(batch, out=str(batch_out))
            downloaded += len(batch)
        except TypeError:
            original_dir = os.getcwd()
            try:
                os.chdir(str(batch_out))
                ap.download(batch)
            finally:
                os.chdir(original_dir)
            downloaded += len(batch)
        except Exception as e:
            failed.extend(batch)
            print(f"[download_library] Batch failed: {e}", file=sys.stderr)

    return {
        "status": "ok",
        "total_found": len(node_ids),
        "downloaded": downloaded,
        "failed_count": len(failed),
        "failed_ids": failed[:50],
        "output_dir": str(out),
        "organize_by": organize_by,
        "import_hint": (
            "For Immich: point External Library at this directory. "
            "For PhotoPrism: use the import folder feature. "
            "For local backup: move/copy this directory to your backup drive."
        ),
    }


@mcp.tool(annotations=_tool_annotations("upload_file"))
@_tool
def upload_file(file_path: str) -> dict[str, Any]:
    """Upload a single file to Amazon Photos. Deduplicates by MD5."""
    import shutil

    path = Path(file_path)
    if not path.exists():
        return {"error": True, "code": "NOT_FOUND", "message": f"File not found: {file_path}"}
    if not path.is_file():
        return {"error": True, "code": "INVALID_INPUT", "message": f"Not a file: {file_path}"}

    ap = _get_client()
    tmp_dir = tempfile.mkdtemp(prefix="ap_upload_")
    try:
        shutil.copy2(str(path), os.path.join(tmp_dir, path.name))
        result = ap.upload(tmp_dir)
        return {
            "status": "ok",
            "action": "uploaded",
            "file": path.name,
            "results": result if isinstance(result, list) else str(result),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@mcp.tool(annotations=_tool_annotations("upload_folder"))
@_tool
def upload_folder(folder_path: str) -> dict[str, Any]:
    """Upload all photos/videos in a folder to Amazon Photos (recursive). Deduplicates by MD5."""
    path = Path(folder_path)
    if not path.exists():
        return {"error": True, "code": "NOT_FOUND", "message": f"Folder not found: {folder_path}"}
    if not path.is_dir():
        return {"error": True, "code": "INVALID_INPUT", "message": f"Not a folder: {folder_path}"}

    ap = _get_client()
    result = ap.upload(str(path))
    count = len(result) if isinstance(result, list) else None
    return {
        "status": "ok",
        "action": "uploaded",
        "folder": str(path),
        "files_processed": count,
        "results": result if isinstance(result, list) else str(result),
    }


@mcp.tool(annotations=_tool_annotations("check_db_integrity"))
@_tool
def check_db_integrity() -> dict[str, Any]:
    """Validate the local parquet metadata cache: schema, row count, and file age."""
    import pandas as pd

    EXPECTED_COLUMNS = {"id", "name", "md5", "size", "createdDate", "contentType"}

    db_path = Path(
        os.environ.get(
            "AMAZON_PHOTOS_DB",
            str(_AMAZON_COOKIE_PATH.parent / "ap.parquet"),
        )
    )

    if not db_path.exists():
        return {
            "valid": False,
            "message": f"Parquet DB not found at {db_path}. Call check_connection to initialize.",
            "path": str(db_path),
        }

    age_hours = (time.time() - db_path.stat().st_mtime) / 3600

    try:
        df = pd.read_parquet(db_path)
    except Exception as e:
        return {
            "valid": False,
            "message": f"Parquet DB is unreadable: {e}",
            "path": str(db_path),
            "age_hours": round(age_hours, 1),
        }

    present = set(df.columns)
    missing = EXPECTED_COLUMNS - present

    return {
        "valid": len(missing) == 0,
        "path": str(db_path),
        "row_count": len(df),
        "column_count": len(df.columns),
        "expected_columns_present": list(EXPECTED_COLUMNS & present),
        "missing_columns": list(missing),
        "age_hours": round(age_hours, 1),
        "message": "OK" if not missing else f"Missing expected columns: {missing}",
    }


@mcp.tool(annotations=_tool_annotations("find_duplicates"))
@_tool
def find_duplicates(max_groups: int = 50, refresh_db: bool = False) -> dict[str, Any]:
    """Find exact duplicate files in your library by MD5 hash. Read-only."""
    ap = _get_client()
    if refresh_db:
        ap.photos()

    db = ap.db

    if "md5" not in db.columns:
        return {
            "error": True,
            "code": "SCHEMA_ERROR",
            "message": "md5 column missing. Call check_connection to rebuild.",
        }

    md5_counts = db.groupby("md5").size()
    dupe_md5s = md5_counts[md5_counts > 1]

    if dupe_md5s.empty:
        return {"total_duplicate_files": 0, "removable_copies": 0, "groups": []}

    total_files = int(dupe_md5s.sum())
    removable = int(total_files - len(dupe_md5s))
    dupe_rows = db[db["md5"].isin(dupe_md5s.index)].copy()

    groups: list[dict[str, Any]] = []
    for md5_hash, group_df in dupe_rows.groupby("md5"):
        if len(groups) >= max_groups:
            break
        files: list[dict[str, Any]] = []
        for _, row in group_df.iterrows():
            files.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "folder": row.get("parentMap.FOLDER") if not _is_nan(row.get("parentMap.FOLDER")) else None,
                "createdDate": str(row.get("createdDate")) if not _is_nan(row.get("createdDate")) else None,
                "size": int(row["size"]) if not _is_nan(row.get("size")) else None,
            })
        files.sort(key=lambda f: f["createdDate"] or "")
        groups.append({"md5": str(md5_hash), "count": len(files), "files": files})

    groups.sort(key=lambda g: g["count"], reverse=True)

    return {
        "total_duplicate_files": total_files,
        "removable_copies": removable,
        "total_groups": len(dupe_md5s),
        "groups_shown": len(groups),
        "groups": groups,
    }


@mcp.tool(annotations=_tool_annotations("preview_duplicate_group"))
@_tool
def preview_duplicate_group(md5_hash: str) -> dict[str, Any]:
    """Show all copies of an MD5 hash with full metadata, oldest first."""
    ap = _get_client()
    db = ap.db

    if "md5" not in db.columns:
        return {"error": True, "code": "SCHEMA_ERROR", "message": "md5 column not found in database."}

    group = db[db["md5"] == md5_hash]
    if group.empty:
        return {"error": True, "code": "NOT_FOUND", "message": f"No files found with md5={md5_hash}"}

    records = [_clean_row(r) for r in group.to_dict(orient="records")]
    records.sort(key=lambda r: str(r.get("createdDate") or ""))
    return {
        "md5": md5_hash,
        "count": len(records),
        "recommended_keep": records[0].get("id") if records else None,
        "files": records,
    }


@mcp.tool(annotations=_tool_annotations("find_near_duplicates"))
@_tool
def find_near_duplicates(
    threshold: int = 5,
    max_groups: int = 50,
    sample_size: int = 200,
) -> dict[str, Any]:
    """Find visually similar (near-duplicate) photos using perceptual hashing.

    Downloads a sample of photos, computes pHash, and groups near-duplicates.
    Complements find_duplicates (MD5 exact match). Use this after exact dedup
    to find resized, re-encoded, or slightly edited copies.

    Args:
        threshold: Hamming distance threshold (0-64). Lower = stricter. Default 5.
                   A difference of 1-2 = nearly identical, 5-10 = similar, >10 = different.
        max_groups: Maximum groups to return
        sample_size: Maximum photos to analyze (downloads them temporarily)
    """
    import shutil
    import tempfile

    from amazon_photos_mcp.phash import compute_phash
    from amazon_photos_mcp.phash import find_near_duplicates as _find_near

    ap = _get_client()
    db = ap.db

    # Get a sample of photos from the database
    if db is None or (hasattr(db, "empty") and db.empty):
        return {"status": "no_data", "message": "Database is empty. Run search_photos or check_connection first."}

    # Find image-type rows
    if "contentType" in db.columns:
        photos = db[db["contentType"].str.contains("image", na=False)].head(sample_size)
    else:
        photos = db.head(sample_size)

    if photos.empty:
        return {"status": "no_photos", "message": "No photos found in database."}

    file_hashes: dict[str, str] = {}
    temp_dir = Path(tempfile.mkdtemp(prefix="ap-phash-"))

    try:
        # Download sample to temp dir
        photo_ids = photos["id"].tolist()
        try:
            ap.download(photo_ids, out=str(temp_dir))
        except TypeError:
            original_dir = os.getcwd()
            try:
                os.chdir(str(temp_dir))
                ap.download(photo_ids)
            finally:
                os.chdir(original_dir)

        for f in temp_dir.iterdir():
            if f.is_file():
                phash = compute_phash(f)
                if phash:
                    # Use filename stem as approximate ID mapping
                    file_hashes[f.stem] = phash
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if not file_hashes:
        return {"status": "no_hashes", "message": "Could not compute hashes for any sample photos."}

    groups = _find_near(file_hashes, threshold=threshold)
    groups = sorted(groups, key=lambda g: g["count"], reverse=True)[:max_groups]

    return {
        "sample_size": len(photos),
        "photos_hashed": len(file_hashes),
        "threshold": threshold,
        "groups_found": len(groups),
        "groups": groups,
    }


@mcp.tool(annotations=_tool_annotations("keep_specific"))
@_tool
def keep_specific(keep_id: str, md5_hash: str, dry_run: bool = True) -> dict[str, Any]:
    """Keep a specific copy and trash all other duplicates in an MD5 group."""
    ap = _get_client()
    db = ap.db

    if "md5" not in db.columns:
        return {"error": True, "code": "SCHEMA_ERROR", "message": "md5 column not found in database."}

    group = db[db["md5"] == md5_hash]
    if group.empty:
        return {"error": True, "code": "NOT_FOUND", "message": f"No files found with md5={md5_hash}"}

    trash_ids = [row["id"] for _, row in group.iterrows() if row["id"] != keep_id]

    if not trash_ids:
        return {"status": "nothing_to_do", "message": "Only one copy found or keep_id is not in this group."}

    if dry_run:
        return {
            "action": "dry_run",
            "keep_id": keep_id,
            "trash_ids": trash_ids,
            "message": f"Would trash {len(trash_ids)} copy/copies. Set dry_run=False to execute.",
        }

    ap.trash(trash_ids)
    return {
        "status": "ok",
        "action": "trashed",
        "kept": keep_id,
        "node_ids": trash_ids,
        "count": len(trash_ids),
        "message": f"Trashed {len(trash_ids)} duplicate copy/copies. Recoverable from trash for 30 days.",
    }


@mcp.tool(annotations=_tool_annotations("trash_duplicates"))
@_tool
def trash_duplicates(
    md5_hashes: list[str] | None = None,
    dry_run: bool = True,
    refresh_db: bool = False,
) -> dict[str, Any]:
    """Trash duplicate copies, keeping the oldest of each MD5 group."""
    ap = _get_client()
    if refresh_db:
        ap.photos()

    db = ap.db

    if "md5" not in db.columns:
        return {"error": True, "code": "SCHEMA_ERROR", "message": "md5 column not found in database."}

    md5_counts = db.groupby("md5").size()
    dupe_md5s = set(md5_counts[md5_counts > 1].index)

    if md5_hashes is not None:
        dupe_md5s = dupe_md5s & set(md5_hashes)

    if not dupe_md5s:
        return {
            "action": "dry_run" if dry_run else "trashed",
            "groups_processed": 0,
            "files_trashed": 0,
            "files_kept": 0,
            "node_ids": [],
            "message": "No duplicates found to process.",
        }

    dupe_rows = db[db["md5"].isin(dupe_md5s)].copy()
    trash_ids: list[str] = []
    keep_ids: list[str] = []

    for _, group_df in dupe_rows.groupby("md5"):
        sorted_group = group_df.sort_values("createdDate", ascending=True, na_position="last")
        keep_ids.append(sorted_group.iloc[0]["id"])
        for _, row in sorted_group.iloc[1:].iterrows():
            trash_ids.append(row["id"])

    result: dict[str, Any] = {
        "action": "dry_run" if dry_run else "trashed",
        "groups_processed": len(dupe_md5s),
        "files_kept": len(keep_ids),
        "files_trashed": len(trash_ids),
        "node_ids": trash_ids,
    }

    if dry_run:
        result["message"] = (
            f"Would trash {len(trash_ids)} duplicate copies across {len(dupe_md5s)} groups. "
            "Set dry_run=False to execute."
        )
        sample = db[db["id"].isin(trash_ids[:10])]
        result["sample_trashed"] = [
            {"id": r["id"], "name": r.get("name"), "md5": r.get("md5")}
            for _, r in sample.iterrows()
        ]
    else:
        batch_size = 100
        for i in range(0, len(trash_ids), batch_size):
            ap.trash(trash_ids[i: i + batch_size])
        result["message"] = (
            f"Trashed {len(trash_ids)} duplicate copies. "
            "Items are recoverable from trash for 30 days."
        )

    return result


def main() -> None:
    # Do NOT call _get_client() here — AmazonPhotos.__init__ makes several
    # synchronous API calls that can take minutes on large libraries, causing
    # MCP handshake timeouts. The client is created lazily on first tool call.
    advice = _cookie_advice()
    print(f"[amazon-photos] MCP server starting. {advice}", file=sys.stderr)
    print("[amazon-photos] Call check_connection or refresh_client to verify the Amazon Photos link.", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
