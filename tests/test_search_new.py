from unittest.mock import MagicMock, patch

import pandas as pd

from amazon_photos_mcp.tools.search import advanced_search


@patch("amazon_photos_mcp.tools.search._get_client")
def test_advanced_search_date_query(mock_get_client):
    mock_ap = MagicMock()
    # Create empty df so post-filtering works fine without error
    mock_ap.query.return_value = pd.DataFrame([{"id": "node1", "size": 100, "createdDate": "2024-06-01"}])
    mock_get_client.return_value = mock_ap

    # Test date range
    res = advanced_search(date_from="2024-01-01", date_to="2024-12-31")

    mock_ap.query.assert_called_with("type:(PHOTOS) createdDate:[20240101 TO 20241231]")
    assert res["query_used"] == "type:(PHOTOS) createdDate:[20240101 TO 20241231]"
    assert len(res["items"]) == 1

    # Test open-ended date_from
    _ = advanced_search(date_from="2024-01-01")
    mock_ap.query.assert_called_with("type:(PHOTOS) createdDate:[20240101 TO]")

    # Test open-ended date_to
    _ = advanced_search(date_to="2024-12-31")
    mock_ap.query.assert_called_with("type:(PHOTOS) createdDate:[ TO 20241231]")


@patch("amazon_photos_mcp.tools.search._get_client")
def test_advanced_search_rejects_invalid_date_formats(mock_get_client):
    """Date validation: reject junk like '2024----01----01' (was silently accepted)."""
    mock_ap = MagicMock()
    mock_get_client.return_value = mock_ap

    # Multiple hyphens should be rejected
    res = advanced_search(date_from="2024----01----01")
    assert res.get("error") is True
    assert res["code"] == "INVALID_ARGS"
    assert "date format" in res.get("message", "").lower()

    # Missing digit should be rejected
    res2 = advanced_search(date_from="2024-1-1")
    assert res2.get("error") is True
    assert res2["code"] == "INVALID_ARGS"

    # Only one hyphen should be rejected
    res3 = advanced_search(date_to="2024-01")
    assert res3.get("error") is True
    assert res3["code"] == "INVALID_ARGS"


@patch("amazon_photos_mcp.tools.search._get_client")
def test_advanced_search_accepts_valid_date_formats(mock_get_client):
    """Both YYYY-MM-DD and YYYYMMDD should be accepted."""
    mock_ap = MagicMock()
    mock_ap.query.return_value = pd.DataFrame([{"id": "node1"}])
    mock_get_client.return_value = mock_ap

    # ISO format should work
    res = advanced_search(date_from="2024-01-01")
    assert "error" not in res

    # Compact format should work
    res2 = advanced_search(date_from="20240101")
    assert "error" not in res2

    # Empty string should be skipped (no error)
    mock_ap.query.return_value = pd.DataFrame([{"id": "node1"}])
    res3 = advanced_search(date_from="")
    assert "error" not in res3
