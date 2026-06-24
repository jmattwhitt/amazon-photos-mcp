"""Integration tests -- validate MCP protocol layer with FastMCP server object.

FastMCP 3.x exposes list_tools() and call_tool() as async methods directly
on the server object (no separate test_client). Tool schemas live on
FunctionTool.parameters rather than on a client-side Tool.inputSchema.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestMCPProtocol:
    """Verify that tools are callable through the MCP transport."""

    async def test_list_tools_returns_all_registered_tools(self) -> None:
        from amazon_photos_mcp import mcp

        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "check_connection" in tool_names
        assert "search_photos" in tool_names
        assert "find_duplicates" in tool_names
        assert "download" in tool_names or "download_files" in tool_names
        assert len(tool_names) >= 40

    async def test_tool_has_input_schema(self) -> None:
        from amazon_photos_mcp import mcp

        tools = await mcp.list_tools()
        for tool in tools:
            params = tool.parameters
            assert params is not None, f"{tool.name} has no parameters"
            assert params.get("type") == "object", f"{tool.name} schema type should be object, got {params.get('type')}"

    async def test_tool_has_description(self) -> None:
        from amazon_photos_mcp import mcp

        tools = await mcp.list_tools()
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description) > 10, f"{tool.name} description too short: {tool.description}"

    async def test_call_check_connection_returns_valid_json_rpc(self) -> None:
        from amazon_photos_mcp import mcp

        result = await mcp.call_tool("check_connection", {})
        assert result is not None
        assert len(result.content) > 0, "Expected at least one content block"

    async def test_call_search_photos_with_query(self) -> None:
        from amazon_photos_mcp import mcp

        result = await mcp.call_tool("search_photos", {"query": "type:(PHOTOS)"})
        assert result is not None

    async def test_call_find_duplicates_read_only(self) -> None:
        from amazon_photos_mcp import mcp

        result = await mcp.call_tool("find_duplicates", {})
        assert result is not None

    async def test_read_only_tools_annotated_correctly(self) -> None:
        from amazon_photos_mcp.server import _READ_ONLY_TOOLS, mcp

        tools = await mcp.list_tools()
        for tool in tools:
            if tool.name in _READ_ONLY_TOOLS:
                ann = tool.annotations
                if ann is not None:
                    ro = getattr(ann, "readOnlyHint", None)
                    assert ro is not False, f"{tool.name} should have readOnlyHint=True, got {ro}"

    async def test_tool_errors_return_readable_messages(self) -> None:
        from amazon_photos_mcp import mcp

        result = await mcp.call_tool(
            "permanently_delete",
            {"node_ids": ["test-id"], "confirm": False},
        )
        assert result is not None
        if result.content:
            text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
            assert "aborted" in text.lower() or "refusing" in text.lower(), f"Expected abort message, got: {text[:200]}"


@pytest.mark.asyncio
class TestToolSchemaValidation:
    """Verify tool schemas match expected signatures."""

    async def test_set_favorite_schema_has_boolean_parameter(self) -> None:
        from amazon_photos_mcp import mcp

        tools = await mcp.list_tools()
        sf = next((t for t in tools if t.name == "set_favorite"), None)
        assert sf is not None, "set_favorite tool not found"
        props = sf.parameters.get("properties", {})
        assert "favorite" in props, "set_favorite should have 'favorite' param"
        assert "boolean" in props["favorite"].get("type", ""), f"'favorite' should be boolean, got {props['favorite']}"

    async def test_set_hidden_schema_has_boolean_parameter(self) -> None:
        from amazon_photos_mcp import mcp

        tools = await mcp.list_tools()
        sh = next((t for t in tools if t.name == "set_hidden"), None)
        assert sh is not None, "set_hidden tool not found"
        props = sh.parameters.get("properties", {})
        assert "hidden" in props, "set_hidden should have 'hidden' param"
        assert "boolean" in props["hidden"].get("type", ""), f"'hidden' should be boolean, got {props['hidden']}"

    async def test_download_schema_has_flexible_params(self) -> None:
        from amazon_photos_mcp import mcp

        tools = await mcp.list_tools()
        dl = next((t for t in tools if t.name == "download"), None)
        assert dl is not None, "download tool not found"
        props = dl.parameters.get("properties", {})
        assert "node_ids" in props
        assert "query" in props
        assert "year" in props, "download should have year param"
