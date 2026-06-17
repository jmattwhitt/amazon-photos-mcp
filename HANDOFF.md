# amazon-photos-mcp Handoff

**Date:** 2026-06-17
**Base commit:** `f48ce26` -> `ab2c84a`
**Tests:** 313 passed, 0 warnings

---

## What Was Done This Session

Hostile code review of the clean-room rewrite (`api.py` + `client.py` decoupling from `amazon-photos` upstream). The review read every file in `amazon_photos_mcp/` and `amazon_photos_mcp/tools/`. Six reported bugs were investigated; all were refuted. Two real crash bugs and one logic bug were found and fixed.

### Fixes Applied

| Commit | File | Fix |
|--------|------|-----|
| `88e8d16` | `duplicates.py:31` | `md5_groups` dedented from 8 to 4 spaces (was dead code inside `if not items:` block after `return`, causing `NameError` at runtime) |
| `88e8d16` | `duplicates.py:217` | `md5_groups_dup` dedented from 8 to 4 spaces (same pattern, same `NameError` crash) |
| `88e8d16` | `media.py:377-418` | `download_library` restructured to group items by date within each batch before downloading |
| `ab2c84a` | `config.py:14,50-58` | `TomlConfigSettingsSource` wired in via `settings_customise_sources` |

### Reported Bugs Investigated (All Refuted)

1. **Missing `download()` method** -- REFUTED. `download()` EXISTS at `api.py:433-463` with matching signature.
2. **`aggregations()` parameter mismatch** -- REFUTED. Method takes `(self, category)`. No caller passes `out=""`.
3. **`_is_nan` import failure** -- REFUTED. `media.py:348` imports from `amazon_photos_mcp.utils` (correct path).
4. **Bare names in `connection.py`** -- REFUTED. All references use `mod_client.` prefix.
5. **`usage.json()` in `connection.py`** -- REFUTED. No `usage.json()` call exists in the file.
6. **`usage.json()` in `storage.py`** -- REFUTED. No `usage.json()` call exists in the file.

---

## Current Architecture

```
amazon_photos_mcp/
+-- __init__.py        Tool module imports + main() entry point
+-- api.py             NEW - AmazonPhotosClient (curl_cffi, no upstream dep)
+-- client.py          NEW - Client lifecycle, _get_client(), cookie mgmt
+-- config.py          TOML + env config (TomlConfigSettingsSource now wired)
+-- server.py          FastMCP instance + tool annotation sets
+-- decorators.py      @_tool error-handling decorator
+-- errors.py          Custom exceptions
+-- logging.py         Structured logging, timed_tool decorator
+-- crypto.py          AES-256-GCM cookie encryption
+-- phash.py           Perceptual hashing
+-- rate_limiter.py    Token bucket + circuit breaker
+-- utils.py           _is_nan, _clean_row, _safe_df_to_list, etc.
+-- tools/
    +-- __init__.py     Re-export hub
    +-- connection.py   Connection health tools
    +-- storage.py      Storage usage + aggregations
    +-- search.py       Search + browse tools
    +-- media.py        Download, thumbnails, EXIF (date-org bug fixed)
    +-- albums.py       Album CRUD
    +-- folders.py      Folder listing
    +-- people.py       Face cluster management
    +-- favorites_hidden.py  Favorite/hide tools
    +-- trash.py        Trash management
    +-- upload.py       File upload
    +-- duplicates.py   Duplicate detection (NameError crashes fixed)
    +-- library.py      Library health, export, timeline gaps
```

---

## Known Remaining Issues

| Issue | Severity | Status |
|-------|----------|--------|
| connection.py:61 dead hasattr(result, "status_code") check | Minor | Fixed (`3470058`) -- removed; catches AuthenticationError explicitly |
| validate_cookies fragile string matching | Minor | Fixed (`3470058`) -- explicit except AuthenticationError |
| utils.py _safe_df_to_result duplicated guard clauses | Minor | Fixed (`0c1d1c8`) -- delegates DataFrame path to _safe_df_to_list |
| No test coverage for find_duplicates non-empty path | Medium | Unfixed -- no regression test added |
| No test coverage for download_library date org | Medium | Unfixed -- no regression test added |
| rate_limiter hardcodes rate/capacity | Low | Pre-existing |

---

## Test Suite

313 passed in ~2.1s, 0 warnings.

Run: `uv run pytest tests/`

---

## Open Questions

1. **download_library batch retry safety**: When a date group fails mid-batch, remaining items in that batch are skipped. Acceptable?
2. **curl_cffi ARM compat**: May need platform-specific extras for Apple Silicon / Raspberry Pi.
3. **Rate limiter config**: Now works via both env vars and TOML file.
