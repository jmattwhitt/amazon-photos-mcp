FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy the project files
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY amazon_photos_mcp/ amazon_photos_mcp/

# Install the dependencies and the project
RUN uv sync --frozen

# Ensure the executable is available
ENV PATH="/app/.venv/bin:$PATH"

# Run the MCP server over stdio
ENTRYPOINT ["amazon-photos-mcp"]
