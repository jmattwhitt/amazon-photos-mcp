# amazon-photos-mcp Handoff

**Date:** 2026-06-06
**Base commit:** `8c7c0b0` → `4977381`
**Tests:** 327 passed, 11 integration failures (pre-existing `pytest-asyncio` missing)

---

## What Was Built

This sprint implemented a comprehensive 14-task improvement plan for the Amazon Photos MCP server. The work spanned 3 phases across two implementation sessions with a review-and-fix iteration.

### Phase 1 — Foundation

**Task 1: Modular architecture** — Split the 1456-line monolithic `__init__.py` into 13 focused modules under `amazon_photos_mcp/tools/`. Each module has a single responsibility (connection, search, media, albums, folders, people, favorites/hidden, trash, upload, duplicates, library, storage). The original `__init__.py` retains `FastMCP` singleton, error classes, client lifecycle, cookie management, and data helpers — then re-exports all tools via a late import at the bottom of the file.

**Task 2: Thumbnail/preview** — `get_thumbnail(node_id, max_size)` downloads the full image via httpx, resizes with PIL LANCZOS, returns base64 JPEG. Reuses the client's connection pool. Configurable via `thumbnail_max_size` in config.

**Task 3: Download progress** — `download_library` writes JSON progress per batch (`downloaded/total/percent/elapsed/eta`). `get_download_progress` tool reads it. `dry_run` param counts items without downloading.

**Task 4: Library health** — `get_library_stats` returns content breakdown, date range, size distribution buckets, files-per-month histogram, duplicate count, folder/album/people counts, data quality (missing dates/location), and storage usage vs quota.

**Task 5: Connection pooling** — `_configure_http_pooling()` sets `keepalive_expiry=30s`, `max_keepalive_connections=5`, `max_connections=10` on the httpx session.

### Phase 2 — New Capabilities

**Task 6: Metadata export** — `export_metadata(fmt="json", output_path, include_exif, slim, filter_query)` exports to JSON (year/month buckets, Immich-compatible) or CSV.

**Task 7: Enhanced search** — `advanced_search(content_type, date_from/to, min/max_size, has_location, is_favorite, is_hidden, person, things, sort_by, sort_order)` builds structured Amazon query strings.

**Task 8: Timeline gaps** — `find_timeline_gaps(min_photos_per_month=5)` scans monthly counts, flags empty and low-count months sorted by severity.

**Task 10: Near-duplicate improvements** — `find_near_duplicates` maps downloaded filenames back to node IDs. `trash_near_duplicates` with quality heuristics (JPEG > HEIC, larger file, higher resolution).

### Phase 3 — Platform & DX

**Task 11: Docker** — Multi-stage Dockerfile (`python:3.12-slim`, uv sync, non-root `mcp` user). `docker-compose.yml` with cookie volume mount.

**Task 12: Logging** — `amazon_photos_mcp/logging.py` with `AMAZON_PHOTOS_LOG_LEVEL`/`AMAZON_PHOTOS_LOG_FILE` env vars. `timed_tool` decorator for performance instrumentation.

**Task 13: README** — Architecture diagram (mermaid), full tool reference tables, Docker config, migration guide (Amazon Photos → Immich).

**Task 14: Config file** — `~/.config/amazon-photos-mcp/config.toml` with env var precedence. Keys: `log_level`, `log_file`, `rate_limit`, `rate_capacity`, `download_default_max`, `download_library_max`, `thumbnail_max_size`.

### Review Iteration Fixes

After the initial implementation, a Critic review found 13 issues. All actionable items were fixed:
- **CRITICAL:** Fixed `advanced_search` date range query (was producing malformed `createdDate:[X createdDate:Y]` instead of `createdDate:[X TO Y]`)
- Fixed `timed_tool` unreachable except handler
- Fixed `get_thumbnail` session reuse (now uses client pool instead of new httpx connection)
- Fixed `download`/`download_library`/`find_near_duplicates` overly broad TypeError catch (added `inspect.signature()` guard)
- Fixed `download_library` NaN check (replaced confusing expression with `_is_nan()`)
- Fixed `export_metadata` `format` parameter shadowing built-in (renamed to `fmt`)
- Fixed `get_folder_tree` return type (now returns `dict` like all other tools)
- Removed unused imports from `__init__.py`
- Wired `thumbnail_max_size` config to `get_thumbnail`

---

## Architecture

```
amazon_photos_mcp/
├── __init__.py        FastMCP singleton, error classes, client lifecycle,
│                      cookie mgmt, data helpers, tool re-exports
├── config.py          TOML + env config system
├── logging.py         Structured logging, timed_tool decorator
├── crypto.py          AES-256-GCM cookie encryption (pre-existing)
├── phash.py           Perceptual hashing (pre-existing)
├── rate_limiter.py    Token bucket (pre-existing)
└── tools/
    ├── __init__.py     Re-export hub
    ├── connection.py   check_connection, refresh_client, validate_cookies
    ├── storage.py      get_storage_usage, get_aggregations
    ├── search.py       search_photos, get_photos, get_videos, search_by_date,
    │                   search_by_things, search_by_person, advanced_search
    ├── media.py        get_photo_url, get_exif_data, get_thumbnail, download,
    │                   download_library, get_download_progress, deprecated wrappers
    ├── albums.py       list_albums, create_album, add_to_album, remove_from_album
    ├── folders.py      list_folders, get_folder_tree
    ├── people.py       list_people, name_person, merge_people
    ├── favorites_hidden.py  set_favorite, set_hidden, deprecated wrappers
    ├── trash.py        trash_items, list_trashed, restore_items, permanently_delete
    ├── upload.py       upload_file, upload_folder
    ├── duplicates.py   find_duplicates, find_near_duplicates, preview_duplicate_group,
    │                   keep_specific, trash_duplicates, trash_near_duplicates
    └── library.py      check_db_integrity, get_library_stats, export_metadata,
                        find_timeline_gaps
```

### Decorator pattern

```
@mcp.tool(annotations=_tool_annotations("tool_name"))   # FastMCP registration
@_tool                                                    # error → dict conversion
def tool_name(...) -> dict[str, Any]:
```

`_tool` catches `AuthenticationError`, `RateLimitError`, `ResourceNotFoundError`, and generic `Exception`, converting all to structured `{"error": True, "code": "...", ...}` dicts. The `@mcp.tool()` decorator supplies `readOnlyHint`/`destructiveHint`/`idempotentHint` annotations per MCP 2025-11-25 spec.

---

## Key Design Decisions

1. **Lazy client init:** `_get_client()` monkey-patches `AmazonPhotos.get_root`, `get_folders`, and `build_tree` to return empty values during `__init__`, preventing the upstream library from making blocking API calls that cause MCP handshake timeouts on large libraries. Original methods are restored after init.

2. **Tool annotations:** Three frozen sets in `__init__.py` classify tools as read-only, destructive, or idempotent. New tools must be added to the appropriate set.

3. **Config precedence:** Env var > TOML file > default. `_coerce()` converts string env vars to the type of the default.

4. **Test patching after module split:** Functions that call each other within the same tool module must be patched at the module's namespace (e.g., `patch("amazon_photos_mcp.tools.trash.list_trashed")`), not at the re-export in `__init__.py`.

---

## What's NOT Done (P4 / Future)

| Item | Reason |
|------|--------|
| **Task 9: Album enrichment** | Requires upstream `amazon_photos` library analysis to see if album metadata updates are supported |
| **CI Docker build step** | No `.github/workflows/ci.yml` exists in the repo to modify |
| **Rate limiter config wiring** | `rate_limiter.py` hardcodes `rate=5.0, capacity=10`; config system exposes these keys but the rate limiter doesn't read them |
| **Cookie encryption recovery path** | `load_encrypted_cookies` silently returns `None` on decryption failure; no diagnostic distinguishes "file missing" from "key mismatch" |
| **HTTP timeout configuration** | `_wrap_http_errors` doesn't set a default timeout on the patched session |
| **Test coverage for new tool modules** | Existing tests cover the old monolithic paths; new functions like `advanced_search` query construction, `trash_near_duplicates` quality scoring, and `download_library` batch logic need dedicated tests |

---

## Open Questions

1. Does Amazon Photos query syntax actually use `createdDate:[YYYYMMDD TO YYYYMMDD]`? The fix assumes it does based on the upstream library patterns, but it hasn't been verified against a live API.
2. Does the current pinned commit of `amazon_photos` (685c965b5a4ba1ac85d418820ad200e12c18a46d) support the `out=` parameter on `download()`? If yes, the entire `TypeError`/CWD-change fallback path is dead code.
3. Should `download_library` keep its `idempotentHint = True` annotation? Downloading thousands of files is technically idempotent but retrying it automatically would be wasteful.

---

## Test Suite

```
327 passed, 11 integration failures (pre-existing: pytest-asyncio not installed)
```

The 11 integration test failures are all `async def functions are not natively supported` — they need `pytest-asyncio` installed in the venv. Not caused by this sprint.

Run: `uv run pytest tests/`
