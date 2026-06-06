"""Tests for internal utility helpers — CookieManager, cookie loading, DataFrame helpers."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import amazon_photos_mcp as mod

# ---------------------------------------------------------------------------
# _normalize_cookies
# ---------------------------------------------------------------------------

class TestNormalizeCookies:
    def test_adds_underscore_variant_when_missing(self):
        raw = {"ubid-main": "abc", "at-main": "xyz", "session-id": "s"}
        result = mod._normalize_cookies(raw)
        assert result["ubid_main"] == "abc"
        assert result["at_main"] == "xyz"

    def test_adds_hyphen_variant_when_missing(self):
        raw = {"ubid_main": "abc", "at_main": "xyz"}
        result = mod._normalize_cookies(raw)
        assert result["ubid-main"] == "abc"
        assert result["at-main"] == "xyz"

    def test_keeps_both_when_both_present(self):
        raw = {"ubid-main": "hyph", "ubid_main": "under", "at-main": "x", "at_main": "y"}
        result = mod._normalize_cookies(raw)
        assert result["ubid-main"] == "hyph"
        assert result["ubid_main"] == "under"

    def test_preserves_unrelated_keys(self):
        raw = {"ubid-main": "a", "at-main": "b", "session-id": "sid", "x-custom": "val"}
        result = mod._normalize_cookies(raw)
        assert result["x-custom"] == "val"
        assert result["session-id"] == "sid"


# ---------------------------------------------------------------------------
# _load_cookies
# ---------------------------------------------------------------------------

class TestLoadCookies:
    def test_loads_from_env_var(self, monkeypatch):
        cookies = {"ubid-main": "env-val", "at-main": "t"}
        monkeypatch.setenv("AMAZON_PHOTOS_COOKIES", json.dumps(cookies))
        result = mod._load_cookies()
        assert result is not None
        assert result["ubid-main"] == "env-val"

    def test_loads_from_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("AMAZON_PHOTOS_COOKIES", raising=False)
        cookies = {"ubid-main": "file-val", "at-main": "t"}
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps(cookies))
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p):
            result = mod._load_cookies()
        assert result is not None
        assert result["ubid-main"] == "file-val"

    def test_returns_none_when_nothing_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AMAZON_PHOTOS_COOKIES", raising=False)
        non_existent = tmp_path / "no_cookies.json"
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", non_existent):
            result = mod._load_cookies()
        assert result is None

    def test_env_var_takes_precedence_over_file(self, tmp_path: Path, monkeypatch):
        cookies_env = {"ubid-main": "from-env", "at-main": "t"}
        cookies_file = {"ubid-main": "from-file", "at-main": "t"}
        monkeypatch.setenv("AMAZON_PHOTOS_COOKIES", json.dumps(cookies_env))
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps(cookies_file))
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p):
            result = mod._load_cookies()
        assert result["ubid-main"] == "from-env"


# ---------------------------------------------------------------------------
# _cookie_age_hours / _cookie_advice / _invalidate_cookie_cache
# ---------------------------------------------------------------------------

class TestCookieAgeHours:
    def test_returns_none_when_file_missing(self, tmp_path: Path):
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", tmp_path / "no_cookies.json"), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            assert mod._cookie_age_hours() is None

    def test_returns_approximate_age_hours(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        age_seconds = 5 * 3600  # 5 hours ago
        os.utime(p, (time.time() - age_seconds, time.time() - age_seconds))
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            age = mod._cookie_age_hours()
        assert age is not None
        assert 4.9 <= age <= 5.1

    def test_returns_none_when_file_disappears(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            age = mod._cookie_age_hours()
            assert age is not None  # file exists
        # Now the file is gone but cache is still primed from above context
        # Force cache to re-stat by invalidating
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", tmp_path / "no_cookies.json"), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            assert mod._cookie_age_hours() is None


class TestCookieAdvice:
    def test_advice_missing_file(self, tmp_path: Path):
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", tmp_path / "missing.json"), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            assert "not found" in mod._cookie_advice().lower()

    def test_advice_fresh(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            assert "fresh" in mod._cookie_advice().lower()

    def test_advice_stale(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        stale_mtime = time.time() - (50 * 3600)  # 50h — in warn zone
        os.utime(p, (stale_mtime, stale_mtime))
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            assert "stale" in mod._cookie_advice().lower()

    def test_advice_expired(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        expired_mtime = time.time() - (80 * 3600)
        os.utime(p, (expired_mtime, expired_mtime))
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            mod._invalidate_cookie_cache()
            assert "expired" in mod._cookie_advice().lower()


class TestInvalidateCookieCache:
    def test_resets_global_cache_state(self, tmp_path: Path):
        p = tmp_path / "cookies.json"
        p.write_text("{}")
        with patch("amazon_photos_mcp._AMAZON_COOKIE_PATH", p), \
             patch("amazon_photos_mcp._COOKIE_STAT_CACHE_TTL", 0):
            _ = mod._cookie_age_hours()  # prime cache
            mod._invalidate_cookie_cache()
            assert mod._cookie_last_stat == 0.0
            assert mod._cookie_cached_mtime is None


# ---------------------------------------------------------------------------
# _tool decorator
# ---------------------------------------------------------------------------

class TestToolDecorator:
    def test_passes_through_success(self):
        @mod._tool
        def fn():
            return {"ok": True}
        assert fn() == {"ok": True}

    def test_catches_authentication_error(self):
        @mod._tool
        def fn():
            raise mod.AuthenticationError("bad cookie")
        result = fn()
        assert result["error"] is True
        assert result["code"] == "AUTH_REQUIRED"
        assert "suggestion" in result

    def test_catches_rate_limit_error(self):
        @mod._tool
        def fn():
            raise mod.RateLimitError(retry_after=30)
        result = fn()
        assert result["error"] is True
        assert result["code"] == "RATE_LIMITED"
        assert result["retry_after_seconds"] == 30

    def test_catches_resource_not_found(self):
        @mod._tool
        def fn():
            raise mod.ResourceNotFoundError("album", "abc-123")
        result = fn()
        assert result["error"] is True
        assert result["code"] == "NOT_FOUND"
        assert result["resource_type"] == "album"

    def test_unexpected_error_includes_tool_name(self):
        @mod._tool
        def my_special_tool():
            raise ValueError("something weird")
        result = my_special_tool()
        assert result["code"] == "UNEXPECTED_ERROR"
        assert result["tool"] == "my_special_tool"

    def test_preserves_function_name(self):
        @mod._tool
        def named_fn():
            return {}
        assert named_fn.__name__ == "named_fn"


# ---------------------------------------------------------------------------
# _safe_df_to_list
# ---------------------------------------------------------------------------

class TestSafeDfToList:
    def test_returns_empty_for_none(self):
        assert mod._safe_df_to_list(None) == []

    def test_returns_empty_for_empty_df(self):
        assert mod._safe_df_to_list(pd.DataFrame()) == []

    def test_respects_max_results(self):
        df = pd.DataFrame({"id": [f"node-{i}" for i in range(100)]})
        assert len(mod._safe_df_to_list(df, max_results=10)) == 10

    def test_deduplicates_by_id(self):
        df = pd.DataFrame({"id": ["a", "a", "b"], "name": ["x", "x", "y"]})
        assert len(mod._safe_df_to_list(df, max_results=50)) == 2

    def test_slim_filters_to_known_fields(self):
        df = pd.DataFrame([{"id": "n1", "name": "photo.jpg", "some_other_field": "trash", "size": 100}])
        result = mod._safe_df_to_list(df, max_results=10, slim=True)
        assert "some_other_field" not in result[0]
        assert "id" in result[0]

    def test_handles_list_input(self):
        data = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        assert mod._safe_df_to_list(data, max_results=2) == [{"id": "a"}, {"id": "b"}]


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
        from amazon_photos_mcp import _DESTRUCTIVE_TOOLS, _READ_ONLY_TOOLS
        overlap = _READ_ONLY_TOOLS & _DESTRUCTIVE_TOOLS
        assert not overlap, f"Tools in both sets: {overlap}"

    def test_all_tool_names_are_valid(self) -> None:
        """Every tool registered with mcp should have annotations defined."""
        from amazon_photos_mcp import _tool_annotations, mcp

        tools = asyncio.run(mcp._local_provider.list_tools())
        for tool in tools:
            name = tool.name
            ann = _tool_annotations(name)
            assert ann, f"Tool {name} has no annotations helper entry"
