"""FastMCP server instantiation and tool annotations."""

from fastmcp import FastMCP

mcp = FastMCP("amazon-photos")

# ---------------------------------------------------------------------------
# Tool annotations per MCP 2025-11-25 spec
# ---------------------------------------------------------------------------
_READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "check_connection",
        "refresh_client",
        "validate_cookies",
        "get_storage_usage",
        "get_aggregations",
        "search_photos",
        "get_photos",
        "get_videos",
        "search_by_date",
        "search_by_things",
        "get_photo_url",
        "get_exif_data",
        "list_folders",
        "get_folder_tree",
        "list_albums",
        "list_people",
        "search_by_person",
        "find_duplicates",
        "preview_duplicate_group",
        "find_near_duplicates",
        "check_db_integrity",
        "get_library_stats",
        "export_metadata",
        "find_timeline_gaps",
        "get_thumbnail",
        "get_download_progress",
        "advanced_search",
    }
)

_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "permanently_delete",
        "trash_items",
        "trash_duplicates",
        "trash_near_duplicates",
        "keep_specific",
        "merge_people",
    }
)

_IDEMPOTENT_TOOLS: frozenset[str] = frozenset(
    {
        "create_album",
        "add_to_album",
        "remove_from_album",
        "set_favorite",
        "favorite_items",
        "unfavorite_items",
        "set_hidden",
        "hide_items",
        "unhide_items",
        "name_person",
        "restore_items",
        "upload_file",
        "upload_folder",
        "list_trashed",
        "list_recently_deleted",
        "download",
        "download_files",
        "download_by_date",
        "download_for_pipeline",
        "download_library",
    }
)


def _tool_annotations(tool_name: str) -> dict[str, bool]:
    """Return MCP tool annotations for the given tool name."""
    annotations: dict[str, bool] = {}
    if tool_name in _READ_ONLY_TOOLS:
        annotations["readOnlyHint"] = True
    if tool_name in _DESTRUCTIVE_TOOLS:
        annotations["destructiveHint"] = True
    if tool_name in _IDEMPOTENT_TOOLS:
        annotations["idempotentHint"] = True
    return annotations
