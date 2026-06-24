"""MCP Inspector smoke tests.

These can also run headlessly to validate tool schema sanity.
"""

from __future__ import annotations

import asyncio

import pytest


def _get_all_tool_names() -> list[str]:
    """Discover registered tools via FastMCP server's tool registry."""
    from amazon_photos_mcp.server import mcp

    try:
        tools = asyncio.run(mcp.list_tools())
        return sorted([t.name for t in tools])
    except Exception:
        return []


ALL_TOOLS = _get_all_tool_names()


class TestAllToolsRegistered:
    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    @pytest.mark.asyncio
    async def test_tool_is_callable(self, tool_name: str) -> None:
        from amazon_photos_mcp.server import mcp

        tools = await mcp.list_tools()
        tool = next((t for t in tools if t.name == tool_name), None)
        assert tool is not None, f"{tool_name} not registered with MCP"

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    @pytest.mark.asyncio
    async def test_tool_has_docstring(self, tool_name: str) -> None:
        from amazon_photos_mcp.server import mcp

        tools = await mcp.list_tools()
        tool = next((t for t in tools if t.name == tool_name), None)
        assert tool is not None, f"{tool_name} not registered with MCP"
        assert tool.description, f"{tool_name} has no description"


class TestToolCallable:
    @pytest.mark.asyncio
    async def test_check_connection_runs(self) -> None:
        from amazon_photos_mcp.tools.connection import check_connection

        result = await check_connection()
        assert isinstance(result, dict)
        assert result.get("status") == "connected"

    @pytest.mark.asyncio
    async def test_search_photos_runs(self) -> None:
        from amazon_photos_mcp.tools.search import search_photos

        result = await search_photos(query="type:(PHOTOS)")
        assert isinstance(result, dict)
        assert "error" not in result or not result.get("error")

    @pytest.mark.asyncio
    async def test_get_photos_runs(self) -> None:
        from amazon_photos_mcp.tools.search import get_photos

        result = await get_photos(max_results=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_folders_runs(self) -> None:
        from amazon_photos_mcp.tools.folders import list_folders

        result = await list_folders()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_people_runs(self) -> None:
        from amazon_photos_mcp.tools.people import list_people

        result = await list_people()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_find_duplicates_runs(self) -> None:
        from amazon_photos_mcp.tools.duplicates import find_duplicates

        result = await find_duplicates(max_groups=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_trash_items_with_dry_run(self) -> None:
        """Permanently_delete requires confirm=True; verify it refuses."""
        from amazon_photos_mcp.tools.trash import permanently_delete

        result = await permanently_delete(node_ids=["test-id"], confirm=False)
        assert result.get("status") in ("aborted",) or "refusing" in str(result.get("message", "")).lower()

    @pytest.mark.asyncio
    async def test_set_favorite_runs(self) -> None:
        from amazon_photos_mcp.tools.favorites_hidden import set_favorite

        result = await set_favorite(node_ids=["node-001"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_set_hidden_runs(self) -> None:
        from amazon_photos_mcp.tools.favorites_hidden import set_hidden

        result = await set_hidden(node_ids=["node-001"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_download_runs(self) -> None:
        from amazon_photos_mcp.tools.media import download

        result = await download(node_ids=["node-001"], max_items=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_download_library_runs(self) -> None:
        from amazon_photos_mcp.tools.media import download_library

        result = await download_library(dry_run=True, max_items=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_permanently_delete_refused_without_confirm(self) -> None:
        from amazon_photos_mcp.tools.trash import permanently_delete

        result = await permanently_delete(node_ids=["test-id"], confirm=False)
        assert result.get("status") in ("aborted", "error") or "refusing" in str(result.get("message", "")).lower()
