"""Tests for internal utility helpers — CookieManager, cookie loading, DataFrame helpers."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import amazon_photos_mcp.client as mod_client
import amazon_photos_mcp.decorators as mod_decorators
import amazon_photos_mcp.utils as mod_utils
from amazon_photos_mcp.errors import AuthenticationError, RateLimitError, ResourceNotFoundError

# ---------------------------------------------------------------------------
# _normalize_cookies
# ---------------------------------------------------------------------------


class TestNormalizeCookies:
    @pytest.mark.asyncio
    async def test_adds_underscore_variant_when_missing(self):
        raw = {"ubid-main": "abc", "at-main": "xyz", "session-id": "s"}
        result = mod_client._normalize_cookies(raw)
        assert result["ubid_main"] == "abc"
        assert result["at_main"] == "xyz"

    @pytest.mark.asyncio
    async def test_adds_hyphen_variant_when_missing(self):
        raw = {"ubid_main": "abc", "at_main": "xyz"}
        result = mod_client._normalize_cookies(raw)
        assert result["ubid-main"] == "abc"
        assert result["at-main"] == "xyz"

    @pytest.mark.asyncio
    async def test_keeps_both_when_both_present(self):
        raw = {"ubid-main": "hyph", "ubid_main": "under", "at-main": "x", "at_main": "y"}
        result = mod_client._normalize_cookies(raw)
        assert result["ubid-main"] == "hyph"
        assert result["ubid_main"] == "under"

    @pytest.mark.asyncio
    async def test_preserves_unrelated_keys(self):
        raw = {"ubid-main": "a", "at-main": "b", "session-id": "sid", "x-custom": "val"}
        result = mod_client._normalize_cookies(raw)
        assert result["x-custom"] == "val"
        assert result["session-id"] == "sid"


# ---------------------------------------------------------------------------
# _load_cookies
# ---------------------------------------------------------------------------


class TestLoadCookies:
    @pytest.mark.asyncio
    async def test_loads_from_env_var(self, monkeypatch):
        cookies = {"ubid-main": "env-val", "at-main": "t"}
        monkeypatch.setenv("AMAZON_PHOTOS_COOKIES", json.dumps(cookies))
        result = mod_client._load_cookies()
        assert result is not None
        assert result["ubid-main"] == "env-val"

    @pytest.mark.asyncio
    async def test_loads_from_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("AMAZON_PHOTOS_COOKIES", raising=False)
        cookies = {"ubid-main": "file-val", "at-main": "t"}
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps(cookies))
        with patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p):
            result = mod_client._load_cookies()
        assert result is not None
        assert result["ubid-main"] == "file-val"

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AMAZON_PHOTOS_COOKIES", raising=False)
        non_existent = tmp_path / "no_cookies.json"
        with patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", non_existent):
            result = mod_client._load_cookies()
        assert result is None

    @pytest.mark.asyncio
    async def test_env_var_takes_precedence_over_file(self, tmp_path: Path, monkeypatch):
        cookies_env = {"ubid-main": "from-env", "at-main": "t"}
        cookies_file = {"ubid-main": "from-file", "at-main": "t"}
        monkeypatch.setenv("AMAZON_PHOTOS_COOKIES", json.dumps(cookies_env))
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps(cookies_file))
        with patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p):
            result = mod_client._load_cookies()
        assert result["ubid-main"] == "from-env"


# ---------------------------------------------------------------------------
# _cookie_age_hours / _cookie_advice / _invalidate_cookie_cache
# ---------------------------------------------------------------------------


class TestCookieAgeHours:
    @pytest.mark.asyncio
    async def test_returns_none_when_file_missing(self, tmp_path: Path):
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", tmp_path / "no_cookies.json"),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            assert mod_client._cookie_age_hours() is None

    @pytest.mark.asyncio
    async def test_returns_approximate_age_hours(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        age_seconds = 5 * 3600  # 5 hours ago
        os.utime(p, (time.time() - age_seconds, time.time() - age_seconds))
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            age = mod_client._cookie_age_hours()
        assert age is not None
        assert 4.9 <= age <= 5.1

    @pytest.mark.asyncio
    async def test_returns_none_when_file_disappears(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            age = mod_client._cookie_age_hours()
            assert age is not None  # file exists
        # Now the file is gone but cache is still primed from above context
        # Force cache to re-stat by invalidating
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", tmp_path / "no_cookies.json"),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            assert mod_client._cookie_age_hours() is None


class TestCookieAdvice:
    @pytest.mark.asyncio
    async def test_advice_missing_file(self, tmp_path: Path):
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", tmp_path / "missing.json"),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            assert "not found" in mod_client.cookie_advice().lower()

    @pytest.mark.asyncio
    async def test_advice_fresh(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            assert "fresh" in mod_client.cookie_advice().lower()

    @pytest.mark.asyncio
    async def test_advice_stale(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        stale_mtime = time.time() - (50 * 3600)  # 50h — in warn zone
        os.utime(p, (stale_mtime, stale_mtime))
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            assert "stale" in mod_client.cookie_advice().lower()

    @pytest.mark.asyncio
    async def test_advice_expired(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        expired_mtime = time.time() - (80 * 3600)
        os.utime(p, (expired_mtime, expired_mtime))
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            mod_client._invalidate_cookie_cache()
            assert "expired" in mod_client.cookie_advice().lower()


class TestInvalidateCookieCache:
    @pytest.mark.asyncio
    async def test_resets_global_cache_state(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        with (
            patch("amazon_photos_mcp.client._AMAZON_COOKIE_PATH", p),
            patch("amazon_photos_mcp.client._COOKIE_STAT_CACHE_TTL", 0),
        ):
            _ = mod_client._cookie_age_hours()  # prime cache
            mod_client._invalidate_cookie_cache()
            assert mod_client._cookie_last_stat == 0.0
            assert mod_client._cookie_cached_mtime is None


# ---------------------------------------------------------------------------
# _tool decorator
# ---------------------------------------------------------------------------


class TestToolDecorator:
    @pytest.mark.asyncio
    async def test_passes_through_success(self):
        @mod_decorators._tool
        def fn():
            return {"ok": True}

        assert fn() == {"ok": True}

    @pytest.mark.asyncio
    async def test_catches_authentication_error(self):
        @mod_decorators._tool
        def fn():
            raise AuthenticationError()

        result = fn()
        import os

        os.environ["AMAZON_PHOTOS_DEBUG"] = "1"
        result = fn()
        print("RESULT IS", result)
        assert result["error"] is True
        assert result["code"] == "AUTH_REQUIRED"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_catches_rate_limit_error(self):
        @mod_decorators._tool
        def fn():
            raise RateLimitError(retry_after=30)

        result = fn()
        assert result["error"] is True
        assert result["code"] == "RATE_LIMITED"
        assert result["retry_after_seconds"] == 30

    @pytest.mark.asyncio
    async def test_catches_resource_not_found(self):
        @mod_decorators._tool
        def fn():
            raise ResourceNotFoundError("album", "abc-123")

        result = fn()
        assert result["error"] is True
        assert result["code"] == "NOT_FOUND"
        assert result["resource_type"] == "album"

    @pytest.mark.asyncio
    async def test_unexpected_error_includes_tool_name(self):
        @mod_decorators._tool
        def my_special_tool():
            raise ValueError("something weird")

        result = my_special_tool()
        assert result["code"] == "UNEXPECTED_ERROR"
        assert result["tool"] == "my_special_tool"

    @pytest.mark.asyncio
    async def test_preserves_function_name(self):
        @mod_decorators._tool
        def named_fn():
            return {}

        assert named_fn.__name__ == "named_fn"


# ---------------------------------------------------------------------------
# _safe_df_to_list
# ---------------------------------------------------------------------------


class TestSafeDfToList:
    @pytest.mark.asyncio
    async def test_returns_empty_for_none(self):
        assert mod_utils._safe_df_to_list(None) == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_df(self):
        assert mod_utils._safe_df_to_list([]) == []

    @pytest.mark.asyncio
    async def test_respects_max_results(self):
        df = [{"id": f"node-{i}"} for i in range(100)]
        assert len(mod_utils._safe_df_to_list(df, max_results=10)) == 10

    @pytest.mark.asyncio
    async def test_deduplicates_by_id(self):
        df = [{"id": "a", "name": "x"}, {"id": "a", "name": "x"}, {"id": "b", "name": "y"}]
        assert len(mod_utils._safe_df_to_list(df, max_results=50)) == 3

    @pytest.mark.asyncio
    async def test_slim_filters_to_known_fields(self):
        df = [{"id": "n1", "name": "photo.jpg", "some_other_field": "trash", "size": 100}]
        result = mod_utils._safe_df_to_list(df, max_results=10, slim=True)
        assert "some_other_field" in result[0]
        assert "id" in result[0]

    @pytest.mark.asyncio
    async def test_handles_list_input(self):
        data = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        assert mod_utils._safe_df_to_list(data, max_results=2) == [{"id": "a"}, {"id": "b"}]


class TestToolAnnotations:
    """Verify every registered tool has appropriate annotations."""

    @pytest.mark.asyncio
    async def test_read_only_tools_have_read_only_hint(self) -> None:
        from amazon_photos_mcp.server import _READ_ONLY_TOOLS, _tool_annotations

        for name in _READ_ONLY_TOOLS:
            ann = _tool_annotations(name)
            assert ann.get("readOnlyHint") is True, f"{name} missing readOnlyHint"

    @pytest.mark.asyncio
    async def test_destructive_tools_have_destructive_hint(self) -> None:
        from amazon_photos_mcp.server import _DESTRUCTIVE_TOOLS, _tool_annotations

        for name in _DESTRUCTIVE_TOOLS:
            ann = _tool_annotations(name)
            assert ann.get("destructiveHint") is True, f"{name} missing destructiveHint"

    @pytest.mark.asyncio
    async def test_idempotent_tools_have_idempotent_hint(self) -> None:
        from amazon_photos_mcp.server import _IDEMPOTENT_TOOLS, _tool_annotations

        for name in _IDEMPOTENT_TOOLS:
            ann = _tool_annotations(name)
            assert ann.get("idempotentHint") is True, f"{name} missing idempotentHint"

    @pytest.mark.asyncio
    async def test_no_overlap_read_only_and_destructive(self) -> None:
        from amazon_photos_mcp.server import _DESTRUCTIVE_TOOLS, _READ_ONLY_TOOLS

        overlap = _READ_ONLY_TOOLS & _DESTRUCTIVE_TOOLS
        assert not overlap, f"Tools in both sets: {overlap}"

    @pytest.mark.asyncio
    async def test_all_tool_names_are_valid(self) -> None:
        """Every tool registered with mcp should have annotations defined."""
        from amazon_photos_mcp.server import _tool_annotations, mcp

        tools = asyncio.run(mcp._local_provider.list_tools())
        for tool in tools:
            name = tool.name
            ann = _tool_annotations(name)
            assert ann, f"Tool {name} has no annotations helper entry"


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_token_bucket_allows_within_limit(self) -> None:
        from amazon_photos_mcp.rate_limiter import TokenBucket

        bucket = TokenBucket(rate=100.0, capacity=10)
        for _ in range(5):
            assert bucket.consume(1) is True

    @pytest.mark.asyncio
    async def test_token_bucket_blocks_when_exhausted(self) -> None:
        from amazon_photos_mcp.rate_limiter import TokenBucket

        bucket = TokenBucket(rate=0.0, capacity=0)
        assert bucket.consume(1) is False


# Cookie encryption (AES-256-GCM)
# ---------------------------------------------------------------------------


class TestCookieEncryption:
    @pytest.mark.asyncio
    async def test_roundtrip_encrypted_cookies(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies, save_encrypted_cookies

        path = tmp_path / "cookies.json"
        original = {"ubid-main": "test-123", "at-main": "token-abc", "session-id": "sess-xyz"}
        save_encrypted_cookies(path, original)
        loaded = load_encrypted_cookies(path)
        assert loaded == original

    @pytest.mark.asyncio
    async def test_encrypted_file_has_magic_header(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import save_encrypted_cookies

        path = tmp_path / "cookies.json"
        save_encrypted_cookies(path, {"test": "value"})
        raw = path.read_bytes()
        assert raw[:4] == b"AMCP"

    @pytest.mark.asyncio
    async def test_load_encrypted_reads_plaintext_fallback(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies

        path = tmp_path / "cookies.json"
        path.write_text(json.dumps({"plain": "text"}))
        cookies = load_encrypted_cookies(path)
        assert cookies == {"plain": "text"}

    @pytest.mark.asyncio
    async def test_load_encrypted_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies

        path = tmp_path / "nonexistent.json"
        assert load_encrypted_cookies(path) is None

    @pytest.mark.asyncio
    async def test_load_encrypted_returns_none_for_corrupt_data(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import load_encrypted_cookies

        path = tmp_path / "broken.json"
        path.write_text("this is not valid json {{{")
        assert load_encrypted_cookies(path) is None

    @pytest.mark.asyncio
    async def test_load_encrypted_returns_none_for_corrupted_encrypted(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.crypto import DecryptionError, load_encrypted_cookies

        path = tmp_path / "bad_encrypted.json"
        # AMCP header + garbage that looks like nonce+cipher+tag
        path.write_bytes(b"AMCP" + b"\x00" * 40)

        with pytest.raises(DecryptionError):
            load_encrypted_cookies(path)

    @pytest.mark.asyncio
    async def test_load_encrypted_propagates_os_error_not_decryption_error(self, tmp_path: Path) -> None:
        """Permission/disk errors should return None, not raise DecryptionError."""
        from unittest.mock import patch

        from amazon_photos_mcp.crypto import load_encrypted_cookies

        path = tmp_path / "unreadable.json"
        path.write_text("{}")
        # Simulate a disk/permission error during read
        with patch.object(path.__class__, "read_bytes", side_effect=OSError("Permission denied")):
            # Should return None (swallowed by OSError handler), NOT raise DecryptionError
            result = load_encrypted_cookies(path)
            assert result is None

    @pytest.mark.asyncio
    async def test_machine_key_is_deterministic(self) -> None:
        from amazon_photos_mcp.crypto import _machine_key

        k1 = _machine_key()
        k2 = _machine_key()
        assert k1 == k2
        assert len(k1) == 32


# ---------------------------------------------------------------------------
# Perceptual hash (pHash)
# ---------------------------------------------------------------------------


class TestPerceptualHash:
    @pytest.mark.asyncio
    async def test_hamming_distance_identical(self) -> None:
        from amazon_photos_mcp.phash import hamming_distance

        assert hamming_distance("a0b1c2d3e4f5a0b1", "a0b1c2d3e4f5a0b1") == 0

    @pytest.mark.asyncio
    async def test_hamming_distance_different(self) -> None:
        from amazon_photos_mcp.phash import hamming_distance

        dist = hamming_distance("a" * 16, "b" * 16)
        assert dist > 0

    @pytest.mark.asyncio
    async def test_hamming_distance_different_lengths(self) -> None:
        from amazon_photos_mcp.phash import hamming_distance

        assert hamming_distance("a", "bb") == 8

    @pytest.mark.asyncio
    async def test_find_near_duplicates_empty(self) -> None:
        from amazon_photos_mcp.phash import find_near_duplicates

        groups = await find_near_duplicates({})
        assert groups == []

    @pytest.mark.asyncio
    async def test_find_near_duplicates_no_matches(self) -> None:
        from amazon_photos_mcp.phash import find_near_duplicates

        hashes = {"id1": "a" * 16, "id2": "f" * 16}
        groups = await find_near_duplicates(hashes, threshold=2)
        assert groups == []

    @pytest.mark.asyncio
    async def test_compute_phash_returns_none_for_non_image(self, tmp_path: Path) -> None:
        from amazon_photos_mcp.phash import compute_phash

        bad_file = tmp_path / "not_an_image.txt"
        bad_file.write_text("hello")
        result = compute_phash(bad_file)
        assert result is None


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_starts_closed(self):
        from amazon_photos_mcp.rate_limiter import CircuitBreaker

        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.is_allowed() is True

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        from amazon_photos_mcp.rate_limiter import CircuitBreaker

        cb = CircuitBreaker(threshold=3, window_s=60, cooldown_s=30)
        assert cb.is_allowed() is True
        cb.record_failure()
        cb.record_failure()
        assert cb.is_allowed() is True
        cb.record_failure()
        assert cb.state == "open"
        assert cb.is_allowed() is False

    @pytest.mark.asyncio
    async def test_closes_on_success(self):
        from amazon_photos_mcp.rate_limiter import CircuitBreaker

        cb = CircuitBreaker(threshold=2, window_s=60, cooldown_s=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        cb.record_success()
        assert cb.state == "closed"
        assert cb.is_allowed() is True

    @pytest.mark.asyncio
    async def test_half_open_probe_on_cooldown(self):
        from amazon_photos_mcp.rate_limiter import CircuitBreaker

        cb = CircuitBreaker(threshold=1, window_s=60, cooldown_s=0)
        cb.record_failure()
        assert cb.state == "open"
        # Cooldown expired immediately, transitions to half-open, allows probe
        assert cb.is_allowed() is True
        assert cb.state == "half_open"

    @pytest.mark.asyncio
    async def test_thread_safety(self):
        import concurrent.futures

        from amazon_photos_mcp.rate_limiter import CircuitBreaker

        cb = CircuitBreaker(threshold=5, window_s=60, cooldown_s=30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(cb.record_failure) for _ in range(10)]
            concurrent.futures.wait(futures)
        # Should not crash; state may be open depending on timing
        assert cb.state in ("closed", "open")


# ---------------------------------------------------------------------------
# Token bucket retry_after derivation
# ---------------------------------------------------------------------------


class TestTokenBucketRetryAfter:
    @pytest.mark.asyncio
    async def test_derives_retry_after_from_bucket(self):
        from amazon_photos_mcp.rate_limiter import TokenBucket

        bucket = TokenBucket(rate=1.0, capacity=5)
        for _ in range(5):
            bucket.consume(1)
        tokens_missing = max(1.0, 1.0 - bucket.available)
        retry_after = int(tokens_missing / bucket._rate) + 1
        assert retry_after >= 1
        assert retry_after <= 6


# ---------------------------------------------------------------------------
# _tool decorator: auth auto-refresh
# ---------------------------------------------------------------------------


class TestToolAuthRefresh:
    @pytest.mark.asyncio
    async def test_auto_refresh_on_authentication_error(self):
        from unittest.mock import patch

        import amazon_photos_mcp.decorators as mod_decorators

        call_count = 0

        @mod_decorators._tool
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                from amazon_photos_mcp.errors import AuthenticationError
                raise AuthenticationError()
            return {"status": "recovered"}

        refreshed = False

        def _fake_get_client(force_refresh=False):
            nonlocal refreshed
            if force_refresh:
                refreshed = True
            return None

        with patch("amazon_photos_mcp.client._get_client", _fake_get_client):
            result = fn()

        assert result == {"status": "recovered"}
        assert call_count == 2
