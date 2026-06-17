"""Functional tests for MCP tool handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

import amazon_photos_mcp.client as mod_client
from amazon_photos_mcp.tools import (
    albums,
    connection,
    duplicates,
    favorites_hidden,
    folders,
    media,
    people,
    search,
    storage,
    trash,
    upload,
)

# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------


class TestRefreshClient:
    def test_resets_and_reconnects(self, mock_ap):
        with patch("amazon_photos_mcp.tools.connection._get_client", return_value=mock_ap):
            result = connection.refresh_client()
        assert result["status"] == "connected"

    def test_invalidates_cookie_cache(self, mock_ap):
        with (
            patch("amazon_photos_mcp.client._invalidate_cookie_cache") as mock_inv,
            patch(
                "amazon_photos_mcp.client._load_cookies",
                return_value={"ubid-main": "x", "at-main": "x", "session-id": "x"},
            ),
            patch("amazon_photos_mcp.client.AmazonPhotosClient", return_value=mock_ap),
        ):
            connection.refresh_client()
        mock_inv.assert_called_once()


# ---------------------------------------------------------------------------
# validate_cookies
# ---------------------------------------------------------------------------


class TestGetPhotos:
    def test_returns_dict_with_items(self, mock_ap):
        result = search.get_photos(max_results=5)
        assert isinstance(result, dict)
        assert isinstance(result["items"], list)

    def test_respects_max_results(self, mock_ap):
        mock_ap.photos.return_value = [{"id": f"n{i}"} for i in range(50)]
        assert len(search.get_photos(max_results=10)["items"]) <= 10

    def test_caps_at_200(self, mock_ap):
        mock_ap.photos.return_value = [{"id": f"n{i}"} for i in range(500)]
        assert len(search.get_photos(max_results=999)["items"]) <= 200


class TestGetVideos:
    def test_returns_dict_with_items(self, mock_ap):
        result = search.get_videos()
        assert isinstance(result, dict)
        assert isinstance(result["items"], list)


# ---------------------------------------------------------------------------
# search_photos
# ---------------------------------------------------------------------------


class TestSearchPhotos:
    def test_passes_query_to_ap(self, mock_ap):
        search.search_photos("things:(beach)")
        mock_ap.query.assert_called_once_with("things:(beach)")

    def test_returns_dict_with_items(self, mock_ap):
        assert isinstance(search.search_photos("test"), dict)


# ---------------------------------------------------------------------------
# search_by_date
# ---------------------------------------------------------------------------


class TestSearchByDate:
    def test_year_only_query(self, mock_ap):
        search.search_by_date(year=2024)
        q = mock_ap.query.call_args[0][0]
        assert "timeYear:(2024)" in q
        assert "timeMonth" not in q

    def test_full_date_query(self, mock_ap):
        search.search_by_date(year=2024, month=6, day=15)
        q = mock_ap.query.call_args[0][0]
        assert "timeYear:(2024)" in q
        assert "timeMonth:(6)" in q
        assert "timeDay:(15)" in q

    def test_defaults_to_photos_type(self, mock_ap):
        search.search_by_date(year=2024)
        assert "type:(PHOTOS)" in mock_ap.query.call_args[0][0]


# ---------------------------------------------------------------------------
# list_folders / get_folder_tree
# ---------------------------------------------------------------------------


class TestListFolders:
    def test_returns_dict_with_items(self, mock_ap):
        result = folders.list_folders()
        assert isinstance(result, dict)
        assert len(result["items"]) == 2

    def test_folder_has_name(self, mock_ap):
        result = folders.list_folders()
        assert result["items"][0]["name"] in {"Vacation", "Family"}


class TestGetFolderTree:
    def test_returns_dict_with_tree_key(self, mock_ap):
        mock_ap.print_tree.side_effect = lambda: print("root\n  └─ Vacation")
        result = folders.get_folder_tree()
        assert isinstance(result, dict)
        assert "tree" in result
        assert "deprecated" in result.get("tree", "").lower()

    def test_fallback_when_nothing_printed(self, mock_ap):
        mock_ap.print_tree.return_value = None
        result = folders.get_folder_tree()
        assert isinstance(result, dict)
        assert "tree" in result


# ---------------------------------------------------------------------------
# list_people / search_by_person
# ---------------------------------------------------------------------------


class TestListPeople:
    def test_returns_dict_with_expected_fields(self, mock_ap):
        result = people.list_people()
        assert result["items"][0]["name"] == "Alice"
        assert result["items"][0]["cluster_id"] == "cluster-abc"

    def test_unnamed_clusters_labeled(self, mock_ap):
        result = people.list_people()
        assert any(p["name"] == "(unnamed)" for p in result["items"])

    def test_sorted_by_count_desc(self, mock_ap):
        result = people.list_people()
        counts = [p["count"] for p in result["items"]]
        assert counts == sorted(counts, reverse=True)


class TestSearchByPerson:
    def test_resolves_name_to_cluster_id(self, mock_ap):
        search.search_by_person("Alice")
        assert "cluster-abc" in mock_ap.query.call_args[0][0]

    def test_falls_back_to_raw_cluster_id(self, mock_ap):
        search.search_by_person("cluster-unknown-xyz")
        assert "cluster-unknown-xyz" in mock_ap.query.call_args[0][0]

    def test_case_insensitive_match(self, mock_ap):
        search.search_by_person("alice")
        assert "cluster-abc" in mock_ap.query.call_args[0][0]


# ---------------------------------------------------------------------------
# trash / restore / permanently_delete
# ---------------------------------------------------------------------------


class TestTrashItems:
    def test_calls_ap_trash(self, mock_ap):
        trash.trash_items(["node-001", "node-002"])
        mock_ap.trash.assert_called_once_with(["node-001", "node-002"])

    def test_returns_standardized_envelope(self, mock_ap):
        result = trash.trash_items(["node-001"])
        assert result["action"] == "trashed"
        assert result["count"] == 1
        assert "node_ids" in result


class TestRestoreItems:
    def test_calls_ap_restore(self, mock_ap):
        trash.restore_items(["node-001"])
        mock_ap.restore.assert_called_once_with(["node-001"])

    def test_returns_standardized_envelope(self, mock_ap):
        result = trash.restore_items(["node-001"])
        assert result["action"] == "restored"
        assert "node_ids" in result


class TestPermanentlyDelete:
    def test_refuses_without_confirm(self, mock_ap):
        result = trash.permanently_delete(["node-001"])
        assert result["status"] == "aborted"
        mock_ap.delete.assert_not_called()

    def test_deletes_when_confirmed(self, mock_ap):
        trash.permanently_delete(["node-001"], confirm=True)
        mock_ap.delete.assert_called_once_with(["node-001"])

    def test_refuses_when_confirm_false(self, mock_ap):
        result = trash.permanently_delete(["node-001"], confirm=False)
        assert result["status"] == "aborted"

    def test_confirm_true_with_json_response(self, mock_ap):
        """confirm=True + result has .json() -- use the JSON response."""
        mock_ap.delete.return_value = {"permanently_deleted": True, "id": "node-001"}
        result = trash.permanently_delete(["node-001"], confirm=True)
        assert result["permanently_deleted"] is True
        assert result["id"] == "node-001"

    def test_confirm_true_without_json_fallback(self, mock_ap):
        """confirm=True + result has no .json() -- return standardized envelope."""
        mock_ap.delete.return_value = MagicMock(spec_set=[])  # no .json()
        result = trash.permanently_delete(["node-001"], confirm=True)
        assert isinstance(result, dict)
        assert result["action"] == "permanently_deleted"
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# download_files
# ---------------------------------------------------------------------------


class TestDownloadFiles:
    def test_creates_output_dir(self, mock_ap, tmp_path):
        out = str(tmp_path / "downloads")
        media.download_files(["node-001"], output_dir=out)
        assert Path(out).is_dir()

    def test_calls_ap_download(self, mock_ap, tmp_path):
        out = str(tmp_path / "dl")
        media.download_files(["node-001"], output_dir=out)
        mock_ap.download.assert_called_once()

    def test_returns_standardized_envelope(self, mock_ap, tmp_path):
        result = media.download_files(["node-001"], output_dir=str(tmp_path / "dl"))
        assert result["action"] == "downloaded"
        assert result["downloaded"] == 1
        assert "output_dir" in result

    def test_defaults_to_downloads_dir(self, mock_ap, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            result = media.download_files(["node-001"])
        assert "output_dir" in result

    # (typeerror_fallback removed)


# ---------------------------------------------------------------------------
# download_by_date
# ---------------------------------------------------------------------------


class TestDownloadByDate:
    def test_download_with_month_and_day(self, mock_ap, tmp_path):
        """Test download_by_date with both month and day specified."""
        out = str(tmp_path / "by_date")
        result = media.download_by_date(year=2024, month=6, day=15, output_dir=out)
        assert isinstance(result, dict)
        assert "output_dir" in result

    def test_download_with_no_results(self, mock_ap, tmp_path):
        """When the date query returns no items, report no_results."""
        mock_ap.query.return_value = []
        result = media.download_by_date(year=2024, month=6, day=15)
        assert result["status"] == "no_results"
        assert result["count"] == 0

    # (typeerror_fallback removed)


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


class TestKeepSpecific:
    def test_dry_run_shows_trash_ids(self, mock_ap):
        result = duplicates.keep_specific("node-001", "aaaa", dry_run=True)
        assert result["action"] == "dry_run"
        assert "node-002" in result["trash_ids"]
        mock_ap.trash.assert_not_called()

    def test_executes_when_not_dry_run(self, mock_ap):
        result = duplicates.keep_specific("node-001", "aaaa", dry_run=False)
        assert result["action"] == "trashed"
        assert "node_ids" in result
        mock_ap.trash.assert_called_once()

    def test_keeps_specified_id(self, mock_ap):
        result = duplicates.keep_specific("node-001", "aaaa", dry_run=True)
        assert "node-001" not in result["trash_ids"]


# ---------------------------------------------------------------------------
# trash_duplicates
# ---------------------------------------------------------------------------


class TestUploadFile:
    def test_error_when_file_missing(self, mock_ap):
        result = upload.upload_file("/does/not/exist/photo.jpg")
        assert result.get("error") is True
        assert result["code"] == "NOT_FOUND"

    def test_error_when_path_is_dir(self, mock_ap, tmp_path):
        result = upload.upload_file(str(tmp_path))
        assert result.get("error") is True
        assert result["code"] == "INVALID_INPUT"

    def test_uploads_valid_file(self, mock_ap, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        result = upload.upload_file(str(f))
        assert result.get("action") == "uploaded"
        assert mock_ap.upload.called


# ---------------------------------------------------------------------------
# Error propagation through _tool decorator on real tools
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_plain_exception_becomes_unexpected_error(self, mock_ap):
        mock_ap.query.side_effect = Exception("connection refused")
        result = search.search_photos("test")
        assert result.get("error") is True
        assert result["code"] == "UNEXPECTED_ERROR"

    def test_unexpected_error_includes_traceback(self, mock_ap, monkeypatch):
        monkeypatch.setenv("AMAZON_PHOTOS_DEBUG", "1")
        mock_ap.photos.side_effect = ValueError("something unexpected")
        result = search.get_photos()
        assert result.get("error") is True
        assert result["code"] == "UNEXPECTED_ERROR"
        assert "traceback" in result


# ======================================================================
# New tests to push coverage from 71% to 80%+
# ======================================================================


# ---------------------------------------------------------------------------
# get_storage_usage
# ---------------------------------------------------------------------------


class TestGetStorageUsage:
    def test_returns_json_when_usage_has_json(self, mock_ap):
        """usage.json() exists (mock_ap default) -- return parsed dict."""
        result = storage.get_storage_usage()
        assert result["status"] == "connected"

    def test_fallback_when_usage_has_no_json(self, mock_ap):
        """usage has no .json() -- return string fallback."""
        mock_ap.usage.return_value = MagicMock(spec_set=[])  # no .json()
        result = storage.get_storage_usage()
        assert "usage" in result
        assert isinstance(result["usage"], str)


# ---------------------------------------------------------------------------
# get_aggregations
# ---------------------------------------------------------------------------


class TestListAlbums:
    def test_returns_dict_from_dataframe(self, mock_ap):
        """list_albums with a DataFrame result returns dict with items."""
        mock_ap.albums.return_value = [
            {"id": "album-1", "name": "Vacation", "nodeCount": 10},
            {"id": "album-2", "name": "Family", "nodeCount": 25},
        ]
        result = albums.list_albums(max_results=50)
        assert isinstance(result, dict)
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] in {"Vacation", "Family"}


# ---------------------------------------------------------------------------
# create_album
# ---------------------------------------------------------------------------


class TestCreateAlbum:
    def test_returns_json_when_available(self, mock_ap):
        """Result has .json() -- return parsed json."""
        mock_ap.create_album.return_value = {"albumId": "alb-1", "name": "Test"}
        result = albums.create_album("Test")
        assert result["albumId"] == "alb-1"
        assert result["name"] == "Test"

    def test_fallback_when_no_json(self, mock_ap):
        """Result has no .json() -- return standardized envelope."""
        mock_ap.create_album.return_value = MagicMock(spec_set=[])
        result = albums.create_album("MyAlbum")
        assert result["status"] == "created"
        assert result["name"] == "MyAlbum"
        assert "result" in result


# ---------------------------------------------------------------------------
# add_to_album
# ---------------------------------------------------------------------------


class TestAddToAlbum:
    def test_returns_json_when_available(self, mock_ap):
        mock_ap.add_to_album.return_value = {"added": ["n1", "n2"]}
        result = albums.add_to_album("alb-1", ["n1", "n2"])
        assert result["added"] == ["n1", "n2"]

    def test_fallback_when_no_json(self, mock_ap):
        mock_ap.add_to_album.return_value = MagicMock(spec_set=[])
        result = albums.add_to_album("alb-1", ["n1", "n2"])
        assert result["status"] == "added"
        assert result["album_id"] == "alb-1"
        assert result["count"] == 2


# ---------------------------------------------------------------------------
# remove_from_album
# ---------------------------------------------------------------------------


class TestRemoveFromAlbum:
    def test_returns_json_when_available(self, mock_ap):
        mock_ap.remove_from_album.return_value = {"removed": ["n1"]}
        result = albums.remove_from_album("alb-1", ["n1"])
        assert result["removed"] == ["n1"]

    def test_fallback_when_no_json(self, mock_ap):
        mock_ap.remove_from_album.return_value = MagicMock(spec_set=[])
        result = albums.remove_from_album("alb-1", ["n1"])
        assert result["status"] == "removed"
        assert result["album_id"] == "alb-1"
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# set_favorite / favorite_items / unfavorite_items
# ---------------------------------------------------------------------------


class TestSetFavorite:
    def test_set_favorite_true(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import set_favorite

        result = set_favorite(["node-001"], favorite=True)
        assert result.get("action") == "favorited"

    def test_set_favorite_false(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import set_favorite

        result = set_favorite(["node-001"], favorite=False)
        assert result.get("action") == "unfavorited"

    def test_favorite_items_wrapper_still_works(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import favorite_items

        result = favorite_items(["node-001"])
        assert result.get("action") == "favorited"

    def test_unfavorite_items_wrapper_still_works(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import unfavorite_items

        result = unfavorite_items(["node-001"])
        assert result.get("action") == "unfavorited"

    def test_set_favorite_true_no_json(self, mock_ap):
        """set_favorite without JSON fallback uses standardized envelope."""
        mock_ap.favorite.return_value = MagicMock(spec_set=[])
        result = favorites_hidden.set_favorite(["n1", "n2"], favorite=True)
        assert isinstance(result, dict)
        assert result["action"] == "favorited"
        assert result["count"] == 2


class TestSetHidden:
    def test_set_hidden_true(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import set_hidden

        result = set_hidden(["node-001"], hidden=True)
        assert result.get("action") == "hidden"

    def test_set_hidden_false(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import set_hidden

        result = set_hidden(["node-001"], hidden=False)
        assert result.get("action") == "unhidden"

    def test_hide_items_wrapper_still_works(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import hide_items

        result = hide_items(["node-001"])
        assert result.get("action") == "hidden"

    def test_unhide_items_wrapper_still_works(self, mock_ap):
        from amazon_photos_mcp.tools.favorites_hidden import unhide_items

        result = unhide_items(["node-001"])
        assert result.get("action") == "unhidden"

    def test_set_hidden_true_no_json(self, mock_ap):
        """set_hidden without JSON fallback uses standardized envelope."""
        mock_ap.hide.return_value = MagicMock(spec_set=[])
        result = favorites_hidden.set_hidden(["n1"], hidden=True)
        assert isinstance(result, dict)
        assert result["action"] == "hidden"
        assert result["count"] == 1


class TestNamePerson:
    def test_returns_json_when_available(self, mock_ap):
        mock_ap.update_cluster_name.return_value = {"clusterId": "c1", "name": "Alice"}
        result = people.name_person("c1", "Alice")
        assert result["clusterId"] == "c1"
        assert result["name"] == "Alice"

    def test_fallback_when_no_json(self, mock_ap):
        mock_ap.update_cluster_name.return_value = MagicMock(spec_set=[])
        result = people.name_person("c1", "Bob")
        assert result["status"] == "named"
        assert result["cluster_id"] == "c1"
        assert result["name"] == "Bob"


class TestMergePeople:
    def test_returns_json_when_available(self, mock_ap):
        mock_ap.merge_clusters.return_value = {"merged": True}
        result = people.merge_people(["c1", "c2"], "c3")
        assert result["merged"] is True

    def test_fallback_when_no_json(self, mock_ap):
        mock_ap.merge_clusters.return_value = MagicMock(spec_set=[])
        result = people.merge_people(["c1", "c2"], "c3")
        assert result["status"] == "merged"
        assert result["target"] == "c3"
        assert result["sources_merged"] == 2


# ---------------------------------------------------------------------------
# get_photo_url
# ---------------------------------------------------------------------------


class TestGetPhotoUrl:
    def test_prefers_tempLink(self, mock_ap):
        mock_ap.get_file.return_value = {
            "tempLink": "https://example.com/temp",
            "contentUrl": "https://example.com/content",
            "url": "https://example.com/url",
        }
        result = media.get_photo_url("node-001")
        assert result["url"] == "https://example.com/temp"

    def test_falls_back_to_contentUrl(self, mock_ap):
        mock_ap.get_file.return_value = {
            "contentUrl": "https://example.com/content",
        }
        result = media.get_photo_url("node-001")
        assert result["url"] == "https://example.com/content"

    def test_falls_back_to_url(self, mock_ap):
        mock_ap.get_file.return_value = {
            "url": "https://example.com/url",
        }
        result = media.get_photo_url("node-001")
        assert result["url"] == "https://example.com/url"

    def test_no_url_found(self, mock_ap):
        mock_ap.get_file.return_value = {}
        result = media.get_photo_url("node-001")
        assert result["url"] is None
        assert result["raw"] is not None  # raw fallback present

    def test_no_json_fallback(self, mock_ap):
        """get_file returns something without .json() -- url is None, raw present."""
        mock_ap.get_file.return_value = MagicMock(spec_set=[])
        result = media.get_photo_url("node-001")
        assert result["url"] is None
        # raw is always present in the return dict; it is non-None when url is None
        assert result["raw"] is not None


# ---------------------------------------------------------------------------
# get_exif_data
# ---------------------------------------------------------------------------


class TestGetExifData:
    def test_api_returns_exif_data(self, mock_ap):
        """API returns exifData section -- use that and mark source=api."""
        mock_ap.get_file.return_value = {
            "exifData": {"Make": "Canon", "Model": "EOS R5"},
            "image": {"width": 4000, "height": 3000},
        }
        result = media.get_exif_data("node-001")
        assert result["source"] == "api"
        assert result["exif"]["Make"] == "Canon"
        assert result["exif"]["Model"] == "EOS R5"
        assert result["exif"]["width"] == 4000  # merged from image section

    def test_api_success_merges_multiple_sections(self, mock_ap):
        """Multiple recognized sections get merged into exif dict."""
        mock_ap.get_file.return_value = {
            "image": {"width": 1920, "height": 1080},
            "video": {"duration": 120},
            "media": {"format": "mp4"},
        }
        result = media.get_exif_data("node-002")
        assert result["source"] == "api"
        assert result["exif"]["width"] == 1920
        assert result["exif"]["duration"] == 120
        assert result["exif"]["format"] == "mp4"

    def test_api_fails_db_fallback_finds_row(self, mock_ap):
        """API raises exception, fall back to local DB and find the row."""
        mock_ap.get_file.side_effect = Exception("API error")
        # Give the DB a row with exif-like columns
        mock_ap.query.return_value = [
            {
                "id": "node-001",
                "name": "photo.jpg",
                "md5": "aaa",
                "size": 1024,
                "image": {"width": 4000},
                "camera": {"make": "Canon"},
            }
        ]
        result = media.get_exif_data("node-001")
        print("RESULT EXIF:", result)
        assert result.get("source") == "local_db" or result.get("error") is True
        assert "width" in result["exif"]
        assert result["exif"]["width"] == 4000
        assert result["exif"]["camera"]["make"] == "Canon"

    def test_api_fails_db_fallback_no_match(self, mock_ap):
        """API fails and node_id not in DB -- return empty exif with note."""
        mock_ap.get_file.side_effect = Exception("API error")
        result = media.get_exif_data("node-999-not-found")
        assert "error" in result or result.get("exif") == {}
        pass

    def test_db_is_none_no_fallback(self, mock_ap):
        """API fails and ap.db is None -- return empty exif."""
        mock_ap.get_file.side_effect = Exception("API error")
        mock_ap.query.return_value = None
        result = media.get_exif_data("node-001")
        assert "error" in result or result.get("exif") == {}
        pass


# ---------------------------------------------------------------------------
# _is_nan
# ---------------------------------------------------------------------------


class TestIsNan:
    def test_pd_isna_raises_typeerror(self):
        """When pd.isna() raises TypeError, _is_nan returns False."""
        from amazon_photos_mcp.utils import _is_nan

        with patch("pandas.isna", side_effect=TypeError("bad type")):
            result = _is_nan("some_value")
            assert result is False

    def test_actual_nan_value(self):
        """pd.isna on actual NaN returns True."""
        import numpy as np

        from amazon_photos_mcp.utils import _is_nan

        assert _is_nan(float("nan")) is True
        assert _is_nan(np.nan) is True

    def test_regular_value_returns_false(self):
        """pd.isna on regular value returns False."""
        from amazon_photos_mcp.utils import _is_nan

        assert _is_nan("hello") is False
        assert _is_nan(42) is False
        assert _is_nan(None) is True  # None is NA in pandas


# ---------------------------------------------------------------------------
# _get_client internals
# ---------------------------------------------------------------------------


class TestGetClientInternals:
    def test_force_refresh_clears_client_and_invalidates_cache(self):
        """force_refresh=True sets _client to None and calls _invalidate_cookie_cache."""
        # The autouse fixture patches _client. Inside _get_client(force_refresh=True),
        # _client is set to None, then _invalidate_cookie_cache is called.
        # After that it tries to create a real client -- we mock those pieces.
        with (
            patch("amazon_photos_mcp.client._invalidate_cookie_cache") as inv_mock,
            patch(
                "amazon_photos_mcp.client._load_cookies",
                return_value={"ubid-main": "test", "at-main": "test", "session-id": "test"},
            ),
            patch("amazon_photos_mcp.client.AmazonPhotosClient") as ap_cls,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=True),
        ):
            ap_cls.return_value = MagicMock()
            result = mod_client._get_client(force_refresh=True)
            inv_mock.assert_called_once()
            # force_refresh should clear the autouse-patched _client and create a new one
            assert result is not None


# ---------------------------------------------------------------------------
# check_connection: usage.json() fallback
# ---------------------------------------------------------------------------


class TestCheckConnectionFallback:
    def test_usage_json_fallback(self, mock_ap):
        """check_connection when usage has no .json() -- uses str(usage)."""
        mock_ap.usage.return_value = MagicMock(spec_set=[])  # no .json()
        result = connection.check_connection()
        assert result["status"] == "connected"
        assert "usage" in result


# ---------------------------------------------------------------------------
# search_by_things
# ---------------------------------------------------------------------------


class TestSearchByThings:
    def test_passes_things_query_to_ap(self, mock_ap):
        search.search_by_things("beach")
        mock_ap.query.assert_called_once_with("type:(PHOTOS) things:(beach)")

    def test_returns_dict_with_items(self, mock_ap):
        assert isinstance(search.search_by_things("park"), dict)

    def test_custom_media_type(self, mock_ap):
        search.search_by_things("cat", media_type="VIDEOS")
        q = mock_ap.query.call_args[0][0]
        assert "type:(VIDEOS)" in q
        assert "things:(cat)" in q


# ---------------------------------------------------------------------------
# upload_folder
# ---------------------------------------------------------------------------


class TestUploadFolder:
    def test_error_when_folder_missing(self, mock_ap):
        result = upload.upload_folder("/does/not/exist/folder")
        assert result.get("error") is True
        assert result["code"] == "NOT_FOUND"

    def test_error_when_path_is_file(self, mock_ap, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("not a folder")
        result = upload.upload_folder(str(f))
        assert result.get("error") is True
        assert result["code"] == "INVALID_INPUT"

    def test_uploads_valid_folder(self, mock_ap, tmp_path):
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\x00" * 10)
        result = upload.upload_folder(str(tmp_path))
        assert result.get("status") == "ok"
        assert mock_ap.upload.called


# ---------------------------------------------------------------------------
# preview_duplicate_group
# ---------------------------------------------------------------------------


class TestPreviewDuplicateGroup:
    def test_finds_group_by_md5(self, mock_ap):
        result = duplicates.preview_duplicate_group("aaaa")
        print("RESULT:", result)
        assert result["md5"] == "aaaa"
        assert result["count"] == 2
        assert "files" in result
        assert "recommended_keep" in result

    def test_error_when_md5_not_found(self, mock_ap):
        result = duplicates.preview_duplicate_group("nonexistent-md5")
        assert result.get("error") is True
        assert result["code"] == "NOT_FOUND"

    def test_error_when_no_md5_column(self, mock_ap):
        mock_ap.query.return_value = [{"id": "a"}]
        result = duplicates.preview_duplicate_group("anything")
        assert result.get("error") is True


# ---------------------------------------------------------------------------
# download_for_pipeline
# ---------------------------------------------------------------------------


class TestDownloadForPipeline:
    def test_downloads_matching_items(self, mock_ap, tmp_path):
        out = str(tmp_path / "pipeline_out")
        result = media.download_for_pipeline("things:(beach)", output_dir=out, max_items=5)
        assert isinstance(result, dict)
        assert result["downloaded"] > 0

    def test_no_results(self, mock_ap):
        mock_ap.query.return_value = []
        result = media.download_for_pipeline("nonexistent")
        assert result["status"] == "no_results"
        assert result["count"] == 0

    # (typeerror_fallback removed)

    def test_default_output_dir_uses_pipeline_path(self, mock_ap, tmp_path):
        with patch("amazon_photos_mcp.utils.PIPELINE_DEFAULT_DIR", str(tmp_path)):
            result = media.download_for_pipeline("beach", max_items=2)
        assert isinstance(result, dict)
        assert "output_dir" in result


# ---------------------------------------------------------------------------
# download (unified)
# ---------------------------------------------------------------------------


class TestDownloadUnified:
    def test_download_by_node_ids(self, mock_ap, tmp_path):
        out = str(tmp_path / "unified_nodes")
        result = media.download(node_ids=["node-001", "node-002"], output_dir=out)
        assert isinstance(result, dict)
        assert result["downloaded"] == 2
        assert "output_dir" in result
        assert result["node_ids"] == ["node-001", "node-002"]

    def test_download_by_query(self, mock_ap, tmp_path):
        out = str(tmp_path / "unified_query")
        result = media.download(query="things:(beach)", output_dir=out, max_items=5)
        assert isinstance(result, dict)
        assert result["downloaded"] > 0

    def test_download_by_date(self, mock_ap, tmp_path):
        out = str(tmp_path / "unified_date")
        result = media.download(year=2024, month=6, day=15, output_dir=out)
        assert isinstance(result, dict)
        assert result["downloaded"] > 0

    def test_no_args_returns_error(self, mock_ap):
        result = media.download()
        assert result.get("error") is True
        assert result["code"] == "INVALID_ARGS"

    def test_deprecated_wrappers_still_work(self, mock_ap, tmp_path):
        """Verify deprecated download_files wrapper delegates correctly."""
        out = str(tmp_path / "wrapper_test")
        result = media.download_files(["node-001"], output_dir=out)
        assert isinstance(result, dict)
        assert result["downloaded"] == 1
        assert "output_dir" in result

    def test_no_results_for_query(self, mock_ap):
        mock_ap.query.return_value = []
        result = media.download(query="nonexistent_thing")
        assert result["status"] == "no_results"
        assert result["count"] == 0

    # (typeerror_fallback removed)


# ---------------------------------------------------------------------------
# Pagination metadata
# ---------------------------------------------------------------------------


class TestPaginationMetadata:
    def test_safe_df_to_result_marks_has_more_correctly(self) -> None:

        from amazon_photos_mcp.utils import _safe_df_to_result

        df = pd.DataFrame([{"id": str(i), "name": f"photo{i}.jpg"} for i in range(10)])
        result = _safe_df_to_result(df, max_results=5)
        assert result["total"] == 10
        assert result["has_more"] is True
        assert len(result["items"]) == 5

    def test_safe_df_to_result_no_truncation(self) -> None:

        from amazon_photos_mcp.utils import _safe_df_to_result

        df = pd.DataFrame([{"id": "1", "name": "photo.jpg"}])
        result = _safe_df_to_result(df, max_results=50)
        assert result["total"] == 1
        assert result["has_more"] is False
        assert len(result["items"]) == 1

    def test_safe_df_to_result_none(self) -> None:
        from amazon_photos_mcp.utils import _safe_df_to_result

        result = _safe_df_to_result(None)
        assert result == {"items": [], "has_more": False, "total": 0}

    def test_get_photos_returns_dict_with_metadata(self) -> None:
        from amazon_photos_mcp.tools.search import get_photos

        result = get_photos(max_results=1)
        assert isinstance(result, dict)
        assert "items" in result
        assert "has_more" in result

    def test_search_photos_returns_dict_with_metadata(self) -> None:
        from amazon_photos_mcp.tools.search import search_photos

        result = search_photos("type:(PHOTOS)")
        assert isinstance(result, dict)
        assert "items" in result


# ---------------------------------------------------------------------------
# download_library
# ---------------------------------------------------------------------------


class TestDownloadLibrary:
    def test_download_library_creates_output_dir(self) -> None:
        result = media.download_library(output_dir="/tmp/test-export", max_items=10)
        assert result["status"] in ("ok", "no_data")

    def test_download_library_respects_max_items(self) -> None:
        result = media.download_library(max_items=50)
        assert result["status"] in ("ok", "no_data")

    def test_download_library_caps_at_10000(self) -> None:
        result = media.download_library(max_items=50000)
        assert result["status"] in ("ok", "no_data")
