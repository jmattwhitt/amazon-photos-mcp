"""Amazon Photos client lifecycle and HTTP configuration."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from amazon_photos_mcp.api import AmazonPhotosClient
from amazon_photos_mcp.errors import AuthenticationError

# ---------------------------------------------------------------------------
# Cookie management
# ---------------------------------------------------------------------------
_AMAZON_COOKIE_PATH = Path.home() / ".config" / "amazon-photos-mcp" / "cookies.json"
_COOKIE_EXPIRED_AFTER_HOURS = 72.0
_COOKIE_WARN_AFTER_HOURS = 48.0
_COOKIE_STAT_CACHE_TTL = 300.0

_cookie_last_stat: float = 0.0
_cookie_cached_mtime: float | None = None
_cookie_cache_lock = threading.Lock()


def _cookie_age_hours() -> float | None:
    global _cookie_last_stat, _cookie_cached_mtime
    now = time.time()
    mtime: float | None
    with _cookie_cache_lock:
        if now - _cookie_last_stat < _COOKIE_STAT_CACHE_TTL and _cookie_cached_mtime is not None:
            mtime = _cookie_cached_mtime
        else:
            try:
                _cookie_cached_mtime = _AMAZON_COOKIE_PATH.stat().st_mtime
            except FileNotFoundError:
                _cookie_cached_mtime = None
            _cookie_last_stat = now
            mtime = _cookie_cached_mtime
    if mtime is None:
        return None
    return (time.time() - mtime) / 3600


def cookie_advice() -> str:
    h = _cookie_age_hours()
    if h is None:
        return "Cookie file not found. Create ~/.config/amazon-photos-mcp/cookies.json."
    if h >= _COOKIE_EXPIRED_AFTER_HOURS:
        return f"Cookies expired ({h:.0f}h old). Refresh immediately and call refresh_client."
    if h >= _COOKIE_WARN_AFTER_HOURS:
        return f"Cookies stale ({h:.0f}h old). Consider refreshing soon."
    return f"Cookies fresh ({h:.0f}h old)."


def _invalidate_cookie_cache() -> None:
    global _cookie_last_stat, _cookie_cached_mtime
    with _cookie_cache_lock:
        _cookie_last_stat = 0.0
        _cookie_cached_mtime = None


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------
_client_lock = threading.Lock()
_client: AmazonPhotosClient | None = None


def _normalize_cookies(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    pairs = [("ubid-main", "ubid_main"), ("at-main", "at_main")]
    for hyphen, underscore in pairs:
        if hyphen in normalized and underscore not in normalized:
            normalized[underscore] = normalized[hyphen]
        elif underscore in normalized and hyphen not in normalized:
            normalized[hyphen] = normalized[underscore]
    return normalized


def _load_cookies() -> dict[str, Any] | None:
    env_cookies = os.environ.get("AMAZON_PHOTOS_COOKIES")
    if env_cookies:
        return _normalize_cookies(json.loads(env_cookies))
    from amazon_photos_mcp.crypto import DecryptionError, load_encrypted_cookies

    try:
        cookies = load_encrypted_cookies(_AMAZON_COOKIE_PATH)
    except DecryptionError as e:
        raise AuthenticationError("Cookie file exists but decryption failed. You may need to re-authenticate.") from e

    if cookies is not None:
        return _normalize_cookies(cookies)
    return None


def _get_client(force_refresh: bool = False) -> AmazonPhotosClient:
    global _client
    with _client_lock:
        if force_refresh:
            _client = None
            _invalidate_cookie_cache()
        if _client is not None:
            return _client

        cookies = _load_cookies()
        if not cookies:
            raise AuthenticationError(
                "No Amazon cookies configured. Create "
                "~/.config/amazon-photos-mcp/cookies.json with keys: "
                "ubid-main, at-main, session-id  (or set AMAZON_PHOTOS_COOKIES env var)"
            )

        _client = AmazonPhotosClient(cookies=cookies)

        _wrap_http_errors(_client)

        return _client


def _wrap_http_errors(client: Any) -> None:
    from amazon_photos_mcp.rate_limiter import _global_circuit, check_rate_limit

    if hasattr(client, "client"):
        http_client = client.client
        orig_request = http_client.request
        orig_stream = http_client.stream

        def _patched_request(method: str, url: str, **kwargs: Any) -> Any:
            check_rate_limit()
            kwargs.setdefault("timeout", 30.0)
            try:
                resp = orig_request(method, url, **kwargs)
                if resp.status_code in (429, 503):
                    if _global_circuit is not None:
                        _global_circuit.record_failure()
                elif resp.status_code < 500:
                    if _global_circuit is not None:
                        _global_circuit.record_success()
                return resp
            except Exception:
                if _global_circuit is not None:
                    _global_circuit.record_failure()
                raise

        def _patched_stream(method: str, url: str, **kwargs: Any) -> Any:
            check_rate_limit()
            kwargs.setdefault("timeout", 30.0)
            return orig_stream(method, url, **kwargs)

        http_client.request = _patched_request
        http_client.stream = _patched_stream
