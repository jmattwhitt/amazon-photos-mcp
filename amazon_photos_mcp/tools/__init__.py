"""Amazon Photos MCP tools — re-exported from individual modules."""

from amazon_photos_mcp.tools.connection import (
    check_connection,
    refresh_client,
    validate_cookies,
)
from amazon_photos_mcp.tools.storage import (
    get_aggregations,
    get_storage_usage,
)
from amazon_photos_mcp.tools.search import (
    advanced_search,
    get_photos,
    get_videos,
    search_by_date,
    search_by_person,
    search_by_things,
    search_photos,
)
from amazon_photos_mcp.tools.media import (
    download,
    download_by_date,
    download_files,
    download_for_pipeline,
    download_library,
    get_download_progress,
    get_exif_data,
    get_photo_url,
    get_thumbnail,
)
from amazon_photos_mcp.tools.albums import (
    add_to_album,
    create_album,
    list_albums,
    remove_from_album,
)
from amazon_photos_mcp.tools.folders import (
    get_folder_tree,
    list_folders,
)
from amazon_photos_mcp.tools.people import (
    list_people,
    merge_people,
    name_person,
)
from amazon_photos_mcp.tools.favorites_hidden import (
    favorite_items,
    hide_items,
    set_favorite,
    set_hidden,
    unfavorite_items,
    unhide_items,
)
from amazon_photos_mcp.tools.trash import (
    list_recently_deleted,
    list_trashed,
    permanently_delete,
    restore_items,
    trash_items,
)
from amazon_photos_mcp.tools.upload import (
    upload_file,
    upload_folder,
)
from amazon_photos_mcp.tools.duplicates import (
    find_duplicates,
    find_near_duplicates,
    keep_specific,
    preview_duplicate_group,
    trash_duplicates,
    trash_near_duplicates,
)
from amazon_photos_mcp.tools.library import (
    check_db_integrity,
    export_metadata,
    find_timeline_gaps,
    get_library_stats,
)

__all__ = [
    # Connection
    "check_connection",
    "refresh_client",
    "validate_cookies",
    # Storage
    "get_storage_usage",
    "get_aggregations",
    # Search
    "search_photos",
    "get_photos",
    "get_videos",
    "search_by_date",
    "search_by_things",
    "search_by_person",
    "advanced_search",
    # Media
    "get_photo_url",
    "get_exif_data",
    "get_thumbnail",
    "download",
    "download_files",
    "download_by_date",
    "download_for_pipeline",
    "download_library",
    "get_download_progress",
    # Albums
    "list_albums",
    "create_album",
    "add_to_album",
    "remove_from_album",
    # Folders
    "list_folders",
    "get_folder_tree",
    # People
    "list_people",
    "name_person",
    "merge_people",
    # Favorites/Hidden
    "set_favorite",
    "favorite_items",
    "unfavorite_items",
    "set_hidden",
    "hide_items",
    "unhide_items",
    # Trash
    "trash_items",
    "list_trashed",
    "list_recently_deleted",
    "restore_items",
    "permanently_delete",
    # Upload
    "upload_file",
    "upload_folder",
    # Duplicates
    "find_duplicates",
    "preview_duplicate_group",
    "find_near_duplicates",
    "keep_specific",
    "trash_duplicates",
    "trash_near_duplicates",
    # Library
    "check_db_integrity",
    "get_library_stats",
    "export_metadata",
    "find_timeline_gaps",
]
