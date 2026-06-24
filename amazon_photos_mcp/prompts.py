"""MCP Prompts for Amazon Photos."""

from amazon_photos_mcp.server import mcp


@mcp.prompt("analyze-vacation")
def analyze_vacation_prompt() -> str:
    """Provide a prompt to analyze recent vacation photos."""
    return (
        "Please use the `search_photos` tool to find the last 50 photos. "
        "Analyze the EXIF metadata to determine the likely locations, dates, "
        "and content. Then, write a short summary of my recent trips or "
        "vacations based entirely on this data."
    )


@mcp.prompt("cleanup-duplicates")
def cleanup_duplicates_prompt() -> str:
    """Provide a prompt to find and clean up duplicates."""
    return (
        "Please run `find_duplicates` or `find_near_duplicates`. "
        "Review the resulting groups, looking at the file sizes and dimensions. "
        "Suggest which duplicate to keep (preferring the higher resolution or "
        "larger file size) and propose calling `trash_duplicates` for the rest."
    )
