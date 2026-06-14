"""Tests for bugs fixed in hostile-review pass (June 2026)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from amazon_photos_mcp import _configure_http_pooling, _safe_df_to_result, _wrap_http_errors
from amazon_photos_mcp.config import _coerce
from amazon_photos_mcp.tools.search import _resolve_person_cluster, _sanitize_query_value

# ---------------------------------------------------------------------------
# _configure_http_pooling
# ---------------------------------------------------------------------------


class TestConfigureHttpPooling:
    def test_sets_pool_attributes(self) -> None:
        """_configure_http_pooling sets keepalive and connection limits."""

        mock_client = MagicMock()
        mock_pool = MagicMock()
        mock_transport = MagicMock()
        mock_transport._pool = mock_pool
        mock_client.client._transport = mock_transport

        _configure_http_pooling(mock_client)

        assert mock_pool._keepalive_expiry == 30.0
        assert mock_pool._max_keepalive_connections == 5
        assert mock_pool._max_connections == 10

    def test_noop_when_no_client_attr(self) -> None:
        """_configure_http_pooling is a no-op when client has no .client attr."""

        obj = MagicMock(spec_set=[])
        _configure_http_pooling(obj)


# ---------------------------------------------------------------------------
# _wrap_http_errors
# ---------------------------------------------------------------------------


class TestWrapHttpErrors:
    def test_passthrough_on_success(self) -> None:
        """Patched request returns the response unchanged for 200 OK."""

        mock_client = MagicMock()
        ok_resp = MagicMock(status_code=200)
        mock_client.client.request.return_value = ok_resp

        _wrap_http_errors(mock_client)

        result = mock_client.client.request("GET", "https://example.com")
        assert result is ok_resp

    def test_timeout_default_added(self) -> None:
        """Patched request adds a default timeout of 30s."""

        mock_client = MagicMock()
        ok_resp = MagicMock(status_code=200)
        orig_request = mock_client.client.request
        orig_request.return_value = ok_resp

        _wrap_http_errors(mock_client)

        mock_client.client.request("GET", "https://example.com")
        call_kwargs = orig_request.call_args[1]
        assert call_kwargs.get("timeout") == 30.0

    def test_noop_when_no_client_attr(self) -> None:
        """_wrap_http_errors is a no-op when object has no .client attr."""

        obj = MagicMock(spec_set=[])
        _wrap_http_errors(obj)


# ---------------------------------------------------------------------------
# Traceback suppression in _tool decorator
# ---------------------------------------------------------------------------


class TestToolTracebackSuppression:
    def test_no_traceback_by_default(self) -> None:
        """Unexpected errors should NOT include traceback by default."""
        import amazon_photos_mcp as mod2

        @mod2._tool
        def bad_tool():
            raise ValueError("secret internal detail")

        result = bad_tool()
        assert result["error"] is True
        assert result["code"] == "UNEXPECTED_ERROR"
        assert "traceback" not in result

    def test_traceback_included_when_debug_enabled(self, monkeypatch) -> None:
        """Unexpected errors include traceback when AMAZON_PHOTOS_DEBUG=1."""
        monkeypatch.setenv("AMAZON_PHOTOS_DEBUG", "1")

        import amazon_photos_mcp as mod2

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
    def test_strips_parens(self) -> None:

        result = _sanitize_query_value("type:(PHOTOS) AND things:(beach)")
        assert "(" not in result
        assert ")" not in result

    def test_strips_logical_keywords(self) -> None:

        result = _sanitize_query_value("beach AND park OR forest NOT desert")
        assert "AND" not in result
        assert "OR" not in result
        assert "NOT" not in result

    def test_preserves_valid_input(self) -> None:

        result = _sanitize_query_value("beach park forest")
        assert result == "beach park forest"


# ---------------------------------------------------------------------------
# Person cluster resolver
# ---------------------------------------------------------------------------


class TestResolvePersonCluster:
    def test_resolves_known_name(self) -> None:

        mock_ap = MagicMock()
        mock_ap.aggregations.return_value = [
            {"value": "cluster-abc", "count": 42, "searchData": {"clusterName": "Alice"}},
        ]
        result = _resolve_person_cluster(mock_ap, "Alice")
        assert result == "cluster-abc"

    def test_case_insensitive_match(self) -> None:

        mock_ap = MagicMock()
        mock_ap.aggregations.return_value = [
            {"value": "cluster-xyz", "count": 10, "searchData": {"clusterName": "Bob"}},
        ]
        result = _resolve_person_cluster(mock_ap, "bob")
        assert result == "cluster-xyz"

    def test_returns_none_for_unknown(self) -> None:

        mock_ap = MagicMock()
        mock_ap.aggregations.return_value = []
        result = _resolve_person_cluster(mock_ap, "UnknownPerson")
        assert result is None


# ---------------------------------------------------------------------------
# _coerce error handling
# ---------------------------------------------------------------------------


class TestCoerceErrorHandling:
    def test_invalid_int_falls_back_to_default(self) -> None:

        result = _coerce("not_a_number", 42)
        assert result == 42

    def test_invalid_float_falls_back_to_default(self) -> None:

        result = _coerce("not_a_float", 3.14)
        assert result == 3.14

    def test_valid_int_passes_through(self) -> None:

        result = _coerce("10", 0)
        assert result == 10
        assert isinstance(result, int)

    def test_valid_float_passes_through(self) -> None:

        result = _coerce("2.5", 0.0)
        assert result == 2.5
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# search_by_date validation
# ---------------------------------------------------------------------------


class TestSearchByDateValidation:
    def test_valid_month_passes(self, mock_ap) -> None:
        from amazon_photos_mcp import search_by_date

        result = search_by_date(year=2024, month=6, day=15)
        assert "error" not in result

    def test_invalid_month_rejected(self, mock_ap) -> None:
        from amazon_photos_mcp import search_by_date

        result = search_by_date(year=2024, month=99)
        assert result.get("error") is True
        assert result["code"] == "INVALID_ARGS"
        assert "month" in result["message"].lower()

    def test_invalid_day_rejected(self, mock_ap) -> None:
        from amazon_photos_mcp import search_by_date

        result = search_by_date(year=2024, month=6, day=999)
        assert result.get("error") is True
        assert result["code"] == "INVALID_ARGS"
        assert "day" in result["message"].lower()


# ---------------------------------------------------------------------------
# _safe_df_to_result reports correct total after dedup
# ---------------------------------------------------------------------------


class TestSafeDfToResultDedup:
    def test_total_reflects_dedup(self) -> None:
        """total should match count after drop_duplicates, not before."""

        df = pd.DataFrame([
            {"id": "a", "name": "photo.jpg"},
            {"id": "a", "name": "photo_copy.jpg"},
            {"id": "b", "name": "other.jpg"},
        ])
        result = _safe_df_to_result(df, max_results=50)
        assert result["total"] == 2
        assert result["has_more"] is False
        assert len(result["items"]) == 2
