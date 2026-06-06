"""Token-bucket rate limiter and HTTP 429 detection for Amazon Photos API."""

from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available(self) -> float:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(self._capacity, self._tokens + elapsed * self._rate)


_global_bucket = TokenBucket(rate=5.0, capacity=10)


def check_rate_limit() -> None:
    """Check and consume a rate limit token. Raises RateLimitError if exceeded."""
    from amazon_photos_mcp import RateLimitError
    if not _global_bucket.consume(1):
        raise RateLimitError(retry_after=15)
