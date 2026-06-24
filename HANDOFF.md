# Amazon Photos MCP — Architecture Notes

## Overview

The server is a FastMCP application with a native Amazon Photos API client (`api.py`)
built on `curl_cffi` for browser TLS fingerprint impersonation. The client handles
pagination, retry with exponential backoff, rate limiting, and structured error
handling (authentication failures, rate limits, circuit breaker trips).

## Key Design Decisions

- **No upstream dependency.** The client is a direct implementation of Amazon's
  undocumented Drive API, reverse-engineered from browser traffic.
- **curl_cffi over httpx.** Amazon's frontend servers require browser TLS
  fingerprints; standard Python HTTP libraries are rejected.
- **Encrypted cookie storage.** Cookies are encrypted at rest with AES-256-GCM
  (`crypto.py`). The encryption key is derived from a machine-specific secret.
- **Token-bucket rate limiter.** Configurable via TOML or environment variables.
  Includes a sliding-window circuit breaker that opens for 30s after repeated
  failures.
- **Structured error dicts.** All tool responses are `dict[str, Any]` with
  consistent `error`, `code`, and `message` keys. The `@_tool` decorator
  catches exceptions and converts them to this format.

## Adding a New Tool

1. Create the handler function in the appropriate `tools/` module.
2. Decorate with `@mcp.tool(annotations=_tool_annotations("tool_name"))` and `@_tool`.
3. Add the tool name to the correct annotation set in `server.py`:
   `_READ_ONLY_TOOLS`, `_DESTRUCTIVE_TOOLS`, or `_IDEMPOTENT_TOOLS`.
4. Import the module in `__init__.py` so it registers with the MCP instance.
5. Add tests using the `mock_ap` fixture from `conftest.py`.

## Running Locally

```bash
uv run amazon-photos-mcp
```

The server starts on stdio (MCP protocol). Configure your MCP client to launch it.
Cookies must be present at `~/.config/amazon-photos-mcp/cookies.json` or in
the `AMAZON_PHOTOS_COOKIES` environment variable.
