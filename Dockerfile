# Multi-stage build for amazon-photos-mcp
# MCP servers use stdio transport — no ports exposed.

FROM python:3.12-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash mcp

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY amazon_photos_mcp/ /app/amazon_photos_mcp/

# Config directory for cookies
RUN mkdir -p /home/mcp/.config/amazon-photos-mcp && \
    chown -R mcp:mcp /home/mcp/.config && \
    chown -R mcp:mcp /app

USER mcp

# MCP servers communicate via stdio
ENTRYPOINT ["python", "-m", "amazon_photos_mcp"]
