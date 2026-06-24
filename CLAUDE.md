# Amazon Photos MCP — Project CLAUDE.md

## Environment

- **Python:** 3.10+ (3.12 in dev). Always use the project venv: `uv run <command>`.
- **Test runner:** `uv run pytest`
- **Linter:** `uv run ruff check .` (line length 120)
- **Type checker:** `uv run mypy amazon_photos_mcp/` (strict mode)
- **Formatting:** `uv run ruff format .`

## Commit Discipline

Tests and lint must pass before every commit:

    uv run ruff check . && uv run ruff format --check . && uv run pytest -q

A git pre-commit hook at `.githooks/pre-commit` enforces this automatically.
Set it up after cloning:

    git config core.hooksPath .githooks

Commit messages: imperative mood, <=72 char subject, body wraps at 72.

## Architecture

```
amazon_photos_mcp/
├── __init__.py          # FastMCP server, _get_client, _tool decorator
├── api.py               # AmazonPhotosClient (curl_cffi, retry, rate limiting)
├── client.py            # Client lifecycle, cookie management
├── config.py            # TOML + env var config system
├── crypto.py            # AES-256-GCM cookie encryption
├── decorators.py        # @_tool error-handling decorator
├── errors.py            # Custom exceptions
├── logging.py           # Structured logging, timed_tool decorator
├── phash.py             # Perceptual hashing for near-duplicate detection
├── rate_limiter.py      # Token-bucket rate limiter + circuit breaker
├── utils.py             # Data cleaning and response helpers
├── prompts.py           # MCP prompt definitions
├── resources.py         # MCP resource definitions
├── server.py            # FastMCP instance + tool annotation sets
└── tools/
    ├── albums.py        # Album CRUD
    ├── connection.py    # Connection health, cookie validation
    ├── duplicates.py    # Exact + near-duplicate detection and cleanup
    ├── favorites_hidden.py
    ├── folders.py       # Folder listing and tree display
    ├── library.py       # Stats, export, timeline gap detection
    ├── media.py         # Download, thumbnails, EXIF, progress
    ├── people.py        # Face cluster management
    ├── search.py        # Query, date, things, person, advanced search
    ├── storage.py       # Storage usage and aggregations
    ├── trash.py         # Trash management
    ├── upload.py        # File upload
    └── vision.py        # Vision and image extraction
```

### Client layer

- `api.py` — `AmazonPhotosClient` wraps `curl_cffi.requests.AsyncSession` with browser TLS
  fingerprint impersonation, request retry (exponential backoff + jitter), and
  structured error handling.
- `client.py` — `_load_cookies()` reads encrypted cookies; `_get_client()` lazily
  creates and caches the `AmazonPhotosClient` singleton.
- `rate_limiter.py` — Token-bucket (configurable rate/capacity) + sliding-window circuit
  breaker.

### Key patterns

- Tool functions are async. `@mcp.tool()` registers them; `@_tool` wraps them
  in error handling that produces structured error dicts.
- Every tool calls `_get_client()` which lazily creates and caches the AmazonPhotos
  client. Call `_get_client(force_refresh=True)` to invalidate the cache.
- Response helpers: `_safe_df_to_list()` (returns list) and `_safe_df_to_result()`
  (returns dict with `items`, `has_more`, `total`).

## Testing

### Autouse fixture

`conftest.py` has an autouse fixture that patches `amazon_photos_mcp.client._client`
with a mock client. Tests that call `_get_client(force_refresh=True)` must also mock
`_load_cookies` and `AmazonPhotosClient`, or patch `_get_client` at the call site.

### Test organization

- `tests/test_tools.py` — main functional tests
- `tests/test_utils.py` — unit tests for helpers, decorators, crypto, phash
- `tests/test_integration.py` — MCP protocol-layer tests
- `tests/test_*_new.py` — focused tests for newer features
- `tests/smoke/` — headless smoke tests
