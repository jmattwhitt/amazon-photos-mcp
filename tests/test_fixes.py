"""Tests for bugs fixed in hostile-review pass (June 2026)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from amazon_photos_mcp.config import _coerce
from amazon_photos_mcp.tools.search import _resolve_person_cluster, _sanitize_query_value

# ---------------------------------------------------------------------------
# Traceback suppression in _tool decorator
# ---------------------------------------------------------------------------


class TestToolTracebackSuppression:
    @pytest.mark.asyncio
    async def test_no_traceback_by_default(self) -> None:
        """Unexpected errors should NOT include traceback by default."""
        import amazon_photos_mcp.decorators as mod2

        @mod2._tool
        def bad_tool():
            raise ValueError("secret internal detail")

        result = bad_tool()
        assert result["error"] is True
        assert result["code"] == "UNEXPECTED_ERROR"
        assert "traceback" not in result

    @pytest.mark.asyncio
    async def test_traceback_included_when_debug_enabled(self, monkeypatch) -> None:
        """Unexpected errors include traceback when AMAZON_PHOTOS_DEBUG=1."""
        monkeypatch.setenv("AMAZON_PHOTOS_DEBUG", "1")

        import amazon_photos_mcp.decorators as mod2

        @mod2._tool
        def bad_tool():
            raise ValueError("debug mode")

        result = bad_tool()
        assert result["error"] is True
        assert "traceback" in result
        assert "debug mode" in result["traceback"]


# ---------------------------------------------------------------------------
# Query sanitizer
# ---------------------------------------------------------------------------


class TestSanitizeQueryValue:
    @pytest.mark.asyncio
    async def test_strips_parens(self) -> None:

        result = _sanitize_query_value("type:(PHOTOS) AND things:(beach)")
        assert "(" not in result
        assert ")" not in result

    @pytest.mark.asyncio
    async def test_strips_logical_keywords(self) -> None:

        result = _sanitize_query_value("beach AND park OR forest NOT desert")
        assert "AND" not in result
        assert "OR" not in result
        assert "NOT" not in result

    @pytest.mark.asyncio
    async def test_preserves_valid_input(self) -> None:

        result = _sanitize_query_value("beach park forest")
        assert result == "beach park forest"


# ---------------------------------------------------------------------------
# Person cluster resolver
# ---------------------------------------------------------------------------


class TestResolvePersonCluster:
    @pytest.mark.asyncio
    async def test_resolves_known_name(self) -> None:

        mock_ap = MagicMock()
        mock_ap.aggregations.return_value = [
            {"value": "cluster-abc", "count": 42, "searchData": {"clusterName": "Alice"}},
        ]
        result = _resolve_person_cluster(mock_ap, "Alice")
        assert result == "cluster-abc"

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self) -> None:

        mock_ap = MagicMock()
        mock_ap.aggregations.return_value = [
            {"value": "cluster-xyz", "count": 10, "searchData": {"clusterName": "Bob"}},
        ]
        result = _resolve_person_cluster(mock_ap, "bob")
        assert result == "cluster-xyz"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown(self) -> None:

        mock_ap = MagicMock()
        mock_ap.aggregations.return_value = []
        result = _resolve_person_cluster(mock_ap, "UnknownPerson")
        assert result is None


# ---------------------------------------------------------------------------
# _coerce error handling
# ---------------------------------------------------------------------------


class TestCoerceErrorHandling:
    @pytest.mark.asyncio
    async def test_invalid_int_falls_back_to_default(self) -> None:

        result = _coerce("not_a_number", 42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_invalid_float_falls_back_to_default(self) -> None:

        result = _coerce("not_a_float", 3.14)
        assert result == 3.14

    @pytest.mark.asyncio
    async def test_valid_int_passes_through(self) -> None:

        result = _coerce("10", 0)
        assert result == 10
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_valid_float_passes_through(self) -> None:

        result = _coerce("2.5", 0.0)
        assert result == 2.5
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# search_by_date validation
# ---------------------------------------------------------------------------


class TestSearchByDateValidation:
    @pytest.mark.asyncio
    async def test_valid_month_passes(self, mock_ap) -> None:
        from amazon_photos_mcp.tools.search import search_by_date

        result = await search_by_date(year=2024, month=6, day=15)
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_invalid_month_rejected(self, mock_ap) -> None:
        from amazon_photos_mcp.tools.search import search_by_date

        result = await search_by_date(year=2024, month=99)
        assert result.get("error") is True
        assert result["code"] == "INVALID_ARGS"
        assert "month" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_day_rejected(self, mock_ap) -> None:
        from amazon_photos_mcp.tools.search import search_by_date

        result = await search_by_date(year=2024, month=6, day=999)
        assert result.get("error") is True
        assert result["code"] == "INVALID_ARGS"
        assert "day" in result["message"].lower()


# ---------------------------------------------------------------------------
# _safe_df_to_result reports correct total after dedup
# ---------------------------------------------------------------------------
