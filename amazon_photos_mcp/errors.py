"""Custom exceptions for Amazon Photos MCP."""


class MCPError(Exception):
    """Base MCP error with machine-readable code."""

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        self.code = code
        super().__init__(message)


class AuthenticationError(MCPError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="AUTH_REQUIRED")


class ResourceNotFoundError(MCPError):
    def __init__(self, resource_type: str, resource_id: str) -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} not found: {resource_id}", code="NOT_FOUND")


class RateLimitError(MCPError):
    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s.", code="RATE_LIMITED")
