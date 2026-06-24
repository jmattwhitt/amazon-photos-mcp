from unittest.mock import AsyncMock, patch

import pytest

from amazon_photos_mcp.tools.duplicates import trash_near_duplicates


@patch("amazon_photos_mcp.tools.duplicates._get_client")
@pytest.mark.asyncio
async def test_trash_near_duplicates_quality_scoring(mock_get_client):
    mock_ap = AsyncMock()
    # node1: small HEIC, node2: small JPEG, node3: large JPEG (should win)
    items = [
        {
            "id": "node1",
            "name": "img1.heic",
            "contentType": "image/heic",
            "size": 1000,
            "image": {"width": 100, "height": 100},
        },
        {
            "id": "node2",
            "name": "img2.jpg",
            "contentType": "image/jpeg",
            "size": 500,
            "image": {"width": 50, "height": 50},
        },
        {
            "id": "node3",
            "name": "img3.jpg",
            "contentType": "image/jpeg",
            "size": 2000,
            "image": {"width": 200, "height": 200},
        },
    ]
    mock_ap.query.return_value = items
    mock_get_client.return_value = mock_ap

    res = await trash_near_duplicates(group=["node1", "node2", "node3"], dry_run=True, keep_strategy="best_quality")

    assert isinstance(res, dict)
    assert res["action"] == "dry_run"
    assert res["keep_id"] == "node3"  # largest JPEG wins
    assert "node1" in res["trash_ids"]
    assert "node2" in res["trash_ids"]
    assert res["keep_strategy"] == "best_quality"


@patch("amazon_photos_mcp.tools.duplicates._get_client")
@pytest.mark.asyncio
async def test_trash_near_duplicates_oldest_strategy(mock_get_client):
    mock_ap = AsyncMock()
    items = [
        {"id": "node1", "createdDate": "2024-02-01", "name": "newer.jpg"},
        {"id": "node2", "createdDate": "2024-01-01", "name": "older.jpg"},  # Oldest
    ]
    mock_ap.query.return_value = items
    mock_get_client.return_value = mock_ap

    res = await trash_near_duplicates(group=["node1", "node2"], dry_run=True, keep_strategy="oldest")

    assert isinstance(res, dict)
    assert res["keep_id"] == "node2"  # oldest wins
    assert "node1" in res["trash_ids"]
    assert res["keep_strategy"] == "oldest"
