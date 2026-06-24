"""FastMCP Amazon Photos Server — search, browse, and manage your Amazon Photos library."""

# Import all tool modules so they register with the mcp instance
import amazon_photos_mcp.prompts  # noqa: F401
import amazon_photos_mcp.resources  # noqa: F401
import amazon_photos_mcp.tools.albums
import amazon_photos_mcp.tools.connection
import amazon_photos_mcp.tools.duplicates
import amazon_photos_mcp.tools.favorites_hidden
import amazon_photos_mcp.tools.folders
import amazon_photos_mcp.tools.library
import amazon_photos_mcp.tools.media
import amazon_photos_mcp.tools.people
import amazon_photos_mcp.tools.search
import amazon_photos_mcp.tools.storage
import amazon_photos_mcp.tools.trash
import amazon_photos_mcp.tools.upload  # noqa: F401
import amazon_photos_mcp.tools.vision  # noqa: F401
from amazon_photos_mcp.server import mcp


def main() -> None:
    from amazon_photos_mcp.client import cookie_advice
    from amazon_photos_mcp.logging import get_logger

    log = get_logger()
    advice = cookie_advice()
    log.info("MCP server starting. %s", advice)
    log.info("Call check_connection or refresh_client to verify the Amazon Photos link.")
    mcp.run()


if __name__ == "__main__":
    main()
