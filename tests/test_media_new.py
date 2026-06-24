from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from amazon_photos_mcp.tools.media import download_library


@patch("amazon_photos_mcp.tools.media._get_client")
@pytest.mark.asyncio
async def test_download_library_batching(mock_get_client):
    mock_ap = AsyncMock()
    items = [{"id": f"node{i}", "createdDate": "2024-01-01T00:00:00Z"} for i in range(300)]
    mock_ap.photos.return_value = items
    mock_get_client.return_value = mock_ap

    async def mock_download(ids, out):
        return [{"node_id": nid, "status": "ok"} for nid in ids]

    mock_ap.download.side_effect = mock_download

    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = await download_library(output_dir=tmp_dir, max_items=5000, organize_by="flat", dry_run=False)

        assert mock_ap.download.call_count == 2  # 300 items / 200 batch size
        assert res["downloaded"] == 300
        assert res["total_found"] == 300

    # Verify dry_run mode returns expected structure
    res_dry = await download_library(output_dir="/tmp/test", max_items=5000, organize_by="flat", dry_run=True)
    assert isinstance(res_dry, dict)
    assert res_dry["status"] == "dry_run"
