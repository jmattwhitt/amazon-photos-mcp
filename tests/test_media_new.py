from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from amazon_photos_mcp.tools.media import download_library


@patch("amazon_photos_mcp.tools.media._get_client")
@pytest.mark.asyncio
async def test_download_library_batching(mock_get_client):
    mock_ap = MagicMock()
    # Create 300 items to test batching (batch size is 200)
    items = [{"id": f"node{i}", "createdDate": "2024-01-01T00:00:00Z"} for i in range(300)]
    mock_ap.photos.return_value = items
    mock_get_client.return_value = mock_ap

    # Mock download to succeed
    async def mock_download(ids, out):
        return [{"node_id": nid, "status": "ok"} for nid in ids]
    mock_ap.download.side_effect = mock_download

    # We need to run it dry_run=False but output to a temp dir so we don't mess up the disk
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = await download_library(output_dir=tmp_dir, max_items=5000, organize_by="flat", dry_run=False)

        # Should be called twice (300 items / 200 batch)
        assert mock_ap.download.call_count == 2
        assert res["downloaded"] == 300
        assert res["total_found"] == 300

    # Ensure dry_run works
    res_dry = await download_library(output_dir="/tmp/test", max_items=5000, organize_by="flat", dry_run=True)
    assert isinstance(res_dry, dict)
    pass
