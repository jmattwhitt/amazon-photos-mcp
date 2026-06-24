# Amazon Photos MCP — Project CLAUDE.md

## Environment

- **Python:** 3.10+ (3.12 in dev). Always use the project venv: `uv run <command>`.
- **Test runner:** `uv run pytest` (431 tests, ~4s)
- **Linter:** `uv run ruff check .` (line length 120)
- **Type checker:** `uv run mypy amazon_photos_mcp/` (strict mode)
- **Formatting:** ruff for isort + basic lint; no black configured yet.

## Commit Discipline

**Tests and lint must pass before every commit.** A git pre-commit hook at
`.githooks/pre-commit` runs `ruff check . && pytest -q` automatically.
Set it up after cloning:

    git config core.hooksPath .githooks

A Claude Code PreToolUse hook in `.claude/settings.local.json` provides
the same enforcement when committing through Claude. Never bypass with
`--no-verify`.

Commit messages: imperative mood, <=72 char subject, body wraps at 72.
Co-authored-by trailer is auto-appended.

## Architecture

```
amazon_photos_mcp/
|__ __init__.py      # FastMCP server, _get_client, _tool decorator, helpers
|__ config.py        # TOML + env var config system
|__ crypto.py        # AES-256-GCM cookie encryption
|__ logging.py       # Structured logging, timed_tool decorator
|__ phash.py         # Perceptual hashing for near-duplicate detection
|__ rate_limiter.py  # Token-bucket rate limiter
|__ tools/
    |__ albums.py          # Album CRUD
    |__ connection.py      # check_connection, refresh_client, validate_cookies
    |__ duplicates.py      # Exact + near-duplicate detection and cleanup
    |__ favorites_hidden.py
    |__ folders.py
    |__ library.py         # DB integrity, stats, export, timeline gaps
    |__ media.py           # Download, thumbnails, EXIF, progress
    |__ people.py          # Face cluster management
    |__ search.py          # Query, date, things, person, advanced search
    |__ storage.py         # Usage and aggregations
    |__ trash.py
    |__ upload.py
```

### Client layer

### Client layer

The library features a fully independent, clean-room native implementation of the Amazon Photos API.

- `api.py` — `AmazonPhotosClient` wraps `curl_cffi.requests.Session` with browser TLS
  fingerprint impersonation, request retry (3x exponential backoff + jitter), and
  structured error handling (401 → `AuthenticationError`, 429/503 → `RateLimitError`).
- `client.py` — `_load_cookies()` reads encrypted cookies; `_get_client()` lazily
  creates + caches the `AmazonPhotosClient` singleton; `_wrap_http_errors()` patches
  the curl_cffi session with rate limiting and circuit-breaker guards.
- `rate_limiter.py` — Token-bucket (5 req/s, burst 10) + sliding-window circuit
  breaker (opens for 30s after 5 failures in 60s).

### Key patterns

- Tool functions are synchronous. `@mcp.tool()` registers them; `@_tool` wraps them
  in error handling that produces structured error dicts.
- Every tool calls `_get_client()` which lazily creates + caches the AmazonPhotos
  client. Call `_get_client(force_refresh=True)` to invalidate the cache.
- Response helpers: `_safe_df_to_list()` (returns list) and `_safe_df_to_result()`
  (returns dict with `items`, `has_more`, `total`).

## Testing

### Autouse fixture trap

`conftest.py` has an autouse fixture that patches `amazon_photos_mcp._client` with
`mock_ap`. **This mock is destroyed by `_get_client(force_refresh=True)`** (line
244 of `__init__.py`), which sets `_client = None` before trying to create a real
client.

Tests that trigger `force_refresh` (e.g., `refresh_client`) must also mock
`_load_cookies` and `AmazonPhotos`, or patch `_get_client` at the call site:

```python
def test_using_force_refresh(self, mock_ap):
    with (
        patch("amazon_photos_mcp._load_cookies",
              return_value={"ubid-main": "x", "at-main": "x", "session-id": "x"}),
        patch("amazon_photos.AmazonPhotos", return_value=mock_ap),
    ):
        result = mod.refresh_client()
```

### Test organization

- `tests/test_tools.py` — main functional tests (~170 tests)
- `tests/test_utils.py` — unit tests for helpers, decorators, crypto, phash
- `tests/test_integration.py` — MCP protocol-layer tests (async, FastMCP schema)
- `tests/test_*_new.py` — focused tests for newer features (duplicates, media, search)
- `tests/smoke/` — headless inspector smoke tests with their own conftest

## Memory

Project memories live at `~/.claude/projects/C--AI-code-amazon-photos-mcp/memory/`:
- `code-review-2026-06-07.md` — 7 bugs found and fixed in June 2026 review
- `code-review-2026-06-17.md` — 21 findings: resilience, error handling, test coverage, curl-cffi
- `test-architecture.md` — autouse fixture trap details
- `upstream-library-internals.md` — verified internals of the pinned library
