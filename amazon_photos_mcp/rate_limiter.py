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


class CircuitBreaker:
    """Sliding-window circuit breaker for API failure detection.

    After N consecutive failures within the window, enters 'open' state
    where all requests are rejected. After cooldown, transitions to
    'half-open' for a probe, then back to 'closed' on success.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, threshold: int = 5, window_s: float = 60.0, cooldown_s: float = 30.0) -> None:
        self._threshold = threshold
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._state = self.STATE_CLOSED
        self._failures: list[float] = []
        self._last_state_change = time.monotonic()
        self._lock = Lock()

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures.append(now)
            # Prune failures outside the window
            self._failures = [t for t in self._failures if now - t < self._window_s]
            if len(self._failures) >= self._threshold:
                if self._state != self.STATE_OPEN:
                    self._state = self.STATE_OPEN
                    self._last_state_change = now

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            if self._state != self.STATE_CLOSED:
                self._state = self.STATE_CLOSED
                self._last_state_change = time.monotonic()

    def is_allowed(self) -> bool:
        with self._lock:
            if self._state == self.STATE_CLOSED:
                return True
            if self._state == self.STATE_OPEN:
                now = time.monotonic()
                if now - self._last_state_change >= self._cooldown_s:
                    self._state = self.STATE_HALF_OPEN
                    self._last_state_change = now
                    return True
                return False
            # half-open: allow one probe
            return True

    @property
    def state(self) -> str:
        with self._lock:
            return self._state


_global_bucket: TokenBucket | None = None
_global_circuit: CircuitBreaker | None = None
_bucket_lock = Lock()


def check_rate_limit() -> None:
    """Check and consume a rate limit token. Raises RateLimitError if exceeded."""
    global _global_bucket, _global_circuit
    if _global_bucket is None:
        with _bucket_lock:
            if _global_bucket is None:
                from amazon_photos_mcp.config import get_config

                rate = float(get_config("rate_limit", default=5.0))
                cap = int(get_config("rate_capacity", default=10))
                _global_bucket = TokenBucket(rate=rate, capacity=cap)
                _global_circuit = CircuitBreaker()

    from amazon_photos_mcp.errors import RateLimitError

    # Circuit breaker check
    if _global_circuit is not None and not _global_circuit.is_allowed():
        raise RateLimitError(retry_after=30)

    if not _global_bucket.consume(1):
        # Derive retry_after from bucket refill rate instead of hardcoded 15
        tokens_missing = max(1.0, 1.0 - _global_bucket.available)
        retry_after = int(tokens_missing / _global_bucket._rate) + 1
        raise RateLimitError(retry_after=max(1, retry_after))
