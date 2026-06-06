"""FastMCP Amazon Photos Server — search, browse, and manage your Amazon Photos library."""

from __future__ import annotations

import functools
import json
import os
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import pandas as pd
from fastmcp import FastMCP

mcp = FastMCP("amazon-photos")

# ---------------------------------------------------------------------------
# Tool annotations per MCP 2025-11-25 spec
# ---------------------------------------------------------------------------
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
    "get_library_stats",
    "export_metadata",
    "find_timeline_gaps",
    "get_thumbnail",
    "get_download_progress",
    "advanced_search",
})

_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "permanently_delete", "trash_items", "trash_duplicates",
    "trash_near_duplicates",
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


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Cookie management
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Tool error-handling decorator
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------
_client_lock = threading.Lock()
_stdout_lock = threading.Lock()
_client: Any = None


def _normalize_cookies(raw: dict[str, Any]) -> dict[str, Any]:
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

        if not db_path_obj.exists():
            import pandas as pd
            pd.DataFrame().to_parquet(db_path_obj)

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

        _configure_http_pooling(_client)
        _wrap_http_errors(_client)

        return _client


def _configure_http_pooling(client: Any) -> None:
    """Enable connection pooling on the httpx session for reduced latency."""
    if hasattr(client, "_session"):
        session = client._session
        if hasattr(session, "_transport") and hasattr(session._transport, "_pool"):
            pool = session._transport._pool
            pool._keepalive_expiry = 30.0
            pool._max_keepalive_connections = 5
            pool._max_connections = 10


def _wrap_http_errors(client: Any) -> None:
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


# ---------------------------------------------------------------------------
# Data cleaning helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Import tool modules — must happen after mcp & helpers are defined above
# so that @mcp.tool() decorators can reference the singleton.
# ---------------------------------------------------------------------------
from amazon_photos_mcp.tools import (  # noqa: E402, F401 — intentional late import
    add_to_album,
    advanced_search,
    check_connection,
    check_db_integrity,
    create_album,
    download,
    download_by_date,
    download_files,
    download_for_pipeline,
    download_library,
    export_metadata,
    favorite_items,
    find_duplicates,
    find_near_duplicates,
    find_timeline_gaps,
    get_aggregations,
    get_download_progress,
    get_exif_data,
    get_folder_tree,
    get_library_stats,
    get_photos,
    get_photo_url,
    get_storage_usage,
    get_thumbnail,
    get_videos,
    hide_items,
    keep_specific,
    list_albums,
    list_folders,
    list_people,
    list_recently_deleted,
    list_trashed,
    merge_people,
    name_person,
    permanently_delete,
    preview_duplicate_group,
    refresh_client,
    remove_from_album,
    restore_items,
    search_by_date,
    search_by_person,
    search_by_things,
    search_photos,
    set_favorite,
    set_hidden,
    trash_duplicates,
    trash_items,
    trash_near_duplicates,
    unfavorite_items,
    unhide_items,
    upload_file,
    upload_folder,
    validate_cookies,
)


def main() -> None:
    # Do NOT call _get_client() here — AmazonPhotos.__init__ makes several
    # synchronous API calls that can take minutes on large libraries, causing
    # MCP handshake timeouts. The client is created lazily on first tool call.
    from amazon_photos_mcp.logging import get_logger
    log = get_logger()
    advice = _cookie_advice()
    log.info("MCP server starting. %s", advice)
    log.info("Call check_connection or refresh_client to verify the Amazon Photos link.")
    mcp.run()


if __name__ == "__main__":
    main()
