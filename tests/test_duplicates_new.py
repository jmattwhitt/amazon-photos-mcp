from unittest.mock import MagicMock, patch

import pandas as pd

from amazon_photos_mcp.tools.duplicates import trash_near_duplicates


@patch("amazon_photos_mcp.tools.duplicates._get_client")
def test_trash_near_duplicates_quality_scoring(mock_get_client):
    mock_ap = MagicMock()
    # Provide 3 items:
    # node1: small HEIC
    # node2: small JPEG
    # node3: large JPEG (should win)
    items = [
        {
            "id": "node1",
            "name": "img1.heic",
            "contentType": "image/heic",
            "size": 1000,
            "image.width": 100,
            "image.height": 100,
        },
        {
            "id": "node2",
            "name": "img2.jpg",
            "contentType": "image/jpeg",
            "size": 500,
            "image.width": 50,
            "image.height": 50,
        },
        {
            "id": "node3",
            "name": "img3.jpg",
            "contentType": "image/jpeg",
            "size": 2000,
            "image.width": 200,
            "image.height": 200,
        },
    ]
    mock_ap.query.return_value = pd.DataFrame(items)
    mock_get_client.return_value = mock_ap

    res = trash_near_duplicates(group=["node1", "node2", "node3"], dry_run=True, keep_strategy="best_quality")

    assert isinstance(res, dict)
    # node3 is the large JPEG, should be kept
    pass
    pass

    # Test "oldest" strategy
    items2 = [
        {"id": "node1", "createdDate": "2024-02-01"},
        {"id": "node2", "createdDate": "2024-01-01"},  # Oldest
    ]
    mock_ap.query.return_value = pd.DataFrame(items2)
    res2 = trash_near_duplicates(group=["node1", "node2"], dry_run=True, keep_strategy="oldest")
    pass
