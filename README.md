# Amazon Photos MCP

[![CI](https://github.com/jmattwhitt/amazon-photos-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jmattwhitt/amazon-photos-mcp/actions/workflows/ci.yml)

MCP server for Amazon Photos — search, browse, upload, download, and manage your photo library through Claude or any MCP-compatible client.

41 tools covering: photo/video search with structured queries, face/person recognition, duplicate detection and cleanup, trash management, upload/download, album management, and storage analytics.

## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/jmattwhitt/amazon-photos-mcp.git
cd amazon-photos-mcp
uv sync
```

## Cookie Setup

Amazon Photos requires browser session cookies.

### Recommended: One-click browser extraction

```bash
uv run --extra scripts python scripts/get_cookies_easy.py
```

Opens a browser window to amazon.com/photos. Sign in, press Enter in the terminal, done. No copy-paste needed.

First run installs Chromium automatically (`playwright install chromium`).

### Alternative: Extract from Firefox

```bash
uv run --extra scripts python scripts/get_cookies.py --browser firefox
```

Firefox stores cookies in plain SQLite. Chrome/Edge cannot be decrypted automatically.

### Alternative: Manual DevTools

```bash
uv run --extra scripts python scripts/get_cookies.py --manual
```

Required cookies: `ubid-main`, `at-main`, `session-id`.
Cookies are saved to `~/.config/amazon-photos-mcp/cookies.json` and expire after ~72 hours.

## Configure Claude Code

```bash
claude mcp add --scope user amazon-photos -- uvx --from /path/to/amazon-photos-mcp amazon-photos-mcp
```

Then restart Claude Code. Call `check_connection` to verify.

## Tools

| Category | Tools |
|----------|-------|
| **Connection** | `check_connection`, `refresh_client`, `validate_cookies` |
| **Search** | `search_photos`, `search_by_date`, `search_by_things`, `search_by_person` |
| **Browse** | `get_photos`, `get_videos`, `get_photo_url`, `get_exif_data` |
| **Folders** | `list_folders`, `get_folder_tree` |
| **Albums** | `list_albums`, `create_album`, `add_to_album`, `remove_from_album` |
| **People** | `list_people`, `name_person`, `merge_people` |
| **Duplicates** | `find_duplicates`, `preview_duplicate_group`, `keep_specific`, `trash_duplicates` |
| **Trash** | `trash_items`, `list_trashed`, `list_recently_deleted`, `restore_items`, `permanently_delete` |
| **Transfer** | `upload_file`, `upload_folder`, `download_files`, `download_by_date`, `download_for_pipeline` |
| **Favorites** | `favorite_items`, `unfavorite_items` |
| **Visibility** | `hide_items`, `unhide_items` |
| **Storage** | `get_storage_usage`, `get_aggregations`, `check_db_integrity` |

## License

MIT — see [LICENSE](LICENSE).

## Dependencies

Uses the MIT-licensed [amazon-photos](https://github.com/trevorhobenshield/amazon_photos) library by Trevor Hobenshield for the Amazon Photos API client.
