"""Vision and image extraction tools."""

from __future__ import annotations

import io as stdlib_io
from typing import Annotated

from mcp.server.fastmcp import Image
from pydantic import Field

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.config import settings
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("view_photo"))
@_tool
async def view_photo(
    node_id: Annotated[str, Field(description="The Amazon Photos node ID")],
    max_size: Annotated[int, Field(ge=0, description="Maximum dimension in pixels. 0 for default.")] = 1024,
) -> Image | str:
    """Fetch a photo and return it as an MCP Image.

    This unlocks Vision models (like Claude 3.5 Sonnet) to 'see' the image.
    Downloads the full image, resizes it to a manageable thumbnail (default 1024px),
    and returns it as an MCP Image payload.
    """
    if max_size <= 0:
        max_size = settings.thumbnail_max_size

    ap = _get_client()
    result = await ap.get_file(node_id)
    url = None

    if isinstance(result, dict):
        url = result.get("tempLink") or result.get("contentUrl") or result.get("url")

    if not url:
        return f"Error: Could not resolve download URL for node_id: {node_id}"

    try:
        from curl_cffi import requests as curl_req

        http_client = getattr(ap, "client", None)
        s = http_client if http_client is not None else curl_req.AsyncSession()

        async with s.stream("GET", url, timeout=30) as r:
            r.raise_for_status()

            ctype = r.headers.get("Content-Type", "")
            if "video" in ctype:
                return f"Cannot view video files. URL: {url}"

            content_length = int(r.headers.get("Content-Length", 0))
            if content_length > 50 * 1024 * 1024:
                return f"Image too large to process ({content_length / 1024 / 1024:.1f} MB). URL: {url}"

            content = await r.aread()

        from PIL import Image as PILImage

        img = PILImage.open(stdlib_io.BytesIO(content))
        img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)

        buf = stdlib_io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)

        return Image(data=buf.getvalue(), format="jpeg")
    except Exception as e:
        return f"Failed to view photo: {str(e)}"
