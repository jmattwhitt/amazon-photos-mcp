"""MCP Inspector smoke tests.

These can also run headlessly to validate tool schema sanity.
"""

from __future__ import annotations

import importlib

import pytest


def _get_all_tool_names() -> list[str]:
    mod = importlib.import_module("amazon_photos_mcp")
    tool_names = []
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and hasattr(obj, "__name__") and not name.startswith("_"):
            if hasattr(obj, "__wrapped__"):
                tool_names.append(name)
    return sorted(set(tool_names))


ALL_TOOLS = _get_all_tool_names()


class TestAllToolsRegistered:
    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_tool_is_callable(self, tool_name: str) -> None:
        mod = importlib.import_module("amazon_photos_mcp")
        tool = getattr(mod, tool_name)
        assert callable(tool), f"{tool_name} is not callable"

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_tool_has_docstring(self, tool_name: str) -> None:
        mod = importlib.import_module("amazon_photos_mcp")
        tool = getattr(mod, tool_name)
        doc = tool.__doc__
        assert doc, f"{tool_name} has no docstring"


class TestToolCallable:
    def test_check_connection_runs(self) -> None:
        from amazon_photos_mcp.tools.connection import check_connection

        result = check_connection()
        assert isinstance(result, dict)
        assert result.get("status") == "connected"

    def test_search_photos_runs(self) -> None:
        from amazon_photos_mcp.tools.search import search_photos

        result = search_photos("test")
        assert isinstance(result, dict)

    def test_get_photos_runs(self) -> None:
        from amazon_photos_mcp.tools.search import get_photos

        result = get_photos()
        assert isinstance(result, dict)

    def test_list_folders_runs(self) -> None:
        from amazon_photos_mcp.tools.folders import list_folders

        result = list_folders()
        assert isinstance(result, dict)

    def test_list_people_runs(self) -> None:
        from amazon_photos_mcp.tools.people import list_people

        result = list_people()
        assert isinstance(result, dict)

    def test_find_duplicates_runs(self) -> None:
        from amazon_photos_mcp.tools.duplicates import find_duplicates

        result = find_duplicates()
        assert isinstance(result, dict)

    def test_trash_items_with_dry_run(self) -> None:
        from amazon_photos_mcp.tools.trash import trash_items

        result = trash_items(["node-001"])
        assert isinstance(result, dict)

    def test_set_favorite_runs(self) -> None:
        from amazon_photos_mcp.tools.favorites_hidden import set_favorite

        result = set_favorite(["node-001"], favorite=True)
        assert isinstance(result, dict)

    def test_set_hidden_runs(self) -> None:
        from amazon_photos_mcp.tools.favorites_hidden import set_hidden

        result = set_hidden(["node-001"], hidden=False)
        assert isinstance(result, dict)

    def test_download_runs(self) -> None:
        from amazon_photos_mcp.tools.media import download

        result = download(node_ids=["node-001"])
        assert isinstance(result, dict)

    def test_download_library_runs(self) -> None:
        from amazon_photos_mcp.tools.media import download_library

        result = download_library(max_items=10)
        assert isinstance(result, dict)

    def test_permanently_delete_refused_without_confirm(self) -> None:
        from amazon_photos_mcp.tools.trash import permanently_delete

        result = permanently_delete(["node-001"], confirm=False)
        assert result.get("status") == "aborted"
