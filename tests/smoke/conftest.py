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
