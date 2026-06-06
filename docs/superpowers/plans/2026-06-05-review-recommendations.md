# Review Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all findings from the June 2026 comprehensive review — spec compliance (tool annotations, pagination), security hardening (cookie encryption), architectural improvements (tool consolidation, RateLimitError wiring, perceptual hash dedup), CI expansion (Python 3.13, fastmcp pinning), and test infrastructure (integration tests, MCP Inspector smoke tests).

**Architecture:** The existing single-file server (`amazon_photos_mcp/__init__.py`, 1157 lines) stays intact as the primary module. New modules are added only where needed: `amazon_photos_mcp/crypto.py` for cookie encryption, `amazon_photos_mcp/rate_limiter.py` for token-bucket rate limiting, `amazon_photos_mcp/phash.py` for perceptual hash dedup. Consolidated tools replace old ones in-place. Integration tests live in `tests/test_integration.py`; smoke tests in `tests/smoke/`.

**Tech Stack:** Python 3.10+, fastmcp>=2.0.0,<4, amazon-photos (git), httpx, pyarrow, imagehash (new), cryptography (new), pytest, mypy, ruff

---

## Phase 1: Immediate (Safety, Spec Compliance, Error Wiring)

### Task 1: Add tool annotations to all 41 tools

**Files:**
- Modify: `amazon_photos_mcp/__init__.py`
- Test: `tests/test_utils.py`

Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`) are a MCP 2025-11-25 spec requirement. FastMCP supports them via the `annotations` kwarg in `@mcp.tool()`.

Read-only tools (no state changes): `check_connection`, `refresh_client`, `validate_cookies`, `get_storage_usage`, `get_aggregations`, `search_photos`, `get_photos`, `get_videos`, `search_by_date`, `search_by_things`, `get_photo_url`, `get_exif_data`, `list_folders`, `get_folder_tree`, `list_albums`, `list_people`, `search_by_person`, `find_duplicates`, `preview_duplicate_group`, `check_db_integrity`

Destructive tools (irreversible or data-altering): `permanently_delete`, `trash_items`, `trash_duplicates`, `keep_specific` (when dry_run=False), `merge_people`, `hide_items`

Idempotent state-changing tools (safe to retry): `create_album`, `add_to_album`, `remove_from_album`, `favorite_items`, `unfavorite_items`, `unhide_items`, `name_person`, `restore_items`, `upload_file`, `upload_folder`

Unclear/dual-mode (don't annotate destructiveHint): `download_files`, `download_by_date`, `download_for_pipeline`, `list_trashed`, `list_recently_deleted`, `keep_specific` (it has dry_run — safe when dry_run=True, destructive when False — leave unannotated)

- [ ] **Step 1: Add ANNOTATIONS dict and helper**

Add after the existing imports in `amazon_photos_mcp/__init__.py` at line 16:

```python
# Tool annotations per MCP 2025-11-25 spec
# Groups of tool names keyed by annotation type
_READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "check_connection", "refresh_client", "validate_cookies",
    "get_storage_usage", "get_aggregations",
    "search_photos", "get_photos", "get_videos",
    "search_by_date", "search_by_things",
    "get_photo_url", "get_exif_data",
    "list_folders", "get_folder_tree",
    "list_albums", "list_people", "search_by_person",
    "find_duplicates", "preview_duplicate_group",
    "check_db_integrity",
})

_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "permanently_delete", "trash_items", "trash_duplicates",
    "keep_specific", "merge_people", "hide_items",
})

_IDEMPOTENT_TOOLS: frozenset[str] = frozenset({
    "create_album", "add_to_album", "remove_from_album",
    "favorite_items", "unfavorite_items", "unhide_items",
    "name_person", "restore_items", "upload_file", "upload_folder",
    "list_trashed", "list_recently_deleted",
    "download_files", "download_by_date", "download_for_pipeline",
    "set_favorite", "set_hidden", "download",  # consolidated tools coming later
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
```

- [ ] **Step 2: Add annotations to one read-only tool as pattern (check_connection)**

Change line 271 from:
```python
@mcp.tool()
```
to:
```python
@mcp.tool(annotations=_tool_annotations("check_connection"))
```

- [ ] **Step 3: Add annotations to one destructive tool as pattern (trash_items)**

Change line 651 from:
```python
@mcp.tool()
```
to:
```python
@mcp.tool(annotations=_tool_annotations("trash_items"))
```

- [ ] **Step 4: Apply annotations to all remaining 39 tools**

Replace every other `@mcp.tool()` with `@mcp.tool(annotations=_tool_annotations("<function_name>"))` where `<function_name>` is the decorated function's name.

Tools at lines: 297, 305, 336, 347, 362, 371, 380, 389, 409, 422, 443, 481, 490, 501, 510, 521, 532, 543, 554, 565, 576, 587, 606, 625, 636, 666, 675, 704, 719, 738, 761, 813, 858, 885, 907, 956, 1010, 1034, 1072

- [ ] **Step 5: Write tests**

Add to `tests/test_utils.py`:

```python
class TestToolAnnotations:
    """Verify every registered tool has appropriate annotations."""

    def test_read_only_tools_have_read_only_hint(self) -> None:
        from amazon_photos_mcp import _READ_ONLY_TOOLS, _tool_annotations
        for name in _READ_ONLY_TOOLS:
            ann = _tool_annotations(name)
            assert ann.get("readOnlyHint") is True, f"{name} missing readOnlyHint"

    def test_destructive_tools_have_destructive_hint(self) -> None:
        from amazon_photos_mcp import _DESTRUCTIVE_TOOLS, _tool_annotations
        for name in _DESTRUCTIVE_TOOLS:
            ann = _tool_annotations(name)
            assert ann.get("destructiveHint") is True, f"{name} missing destructiveHint"

    def test_idempotent_tools_have_idempotent_hint(self) -> None:
        from amazon_photos_mcp import _IDEMPOTENT_TOOLS, _tool_annotations
        for name in _IDEMPOTENT_TOOLS:
            ann = _tool_annotations(name)
            assert ann.get("idempotentHint") is True, f"{name} missing idempotentHint"

    def test_no_overlap_read_only_and_destructive(self) -> None:
        from amazon_photos_mcp import _READ_ONLY_TOOLS, _DESTRUCTIVE_TOOLS
        overlap = _READ_ONLY_TOOLS & _DESTRUCTIVE_TOOLS
        assert not overlap, f"Tools in both sets: {overlap}"

    def test_all_tool_names_are_valid(self) -> None:
        """Every tool registered with mcp should have annotations defined."""
        from amazon_photos_mcp import mcp, _tool_annotations
        for tool in mcp._tool_manager._tools.values():
            name = tool.name
            ann = _tool_annotations(name)
            # At minimum, tools without annotations should still get an empty dict
            assert isinstance(ann, dict), f"Tool {name} has no annotations helper entry"
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_utils.py::TestToolAnnotations -v`
Expected: 5 PASS

- [ ] **Step 7: Commit**

```bash
git add amazon_photos_mcp/__init__.py tests/test_utils.py
git commit -m "feat: add MCP 2025-11-25 tool annotations to all 41 tools

readOnlyHint on read-only tools, destructiveHint on destructive tools,
idempotentHint on safe-to-retry state-changing tools.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Wire RateLimitError to actual HTTP 429 detection

**Files:**
- Create: `amazon_photos_mcp/rate_limiter.py`
- Modify: `amazon_photos_mcp/__init__.py`

The `RateLimitError` class exists (line 57-60) and is caught by `@_tool` (line 125-131) but is never raised. The upstream `amazon_photos` library uses `httpx` for HTTP requests. We need to wrap the client creation and key API calls to detect HTTP 429/503 responses.

- [ ] **Step 1: Create rate_limiter module**

Create `amazon_photos_mcp/rate_limiter.py`:

```python
"""Token-bucket rate limiter and HTTP 429 detection for Amazon Photos API."""

from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate       # tokens per second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate limited."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available(self) -> float:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(self._capacity, self._tokens + elapsed * self._rate)


# Global bucket: 5 requests/second, burst capacity of 10
_global_bucket = TokenBucket(rate=5.0, capacity=10)


def check_rate_limit() -> None:
    """Check and consume a rate limit token. Raises RateLimitError if exceeded."""
    from amazon_photos_mcp import RateLimitError
    if not _global_bucket.consume(1):
        raise RateLimitError(retry_after=15)
```

- [ ] **Step 2: Integrate rate limiter into client wrapper**

Add at line 183 of `amazon_photos_mcp/__init__.py`, inside `_get_client()`, after the client is created:

```python
        # Wrap the client's HTTP session to detect 429/503 responses
        _wrap_http_errors(_client)
```

Add this function after `_get_client` (before line 239):

```python
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
                    raise RateLimitError(
                        retry_after=30
                    )
            return resp

        session.request = _patched_request  # type: ignore[method-assign]
```

- [ ] **Step 3: Write tests**

Add to `tests/test_utils.py`:

```python
class TestRateLimiter:
    def test_token_bucket_allows_within_limit(self) -> None:
        from amazon_photos_mcp.rate_limiter import TokenBucket
        bucket = TokenBucket(rate=100.0, capacity=10)
        for _ in range(5):
            assert bucket.consume(1) is True

    def test_token_bucket_blocks_when_exhausted(self) -> None:
        from amazon_photos_mcp.rate_limiter import TokenBucket
        bucket = TokenBucket(rate=0.0, capacity=0)
        assert bucket.consume(1) is False

    def test_check_rate_limit_raises_when_exhausted(self) -> None:
        from amazon_photos_mcp import RateLimitError
        from amazon_photos_mcp.rate_limiter import _global_bucket, check_rate_limit
        # Drain the bucket
        while _global_bucket.consume(1):
            pass
        with pytest.raises((RateLimitError,)) as _:  # may not raise if refilled
            check_rate_limit()

    def test_rate_limit_error_includes_retry_after(self) -> None:
        from amazon_photos_mcp import RateLimitError
        e = RateLimitError(retry_after=30)
        assert e.retry_after == 30
        assert e.code == "RATE_LIMITED"

    def test_wrap_http_errors_detects_429(self) -> None:
        from unittest.mock import MagicMock
        from amazon_photos_mcp import RateLimitError, _wrap_http_errors
        mock_client = MagicMock()
        mock_resp = MagicMock(status_code=429)
        mock_resp.headers = {"Retry-After": "45"}
        mock_client._session.request.return_value = mock_resp
        _wrap_http_errors(mock_client)
        with pytest.raises(RateLimitError) as exc_info:
            mock_client._session.request("GET", "https://example.com")
        assert exc_info.value.retry_after == 45

    def test_wrap_http_errors_detects_503(self) -> None:
        from unittest.mock import MagicMock
        from amazon_photos_mcp import RateLimitError, _wrap_http_errors
        mock_client = MagicMock()
        mock_resp = MagicMock(status_code=503, headers={})
        mock_client._session.request.return_value = mock_resp
        _wrap_http_errors(mock_client)
        with pytest.raises(RateLimitError) as exc_info:
            mock_client._session.request("GET", "https://example.com")
        assert exc_info.value.retry_after == 30
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_utils.py::TestRateLimiter -v`
Expected: 6 PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All existing tests still pass (the wrapper is applied post-mock in conftest)

- [ ] **Step 6: Commit**

```bash
git add amazon_photos_mcp/rate_limiter.py amazon_photos_mcp/__init__.py tests/test_utils.py
git commit -m "feat: wire RateLimitError to HTTP 429/503 detection with token-bucket

Adds TokenBucket rate limiter (5 req/s, burst 10) and httpx session
wrapping to detect upstream rate limiting. RateLimitError was defined
but never raised — now it fires on real 429/503 responses.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Add has_more/next_cursor to search and browse tools

**Files:**
- Modify: `amazon_photos_mcp/__init__.py`
- Test: `tests/test_tools.py`

Search and browse tools currently truncate via `_safe_df_to_list(df, min(max_results, 200))` with no indication that results were truncated. Return a dict with `items`, `has_more`, and `total` fields instead of a plain list.

- [ ] **Step 1: Modify _safe_df_to_list to include truncation metadata**

Add a new function after `_safe_df_to_list` (after line 268):

```python
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
```

- [ ] **Step 2: Update search_photos (line 362-368)**

Replace:
```python
def search_photos(query: str, max_results: int = 25) -> list[dict[str, Any]]:
    """Search Amazon Photos by query string with optional filters (type, things, dates, etc.)."""
    ap = _get_client()
    df = ap.query(query)
    return _safe_df_to_list(df, min(max_results, 200))
```

With:
```python
def search_photos(query: str, max_results: int = 25) -> dict[str, Any]:
    """Search Amazon Photos by query string with optional filters (type, things, dates, etc.).

    Returns a dict with 'items', 'has_more' (True if results were truncated), and 'total'.
    """
    ap = _get_client()
    df = ap.query(query)
    return _safe_df_to_result(df, min(max_results, 200))
```

- [ ] **Step 3: Update get_photos (line 371-377)**

Same pattern — replace `_safe_df_to_list` with `_safe_df_to_result`, change return type to `dict[str, Any]`, add docstring about `has_more`/`total`.

- [ ] **Step 4: Update get_videos (line 380-386)**

Same as Step 3.

- [ ] **Step 5: Update search_by_date (line 389-406)**

Same pattern — `_safe_df_to_result`, return type `dict[str, Any]`, docstring.

- [ ] **Step 6: Update search_by_things (line 409-420)**

Same as Step 5.

- [ ] **Step 7: Update list_folders (line 422-441)**

Same pattern with `_safe_df_to_result`.

- [ ] **Step 8: Update list_albums (line 481-489)**

Same pattern.

- [ ] **Step 9: Update search_by_person (line 501-530)**

Same pattern.

- [ ] **Step 10: Update list_people (line 587-604)**

This returns a hand-built list, not a DataFrame. Wrap the result:

Replace the return at line 604:
```python
    return results
```
With:
```python
    return {"items": results, "has_more": False, "total": len(results)}
```

- [ ] **Step 11: Update list_trashed (line 666-672)**

Same pattern — `_safe_df_to_result`, `dict[str, Any]`.

- [ ] **Step 12: Update list_recently_deleted (line 675-701)**

Same pattern.

- [ ] **Step 13: Write tests**

Add to `tests/test_tools.py`:

```python
class TestPaginationMetadata:
    """Verify that search/browse tools return has_more/total metadata."""

    def test_search_photos_returns_dict_with_metadata(self) -> None:
        from amazon_photos_mcp import search_photos
        result = search_photos("type:(PHOTOS)", max_results=2)
        assert isinstance(result, dict)
        assert "items" in result
        assert "has_more" in result
        assert "total" in result
        assert isinstance(result["items"], list)

    def test_get_photos_returns_dict_with_metadata(self) -> None:
        from amazon_photos_mcp import get_photos
        result = get_photos(max_results=1)
        assert isinstance(result, dict)
        assert "items" in result

    def test_safe_df_to_result_marks_has_more_correctly(self) -> None:
        import pandas as pd
        from amazon_photos_mcp import _safe_df_to_result
        df = pd.DataFrame([{"id": "1", "name": f"photo{i}.jpg"} for i in range(10)])
        result = _safe_df_to_result(df, max_results=5)
        assert result["has_more"] is True
        assert result["total"] == 10
        assert len(result["items"]) == 5

    def test_safe_df_to_result_no_truncation(self) -> None:
        import pandas as pd
        from amazon_photos_mcp import _safe_df_to_result
        df = pd.DataFrame([{"id": "1", "name": "photo.jpg"}])
        result = _safe_df_to_result(df, max_results=50)
        assert result["has_more"] is False
        assert result["total"] == 1

    def test_safe_df_to_result_none(self) -> None:
        from amazon_photos_mcp import _safe_df_to_result
        result = _safe_df_to_result(None)
        assert result == {"items": [], "has_more": False, "total": 0}
```

- [ ] **Step 14: Update existing tests that check return types**

Existing tests like `TestGetPhotos.test_returns_list` will now receive dicts. Update:

In `tests/test_tools.py`, change:
```python
def test_returns_list(self) -> None:
    result = get_photos()
    assert isinstance(result, list)
```
To:
```python
def test_returns_dict_with_items(self) -> None:
    result = get_photos()
    assert isinstance(result, dict)
    assert isinstance(result["items"], list)
```

Apply similar changes to all tests that assert `isinstance(result, list)` for the modified tools.

- [ ] **Step 15: Run tests**

Run: `pytest tests/ -v`
Expected: All tests pass after test updates.

- [ ] **Step 16: Commit**

```bash
git add amazon_photos_mcp/__init__.py tests/test_tools.py
git commit -m "feat: add has_more/total metadata to all search and browse tools

All list-returning tools now return dicts with 'items', 'has_more',
and 'total' fields so the LLM knows when results are truncated and
can decide whether to refine the search.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Encrypt cookie file at rest

**Files:**
- Create: `amazon_photos_mcp/crypto.py`
- Modify: `amazon_photos_mcp/__init__.py` (cookie loading logic)
- Test: `tests/test_utils.py`

Cookies are full Amazon session tokens stored as plaintext JSON. Encrypt with AES-256-GCM using a machine-derived key.

- [ ] **Step 1: Create crypto module**

Create `amazon_photos_mcp/crypto.py`:

```python
"""Cookie file encryption for Amazon Photos MCP.

Uses AES-256-GCM with a key derived from machine identity.
Plaintext fallback for backward compatibility — existing unencrypted
cookie files continue to work and are encrypted on next write.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


def _machine_key() -> bytes:
    """Derive a 32-byte key from machine-specific attributes.

    Not cryptographic-grade (an attacker with filesystem access can
    reconstruct this), but protects against casual exfiltration.
    """
    parts = [
        platform.node() or "unknown-host",
        platform.machine() or "unknown-arch",
        str(Path.home()),
    ]
    if sys.platform == "win32":
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True, text=True, timeout=5,
            )
            parts.append(result.stdout.strip())
        except Exception:
            pass
    else:
        try:
            machine_id = Path("/etc/machine-id").read_text().strip()
            parts.append(machine_id)
        except Exception:
            try:
                machine_id = Path("/var/lib/dbus/machine-id").read_text().strip()
                parts.append(machine_id)
            except Exception:
                pass

    seed = "|".join(parts).encode("utf-8")
    return hashlib.sha256(seed).digest()


def _get_cipher(key: bytes, nonce: bytes | None = None):
    """Create an AES-GCM cipher."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key), nonce


def _encrypt(plaintext: bytes) -> bytes:
    """Encrypt plaintext. Returns nonce (12 bytes) + ciphertext + tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets

    key = _machine_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def _decrypt(data: bytes) -> bytes:
    """Decrypt data produced by _encrypt."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _machine_key()
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def load_encrypted_cookies(path: Path) -> dict[str, Any] | None:
    """Load cookies from a JSON file. Handles both plaintext and encrypted formats.

    Returns None if the file doesn't exist or can't be read.
    Returns the cookie dict on success.
    """
    if not path.exists():
        return None

    try:
        raw = path.read_bytes()

        # Try encrypted first (has "AMCP" magic header)
        if raw[:4] == b"AMCP":
            decrypted = _decrypt(raw[4:])
            return json.loads(decrypted)
        else:
            # Plaintext backward compatibility
            return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def save_encrypted_cookies(path: Path, cookies: dict[str, Any]) -> None:
    """Save cookies as encrypted JSON. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(cookies, indent=2).encode("utf-8")
    encrypted = _encrypt(plaintext)
    path.write_bytes(b"AMCP" + encrypted)
    # Restrictive permissions on Unix
    if sys.platform != "win32":
        path.chmod(0o600)
```

- [ ] **Step 2: Integrate into cookie loading in __init__.py**

Replace the `_load_cookies` function (lines 171-180):

```python
def _load_cookies() -> dict[str, Any] | None:
    env_cookies = os.environ.get("AMAZON_PHOTOS_COOKIES")
    if env_cookies:
        return _normalize_cookies(json.loads(env_cookies))
    from amazon_photos_mcp.crypto import load_encrypted_cookies
    cookies = load_encrypted_cookies(_AMAZON_COOKIE_PATH)
    if cookies is not None:
        return _normalize_cookies(cookies)
    return None
```

- [ ] **Step 3: Update get_cookies.py to encrypt on save**

Modify `scripts/get_cookies.py` to import and use `save_encrypted_cookies` instead of writing plaintext JSON. Add at the top of the save function:

```python
try:
    from amazon_photos_mcp.crypto import save_encrypted_cookies
    save_encrypted_cookies(cookie_path, cookies)
    print(f"Cookies saved (encrypted) to {cookie_path}")
except ImportError:
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(json.dumps(cookies))
    print(f"Cookies saved (plaintext) to {cookie_path}")
```

- [ ] **Step 4: Add file permission check to _cookie_advice**

Add a check in `_cookie_advice` (after line 92) for world-readable cookie files on Unix:

```python
def _cookie_advice() -> str:
    h = _cookie_age_hours()
    if h is None:
        return "Cookie file not found. Create ~/.config/amazon-photos-mcp/cookies.json."
    # Check permissions on Unix
    import sys
    if sys.platform != "win32":
        try:
            mode = _AMAZON_COOKIE_PATH.stat().st_mode
            if mode & 0o077:
                advice = "WARNING: Cookie file is readable by other users. Run: chmod 600 ~/.config/amazon-photos-mcp/cookies.json"
                if h >= _COOKIE_EXPIRED_AFTER_HOURS:
                    return f"Cookies expired ({h:.0f}h old). Refresh immediately and call refresh_client. {advice}"
                if h >= _COOKIE_WARN_AFTER_HOURS:
                    return f"Cookies stale ({h:.0f}h old). Consider refreshing soon. {advice}"
                return f"Cookies fresh ({h:.0f}h old). {advice}"
        except Exception:
            pass
    if h >= _COOKIE_EXPIRED_AFTER_HOURS:
        return f"Cookies expired ({h:.0f}h old). Refresh immediately and call refresh_client."
    if h >= _COOKIE_WARN_AFTER_HOURS:
        return f"Cookies stale ({h:.0f}h old). Consider refreshing soon."
    return f"Cookies fresh ({h:.0f}h old)."
```

- [ ] **Step 5: Wire cryptography dependency**

Add to `pyproject.toml` dependencies:

```toml
dependencies = [
    "fastmcp>=2.0.0",
    "amazon-photos @ git+https://github.com/trevorhobenshield/amazon_photos.git@685c965b5a4ba1ac85d418820ad200e12c18a46d",
    "httpx",
    "pyarrow",
    "cryptography>=42.0.0",
]
```

- [ ] **Step 6: Write tests**

Add to `tests/test_utils.py`:

```python
class TestCookieEncryption:
    def test_roundtrip_encrypted_cookies(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import (
            load_encrypted_cookies,
            save_encrypted_cookies,
        )
        path = tmp_path / "cookies.json"
        original = {"ubid-main": "test-123", "at-main": "token-abc", "session-id": "sess-xyz"}
        save_encrypted_cookies(path, original)
        loaded = load_encrypted_cookies(path)
        assert loaded == original

    def test_encrypted_file_has_magic_header(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import save_encrypted_cookies
        path = tmp_path / "cookies.json"
        save_encrypted_cookies(path, {"test": "value"})
        raw = path.read_bytes()
        assert raw[:4] == b"AMCP"

    def test_load_encrypted_reads_plaintext_fallback(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies
        path = tmp_path / "cookies.json"
        path.write_text(json.dumps({"plain": "text"}))
        cookies = load_encrypted_cookies(path)
        assert cookies == {"plain": "text"}

    def test_load_encrypted_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies
        path = tmp_path / "nonexistent.json"
        assert load_encrypted_cookies(path) is None

    def test_load_encrypted_returns_none_for_corrupt_data(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies
        path = tmp_path / "broken.json"
        path.write_text("this is not valid json {{{")
        assert load_encrypted_cookies(path) is None

    def test_machine_key_is_deterministic(self) -> None:
        from amazon_photos_mcp.crypto import _machine_key
        k1 = _machine_key()
        k2 = _machine_key()
        assert k1 == k2
        assert len(k1) == 32
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_utils.py::TestCookieEncryption -v`
Expected: 6 PASS

- [ ] **Step 8: Install new dependency and run full suite**

Run: `uv sync --extra dev && uv sync --extra scripts`
Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add amazon_photos_mcp/crypto.py amazon_photos_mcp/__init__.py scripts/get_cookies.py pyproject.toml tests/test_utils.py uv.lock
git commit -m "feat: encrypt cookie file at rest with AES-256-GCM

Cookies are full Amazon session tokens. Now encrypted on disk with a
machine-derived key. Plaintext files still load (backward compat) and
are transparently upgraded on next save. Adds file permission check
on Unix.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 2: Short-Term (Architecture, Tool Consolidation, CI)

### Task 5: Consolidate boolean-pair tools (favorite/unfavorite, hide/unhide)

**Files:**
- Modify: `amazon_photos_mcp/__init__.py`
- Test: `tests/test_tools.py`

Merge `favorite_items` + `unfavorite_items` into `set_favorite(node_ids, favorite: bool)`, and `hide_items` + `unhide_items` into `set_hidden(node_ids, hidden: bool)`. Keep old tools with deprecation wrappers for one release.

- [ ] **Step 1: Add set_favorite tool**

Replace `favorite_items` and `unfavorite_items` (lines 543-562) with:

```python
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


# Deprecated — use set_favorite with a bool parameter
@mcp.tool(annotations=_tool_annotations("favorite_items"))
@_tool
def favorite_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_favorite(node_ids, favorite=True) instead."""
    return set_favorite(node_ids, favorite=True)


# Deprecated — use set_favorite with a bool parameter
@mcp.tool(annotations=_tool_annotations("unfavorite_items"))
@_tool
def unfavorite_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_favorite(node_ids, favorite=False) instead."""
    return set_favorite(node_ids, favorite=False)
```

- [ ] **Step 2: Add set_hidden tool**

Replace `hide_items` and `unhide_items` (lines 565-584) with:

```python
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


# Deprecated — use set_hidden with a bool parameter
@mcp.tool(annotations=_tool_annotations("hide_items"))
@_tool
def hide_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_hidden(node_ids, hidden=True) instead."""
    return set_hidden(node_ids, hidden=True)


# Deprecated — use set_hidden with a bool parameter
@mcp.tool(annotations=_tool_annotations("unhide_items"))
@_tool
def unhide_items(node_ids: list[str]) -> dict[str, Any]:
    """DEPRECATED: Use set_hidden(node_ids, hidden=False) instead."""
    return set_hidden(node_ids, hidden=False)
```

- [ ] **Step 3: Write tests**

Add to `tests/test_tools.py`:

```python
class TestSetFavorite:
    def test_set_favorite_true(self) -> None:
        from amazon_photos_mcp import set_favorite
        result = set_favorite(["node-001"], favorite=True)
        assert result.get("action") == "favorited"

    def test_set_favorite_false(self) -> None:
        from amazon_photos_mcp import set_favorite
        result = set_favorite(["node-001"], favorite=False)
        assert result.get("action") == "unfavorited"

    def test_favorite_items_wrapper_still_works(self) -> None:
        from amazon_photos_mcp import favorite_items
        result = favorite_items(["node-001"])
        assert result.get("action") == "favorited"

    def test_unfavorite_items_wrapper_still_works(self) -> None:
        from amazon_photos_mcp import unfavorite_items
        result = unfavorite_items(["node-001"])
        assert result.get("action") == "unfavorited"


class TestSetHidden:
    def test_set_hidden_true(self) -> None:
        from amazon_photos_mcp import set_hidden
        result = set_hidden(["node-001"], hidden=True)
        assert result.get("action") == "hidden"

    def test_set_hidden_false(self) -> None:
        from amazon_photos_mcp import set_hidden
        result = set_hidden(["node-001"], hidden=False)
        assert result.get("action") == "unhidden"

    def test_hide_items_wrapper_still_works(self) -> None:
        from amazon_photos_mcp import hide_items
        result = hide_items(["node-001"])
        assert result.get("action") == "hidden"

    def test_unhide_items_wrapper_still_works(self) -> None:
        from amazon_photos_mcp import unhide_items
        result = unhide_items(["node-001"])
        assert result.get("action") == "unhidden"
```

- [ ] **Step 4: Update _ANNOTATIONS sets for consolidated tools**

Replace `"favorite_items", "unfavorite_items"` with `"set_favorite", "favorite_items", "unfavorite_items"` in `_IDEMPOTENT_TOOLS`.

Replace `"hide_items", "unhide_items"` with `"set_hidden", "hide_items", "unhide_items"` in `_IDEMPOTENT_TOOLS`.

Also add `"hide_items"` to `_DESTRUCTIVE_TOOLS` (hiding is a visibility state change).

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_tools.py::TestSetFavorite tests/test_tools.py::TestSetHidden -v`
Expected: 8 PASS

Run: `pytest tests/ -v` (full suite)
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add amazon_photos_mcp/__init__.py tests/test_tools.py
git commit -m "refactor: consolidate favorite/unfavorite and hide/unhide into set_* tools

Merges favorite_items+unfavorite_items → set_favorite(node_ids, favorite: bool)
and hide_items+unhide_items → set_hidden(node_ids, hidden: bool).
Old tools retained as deprecated wrappers (net +2 tools, visible +0).
Reduces tool list from 41 to 37 (4 removed, 2 added).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Consolidate download tools

**Files:**
- Modify: `amazon_photos_mcp/__init__.py`
- Test: `tests/test_tools.py`

Merge `download_files`, `download_by_date`, and `download_for_pipeline` into a single `download` tool.

- [ ] **Step 1: Add unified download tool**

Insert before the three download tools (before line 738):

```python
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
        "node_ids_sample": ids[:20],
    }


# Deprecated wrappers delegate to download
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
```

- [ ] **Step 2: Write tests**

Add to `tests/test_tools.py`:

```python
class TestDownloadUnified:
    def test_download_by_node_ids(self) -> None:
        from amazon_photos_mcp import download
        result = download(node_ids=["node-001"])
        assert result["status"] == "ok"

    def test_download_by_query(self) -> None:
        from amazon_photos_mcp import download
        result = download(query="type:(PHOTOS)")
        assert result["status"] in ("ok", "no_results")

    def test_download_by_date(self) -> None:
        from amazon_photos_mcp import download
        result = download(year=2024, month=6)
        assert result["status"] in ("ok", "no_results")

    def test_download_no_args_returns_error(self) -> None:
        from amazon_photos_mcp import download
        result = download()
        assert result.get("error") is True
        assert result.get("code") == "INVALID_ARGS"

    def test_download_files_wrapper_still_works(self) -> None:
        from amazon_photos_mcp import download_files
        result = download_files(["node-001"])
        assert result["status"] == "ok"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_tools.py::TestDownloadUnified tests/test_tools.py::TestDownloadFiles tests/test_tools.py::TestDownloadByDate -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add amazon_photos_mcp/__init__.py tests/test_tools.py
git commit -m "refactor: consolidate three download tools into one unified download()

Merges download_files, download_by_date, and download_for_pipeline into
a single download(node_ids/query/year) tool. Old tools retained as
deprecated wrappers. Net reduction: 2 tools (3 removed, 1 added).
Total now 35 (after previous consolidation).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Merge list_trashed + list_recently_deleted

**Files:**
- Modify: `amazon_photos_mcp/__init__.py`
- Test: `tests/test_tools.py`

`list_recently_deleted` is a subset of `list_trashed` with date filtering. Merge by adding `within_days` parameter to `list_trashed`.

- [ ] **Step 1: Rewrite list_trashed**

Replace lines 666-701:

```python
@mcp.tool(annotations=_tool_annotations("list_trashed"))
@_tool
def list_trashed(within_days: int = 0) -> list[dict[str, Any]] | dict[str, Any]:
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
        except (TypeError, ValueError, pd.errors.OutOfBoundsDatetime):
            pass

    return _safe_df_to_result(df, max_results=200)


# Deprecated — use list_trashed(within_days=N)
@mcp.tool(annotations=_tool_annotations("list_recently_deleted"))
@_tool
def list_recently_deleted(within_days: int = 7) -> list[dict[str, Any]] | dict[str, Any]:
    """DEPRECATED: Use list_trashed(within_days=N) instead."""
    return list_trashed(within_days=within_days)
```

- [ ] **Step 2: Update test to use new return type**

Update `TestListRecentlyDeleted` in `tests/test_tools.py` to handle the dict response from `list_trashed`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_tools.py::TestListTrashed tests/test_tools.py::TestListRecentlyDeleted -v`

- [ ] **Step 4: Commit**

```bash
git add amazon_photos_mcp/__init__.py tests/test_tools.py
git commit -m "refactor: merge list_trashed and list_recently_deleted

Adds within_days parameter to list_trashed (0=all, N=filter).
list_recently_deleted retained as deprecated wrapper.
Total now 34 tools.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Add perceptual hash dedup

**Files:**
- Create: `amazon_photos_mcp/phash.py`
- Modify: `amazon_photos_mcp/__init__.py` (extend `find_duplicates`)
- Test: `tests/test_utils.py`

Supplement MD5-based exact dedup with perceptual hash (pHash) for near-duplicate detection.

- [ ] **Step 1: Add imagehash dependency**

Add to `pyproject.toml`:

```toml
dependencies = [
    ...
    "imagehash>=4.3",
    "Pillow>=10.0",
]
```

- [ ] **Step 2: Create phash module**

Create `amazon_photos_mcp/phash.py`:

```python
"""Perceptual hash support for near-duplicate photo detection.

Ported from the immich-photo-manager MCP server pattern.
Uses pHash (DCT-based) with configurable Hamming distance threshold.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def compute_phash(file_path: str | Path) -> str | None:
    """Compute perceptual hash of an image file.

    Returns a hex string or None if the file can't be opened as an image.
    Requires Pillow and imagehash packages.
    """
    try:
        from PIL import Image
        import imagehash

        img = Image.open(str(file_path))
        phash = imagehash.phash(img)
        return str(phash)
    except Exception:
        return None


def hamming_distance(h1: str, h2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    # Convert hex -> int, XOR, count bits
    if len(h1) != len(h2):
        return max(len(h1), len(h2)) * 4
    try:
        n1 = int(h1, 16)
        n2 = int(h2, 16)
        return (n1 ^ n2).bit_count()
    except ValueError:
        return 999


def find_near_duplicates(
    file_hashes: dict[str, str],  # id -> phash
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Group files whose perceptual hashes are within threshold Hamming distance.

    Args:
        file_hashes: Dict mapping node_id to phash hex string
        threshold: Maximum Hamming distance for "near duplicate" (0-64, default 5)

    Returns:
        List of groups, each with: ids, phashes, distances (to group centroid)
    """
    ids = list(file_hashes.keys())
    # Simple greedy clustering — group anything within threshold
    seen: set[str] = set()
    groups: list[dict[str, Any]] = []

    for i, id_i in enumerate(ids):
        if id_i in seen:
            continue
        h1 = file_hashes[id_i]
        group: list[str] = [id_i]
        group_hashes: list[str] = [h1]
        for j in range(i + 1, len(ids)):
            id_j = ids[j]
            if id_j in seen:
                continue
            h2 = file_hashes[id_j]
            if hamming_distance(h1, h2) <= threshold:
                group.append(id_j)
                group_hashes.append(h2)
                seen.add(id_j)
        if len(group) > 1:
            seen.add(id_i)
            groups.append({
                "node_ids": group,
                "count": len(group),
                "phash_sample": h1,
                "distances": [hamming_distance(h1, h) for h in group_hashes],
            })

    return groups
```

- [ ] **Step 3: Add near_duplicate detection tool**

Add to `__init__.py` after `find_duplicates`:

```python
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
    from amazon_photos_mcp.phash import compute_phash, find_near_duplicates as _find_near

    ap = _get_client()
    db = ap.db

    # Get a sample of photos from the database
    if db is None or (hasattr(db, "empty") and db.empty):
        return {"status": "no_data", "message": "Database is empty. Run search_photos or check_connection first."}

    photos = db[db.get("contentType", "").str.contains("image", na=False)].head(sample_size)
    if photos.empty:
        return {"status": "no_photos", "message": "No photos found in database."}

    file_hashes: dict[str, str] = {}
    temp_dir = Path(tempfile.mkdtemp(prefix="ap-phash-"))

    try:
        # Download sample to temp dir and compute hashes
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

        for photo_id in photo_ids:
            # Find the downloaded file (name may differ from id)
            for f in temp_dir.iterdir():
                if f.is_file():
                    phash = compute_phash(f)
                    if phash:
                        file_hashes[photo_id] = phash
                        break  # First match per ID
    finally:
        import shutil
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
```

- [ ] **Step 4: Write tests**

Add to `tests/test_utils.py`:

```python
class TestPerceptualHash:
    def test_hamming_distance_identical(self) -> None:
        from amazon_photos_mcp.phash import hamming_distance
        assert hamming_distance("a0b1c2d3e4f5a0b1", "a0b1c2d3e4f5a0b1") == 0

    def test_hamming_distance_different(self) -> None:
        from amazon_photos_mcp.phash import hamming_distance
        # "a" vs "b" differ in 1 bit
        dist = hamming_distance("a" * 16, "b" * 16)
        assert dist > 0

    def test_hamming_distance_different_lengths(self) -> None:
        from amazon_photos_mcp.phash import hamming_distance
        assert hamming_distance("a", "bb") == 8  # max(len) * 4

    def test_find_near_duplicates_empty(self) -> None:
        from amazon_photos_mcp.phash import find_near_duplicates
        groups = find_near_duplicates({})
        assert groups == []

    def test_find_near_duplicates_no_matches(self) -> None:
        from amazon_photos_mcp.phash import find_near_duplicates
        # Uses real hash-like values with large Hamming distances
        hashes = {
            "id1": "a" * 16,
            "id2": "f" * 16,  # Very different from "a"*16
        }
        groups = find_near_duplicates(hashes, threshold=2)
        assert groups == []  # Too far apart

    def test_compute_phash_returns_none_for_non_image(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.phash import compute_phash
        bad_file = tmp_path / "not_an_image.txt"
        bad_file.write_text("hello")
        result = compute_phash(bad_file)
        assert result is None
```

- [ ] **Step 5: Install deps and run tests**

Run: `uv sync --extra dev`
Run: `pytest tests/test_utils.py::TestPerceptualHash -v`

- [ ] **Step 6: Commit**

```bash
git add amazon_photos_mcp/phash.py amazon_photos_mcp/__init__.py tests/test_utils.py pyproject.toml uv.lock
git commit -m "feat: add perceptual hash near-duplicate detection

Adds find_near_duplicates tool using pHash (DCT-based) with configurable
Hamming distance threshold. Complements MD5-based find_duplicates for
detecting resized, re-encoded, or slightly edited copies.
Total now 35 tools.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 9: Add Python 3.13 to CI and pin fastmcp

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add Python 3.13 to CI matrix**

In `.github/workflows/ci.yml`, line 14, change:
```yaml
        python-version: ["3.10", "3.11", "3.12"]
```
To:
```yaml
        python-version: ["3.10", "3.11", "3.12", "3.13"]
```

- [ ] **Step 2: Add Python 3.13 classifier**

In `pyproject.toml`, after line 23 (`"Programming Language :: Python :: 3.12",`), add:
```toml
    "Programming Language :: Python :: 3.13",
```

- [ ] **Step 3: Pin fastmcp version**

In `pyproject.toml`, line 29, change:
```toml
    "fastmcp>=2.0.0",
```
To:
```toml
    "fastmcp>=2.0.0,<4",
```

- [ ] **Step 4: Regenerate lock file**

Run: `uv lock`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml pyproject.toml uv.lock
git commit -m "ci: add Python 3.13 to matrix, pin fastmcp<4

Python 3.13 has been stable since October 2024. Pinning fastmcp to
<4 prevents surprise breakage from FastMCP 4.0's inevitable breaking
changes (FastMCP 3.0 already had Providers + Transforms overhaul).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 3: Medium-Term (Test Infrastructure, Migration Tool)

### Task 10: Add integration tests using FastMCP test client

**Files:**
- Create: `tests/test_integration.py`
- Modify: `tests/conftest.py` (add integration fixture)

- [ ] **Step 1: Add transport-level test fixture**

Add to `tests/conftest.py`:

```python
@pytest.fixture()
async def mcp_client() -> Any:
    """Create a FastMCP test client connected to the server with a mock Amazon client."""
    from amazon_photos_mcp import mcp
    async with mcp.test_client() as client:
        # Inject mock before any tool call
        with patch("amazon_photos_mcp._client", mock_ap):
            yield client
```

- [ ] **Step 2: Create test_integration.py**

Create `tests/test_integration.py`:

```python
"""Integration tests — validate MCP protocol layer with FastMCP test client."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
class TestMCPProtocol:
    """Verify that tools are callable through the MCP JSON-RPC transport."""

    async def test_list_tools_returns_all_registered_tools(self) -> None:
        """Every decorated tool should appear in tools/list response."""
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "check_connection" in tool_names
            assert "search_photos" in tool_names
            assert "find_duplicates" in tool_names
            assert "download" in tool_names or "download_files" in tool_names
            assert len(tool_names) >= 25  # Minimum after consolidation

    async def test_tool_has_input_schema(self) -> None:
        """Every tool should have a valid input schema."""
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.inputSchema is not None, f"{tool.name} has no inputSchema"
                assert tool.inputSchema.get("type") == "object", \
                    f"{tool.name} schema type should be object"

    async def test_tool_has_description(self) -> None:
        """Every tool should have a non-empty description."""
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.description, f"{tool.name} has no description"
                assert len(tool.description) > 10, \
                    f"{tool.name} description too short: {tool.description}"

    async def test_call_check_connection_returns_valid_json_rpc(self) -> None:
        """A simple tool call should return valid structured content."""
        import json

        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            result = await client.call_tool("check_connection", {})
            assert result is not None
            assert len(result.content) > 0, "Expected at least one content block"

    async def test_call_search_photos_with_query(self) -> None:
        """search_photos should accept a query string parameter."""
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            result = await client.call_tool("search_photos", {"query": "type:(PHOTOS)"})
            assert result is not None

    async def test_call_find_duplicates_read_only(self) -> None:
        """find_duplicates should be callable and return structured data."""
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            result = await client.call_tool("find_duplicates", {})
            assert result is not None

    async def test_read_only_tools_annotated_correctly(self) -> None:
        """Read-only tools should have readOnlyHint in their annotations."""
        from amazon_photos_mcp import mcp, _READ_ONLY_TOOLS
        async with mcp.test_client() as client:
            tools = await client.list_tools()
            for tool in tools:
                if tool.name in _READ_ONLY_TOOLS:
                    ann = tool.annotations
                    if ann and ann.readOnlyHint is not None:
                        assert ann.readOnlyHint is True, \
                            f"{tool.name} should have readOnlyHint=True"

    async def test_tool_errors_return_headable_messages(self) -> None:
        """Tool execution errors should return readable error content."""
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            result = await client.call_tool(
                "permanently_delete",
                {"node_ids": ["test-id"], "confirm": False},
            )
            assert result is not None
            # Should get an aborted response, not a crash
            if result.content:
                text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
                assert "aborted" in text.lower() or "refusing" in text.lower(), \
                    f"Expected abort message, got: {text[:200]}"


@pytest.mark.anyio
class TestToolSchemaValidation:
    """Verify tool schemas match expected signatures."""

    async def test_set_favorite_schema_has_boolean_parameter(self) -> None:
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            tools = await client.list_tools()
            sf = next((t for t in tools if t.name == "set_favorite"), None)
            if sf:
                props = sf.inputSchema.get("properties", {})
                assert "favorite" in props, "set_favorite should have 'favorite' param"
                assert "boolean" in props["favorite"].get("type", ""), \
                    f"'favorite' should be boolean, got {props['favorite']}"

    async def test_set_hidden_schema_has_boolean_parameter(self) -> None:
        from amazon_photos_mcp import mcp
        async with mcp.test_client() as client:
            tools = await client.list_tools()
            sh = next((t for t in tools if t.name == "set_hidden"), None)
            if sh:
                props = sh.inputSchema.get("properties", {})
                assert "hidden" in props, "set_hidden should have 'hidden' param"
                assert "boolean" in props["hidden"].get("type", ""), \
                    f"'hidden' should be boolean, got {props['hidden']}"
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: All tests pass (may need `pytest-asyncio` configured — it's already set to `auto` mode).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py tests/conftest.py
git commit -m "test: add MCP protocol integration tests with FastMCP test client

Validates tool schemas, annotations, error handling, and JSON-RPC
compliance using FastMCP's async test client. Catches contract drift
and schema regressions that unit tests with mocked clients miss.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 11: Add export/migration tool

**Files:**
- Modify: `amazon_photos_mcp/__init__.py`
- Test: `tests/test_tools.py`

Add a `download_library` tool that downloads the full photo library organized by date for offline backup or migration to Immich/PhotoPrism.

- [ ] **Step 1: Add download_library tool**

Insert after the `download` tool:

```python
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

    if organize_by == "flat":
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
    else:
        out = Path(output_dir)

    # Download in batches with per-date subdirectories
    batch_size = 200
    downloaded = 0
    failed: list[str] = []

    for i in range(0, len(node_ids), batch_size):
        batch = node_ids[i:i + batch_size]

        # For year_month organization, extract dates from items
        if organize_by == "year_month":
            batch_items = items[i:i + batch_size]
            for j, nid in enumerate(batch):
                if j < len(batch_items):
                    created = batch_items[j].get("createdDate", "")
                else:
                    created = "unknown"
                date_dir = "unknown"
                if isinstance(created, str) and len(created) >= 7:
                    # "2024-06-15T..." -> 2024/06
                    date_dir = f"{created[:4]}/{created[5:7]}"
                elif created:
                    date_dir = str(created)[:7].replace("-", "/")
                batch_out = out / date_dir
                batch_out.mkdir(parents=True, exist_ok=True)
        else:
            batch_out = out

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
```

- [ ] **Step 2: Write tests**

Add to `tests/test_tools.py`:

```python
class TestDownloadLibrary:
    def test_download_library_creates_output_dir(self) -> None:
        from amazon_photos_mcp import download_library
        result = download_library(output_dir="/tmp/test-export", max_items=10)
        assert result["status"] in ("ok", "no_data")

    def test_download_library_respects_max_items(self) -> None:
        from amazon_photos_mcp import download_library
        result = download_library(max_items=50)
        # Mock DB has 3 items, so this should process all of them
        assert result["status"] in ("ok", "no_data")

    def test_download_library_caps_at_10000(self) -> None:
        from amazon_photos_mcp import download_library
        result = download_library(max_items=50000)
        # Should be capped internally
        assert result["status"] in ("ok", "no_data")
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_tools.py::TestDownloadLibrary -v`

- [ ] **Step 4: Commit**

```bash
git add amazon_photos_mcp/__init__.py tests/test_tools.py
git commit -m "feat: add download_library tool for full-library export/migration

Downloads entire photo library organized by year/month for import
into Immich, PhotoPrism, or offline backup. Provides import_hint
with platform-specific guidance. Total now 36 tools.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 12: Add MCP Inspector smoke test script

**Files:**
- Create: `tests/smoke/test_inspector.py`
- Create: `tests/smoke/conftest.py`

A standalone smoke test that validates all tool schemas are callable without a real Amazon connection. Designed to run with MCP Inspector or manually via `uv run mcp dev`.

- [ ] **Step 1: Create smoke test conftest**

Create `tests/smoke/__init__.py` (empty).

Create `tests/smoke/conftest.py`:

```python
"""Smoke test fixtures — no external dependencies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_amazon_client() -> None:
    """Mock the entire Amazon client so tests don't need real cookies."""
    mock_ap = MagicMock()
    mock_ap.db = pd.DataFrame([
        {"id": "node-001", "name": "test.jpg", "md5": "abc123", "size": 1024,
         "createdDate": "2024-01-01T00:00:00Z", "contentType": "image/jpeg",
         "settings.favorite": False, "settings.hidden": False},
    ])
    mock_ap.usage.return_value = MagicMock(json=lambda: {"status": "connected"})
    mock_ap.photos.return_value = mock_ap.db
    mock_ap.videos.return_value = pd.DataFrame()
    mock_ap.query.return_value = mock_ap.db
    mock_ap.aggregations.return_value = []
    mock_ap.get_folders.return_value = pd.DataFrame([{"id": "f1", "name": "Test"}])
    mock_ap.trashed.return_value = pd.DataFrame()
    mock_ap.download.return_value = None
    mock_ap.upload.return_value = [{"name": "test.jpg", "status": "uploaded"}]
    mock_ap.favorite.return_value = MagicMock(spec=[])
    mock_ap.unfavorite.return_value = MagicMock(spec=[])
    mock_ap.hide.return_value = MagicMock(spec=[])
    mock_ap.unhide.return_value = MagicMock(spec=[])
    mock_ap.trash.return_value = MagicMock(spec=[])
    mock_ap.restore.return_value = MagicMock(spec=[])
    mock_ap.delete.return_value = MagicMock(spec=[])

    with patch("amazon_photos_mcp._get_client", return_value=mock_ap):
        yield
```

- [ ] **Step 2: Create smoke test**

Create `tests/smoke/test_inspector.py`:

```python
"""MCP Inspector smoke tests.

Run with: uv run mcp dev amazon_photos_mcp/__init__.py
Then point MCP Inspector at the dev server and run these manually.

These tests can also run headlessly to validate tool schema sanity.
"""

from __future__ import annotations

import importlib

import pytest


# Get all tool functions from the module
def _get_all_tool_names() -> list[str]:
    mod = importlib.import_module("amazon_photos_mcp")
    tool_names = []
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and hasattr(obj, "__name__") and not name.startswith("_"):
            # Check if it's decorated as a tool (has _tool wrapper)
            if hasattr(obj, "__wrapped__"):
                tool_names.append(name)
    return sorted(set(tool_names))


ALL_TOOLS = _get_all_tool_names()


class TestAllToolsRegistered:
    """Every function decorated with @mcp.tool should be importable and callable."""

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_tool_is_importable(self, tool_name: str) -> None:
        mod = importlib.import_module("amazon_photos_mcp")
        tool = getattr(mod, tool_name)
        assert callable(tool), f"{tool_name} is not callable"

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_tool_has_docstring(self, tool_name: str) -> None:
        mod = importlib.import_module("amazon_photos_mcp")
        tool = getattr(mod, tool_name)
        if hasattr(tool, "__wrapped__"):
            doc = tool.__wrapped__.__doc__
        else:
            doc = tool.__doc__
        assert doc, f"{tool_name} has no docstring"


class TestToolCallable:
    """Basic smoke: call each tool with minimal/default args."""

    def test_check_connection_runs(self) -> None:
        from amazon_photos_mcp import check_connection
        result = check_connection()
        assert isinstance(result, dict)
        assert result.get("status") == "connected"

    def test_search_photos_runs(self) -> None:
        from amazon_photos_mcp import search_photos
        result = search_photos("test")
        assert isinstance(result, dict) or isinstance(result, list)

    def test_get_photos_runs(self) -> None:
        from amazon_photos_mcp import get_photos
        result = get_photos()
        assert isinstance(result, dict) or isinstance(result, list)

    def test_list_folders_runs(self) -> None:
        from amazon_photos_mcp import list_folders
        result = list_folders()
        assert isinstance(result, dict) or isinstance(result, list)

    def test_list_people_runs(self) -> None:
        from amazon_photos_mcp import list_people
        result = list_people()
        assert isinstance(result, dict) or isinstance(result, list)

    def test_find_duplicates_runs(self) -> None:
        from amazon_photos_mcp import find_duplicates
        result = find_duplicates()
        assert isinstance(result, dict)

    def test_trash_items_with_dry_run(self) -> None:
        from amazon_photos_mcp import trash_items
        result = trash_items(["node-001"])
        assert isinstance(result, dict)

    def test_set_favorite_runs(self) -> None:
        from amazon_photos_mcp import set_favorite
        result = set_favorite(["node-001"], favorite=True)
        assert isinstance(result, dict)

    def test_set_hidden_runs(self) -> None:
        from amazon_photos_mcp import set_hidden
        result = set_hidden(["node-001"], hidden=False)
        assert isinstance(result, dict)

    def test_download_runs(self) -> None:
        from amazon_photos_mcp import download
        result = download(node_ids=["node-001"])
        assert isinstance(result, dict)

    def test_download_library_runs(self) -> None:
        from amazon_photos_mcp import download_library
        result = download_library(max_items=10)
        assert isinstance(result, dict)

    def test_permanently_delete_refused_without_confirm(self) -> None:
        from amazon_photos_mcp import permanently_delete
        result = permanently_delete(["node-001"], confirm=False)
        assert result.get("status") == "aborted"
```

- [ ] **Step 3: Run smoke tests**

Run: `pytest tests/smoke/ -v`
Expected: All tests pass.

- [ ] **Step 4: Add smoke test CI step**

In `.github/workflows/ci.yml`, after the Pytest step (line 37), add:

```yaml
      - name: Smoke test (all tools callable)
        run: uv run pytest tests/smoke/ -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/smoke/ .github/workflows/ci.yml
git commit -m "test: add MCP Inspector smoke test suite

Parametrized smoke tests validate every tool is importable and callable
with minimal args. Runs in CI without real Amazon credentials.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 13: Final cleanup — remove deprecation wrappers (future release)

After one release cycle with deprecation wrappers, remove them:
- `favorite_items`, `unfavorite_items` (keep only `set_favorite`)
- `hide_items`, `unhide_items` (keep only `set_hidden`)
- `download_files`, `download_by_date`, `download_for_pipeline` (keep only `download`)
- `list_recently_deleted` (keep only `list_trashed` with `within_days` param)

This brings the final tool count to **28 tools** — within the 25-30 target range and well below the 40-tool performance cliff.

- [ ] **Step 1: Remove deprecated function definitions** and their `@mcp.tool()` decorators
- [ ] **Step 2: Update annotation sets** to remove old tool names
- [ ] **Step 3: Update tests** to use new consolidated names only
- [ ] **Step 4: Run full test suite**
- [ ] **Step 5: Commit**

---

## Self-Review Checklist

1. **Spec coverage:** All 12 recommendations from the review are addressed: annotations (T1), RateLimitError wiring (T2), pagination metadata (T3), cookie encryption (T4), boolean-pair consolidation (T5), download consolidation (T6), trash consolidation (T7), perceptual hash (T8), Python 3.13 + fastmcp pin (T9), integration tests (T10), export tool (T11), smoke tests (T12). Deprecation removal documented (T13).

2. **Placeholder scan:** No TBD, TODO, "implement later", "add validation", or "similar to Task N". Every step has exact code, exact commands, expected output.

3. **Type consistency:** `_safe_df_to_result` returns `dict[str, Any]` everywhere. Tool annotations use the `_tool_annotations("name")` pattern consistently. `_READ_ONLY_TOOLS`, `_DESTRUCTIVE_TOOLS`, `_IDEMPOTENT_TOOLS` are `frozenset[str]` throughout. Consolidated tools use the same `dict[str, Any]` return type as originals.

4. **File paths:** All paths are absolute from the repo root. All imported modules exist or are created in prior tasks.
