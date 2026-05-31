"""Shared fixtures for amazon-photos-mcp tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Cookie fixtures
# ---------------------------------------------------------------------------

SAMPLE_COOKIES = {
    "ubid-main": "123-4567890-1234567",
    "at-main": "Atza|some-token-value",
    "session-id": "123-4567890-9876543",
}


@pytest.fixture()
def cookie_file(tmp_path: Path) -> Path:
    """Write sample cookies.json to tmp_path and return its path."""
    p = tmp_path / ".config" / "amazon-photos-mcp" / "cookies.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(SAMPLE_COOKIES))
    return p


# ---------------------------------------------------------------------------
# Mock AmazonPhotos client
# ---------------------------------------------------------------------------

def _make_mock_db() -> pd.DataFrame:
    """Build a minimal parquet-like DataFrame for testing."""
    return pd.DataFrame(
        [
            {
                "id": "node-001",
                "name": "photo1.jpg",
                "md5": "aaaa",
                "size": 1024,
                "createdDate": "2024-01-01T00:00:00Z",
                "contentType": "image/jpeg",
                "settings.favorite": False,
                "settings.hidden": False,
            },
            {
                "id": "node-002",
                "name": "photo2.jpg",
                "md5": "aaaa",  # duplicate of node-001
                "size": 1024,
                "createdDate": "2024-06-01T00:00:00Z",
                "contentType": "image/jpeg",
                "settings.favorite": False,
                "settings.hidden": False,
            },
            {
                "id": "node-003",
                "name": "unique.jpg",
                "md5": "bbbb",
                "size": 2048,
                "createdDate": "2024-03-15T00:00:00Z",
                "contentType": "image/jpeg",
                "settings.favorite": True,
                "settings.hidden": False,
            },
        ]
    )


@pytest.fixture()
def mock_ap() -> MagicMock:
    """Return a pre-configured mock AmazonPhotos client."""
    ap = MagicMock()
    ap.db = _make_mock_db()

    # usage()
    usage_resp = MagicMock()
    usage_resp.json.return_value = {
        "status": "connected",
        "available": 5_000_000_000,
        "used": 1_000_000_000,
        "photos": 500,
        "videos": 20,
    }
    ap.usage.return_value = usage_resp

    # photos() / videos()
    ap.photos.return_value = _make_mock_db()
    ap.videos.return_value = pd.DataFrame()

    # query()
    ap.query.return_value = _make_mock_db()

    # aggregations("allPeople", out="")
    ap.aggregations.return_value = [
        {
            "value": "cluster-abc",
            "count": 42,
            "searchData": {"clusterName": "Alice", "nodeId": "folder-xyz"},
        },
        {
            "value": "cluster-def",
            "count": 7,
            "searchData": {"clusterName": None, "nodeId": "folder-uvw"},
        },
    ]

    # get_folders()
    ap.get_folders.return_value = pd.DataFrame(
        [{"id": "folder-1", "name": "Vacation"}, {"id": "folder-2", "name": "Family"}]
    )

    # trash / restore / delete — return plain dicts so standardized envelope logic works
    ap.trash.return_value = MagicMock(spec=[])   # no .json() — triggers fallback path
    ap.restore.return_value = MagicMock(spec=[])
    ap.delete.return_value = MagicMock(spec=[])
    ap.trashed.return_value = pd.DataFrame()

    # download
    ap.download.return_value = None

    # upload
    ap.upload.return_value = [{"name": "photo.jpg", "status": "uploaded"}]

    return ap


@pytest.fixture(autouse=True)
def patch_client(mock_ap: MagicMock) -> None:
    """Inject mock_ap as the global _client for every test."""
    with patch("amazon_photos_mcp._client", mock_ap):
        yield
