"""Configuration system for amazon-photos-mcp.

Supports both a config file (~/.config/amazon-photos-mcp/config.toml) and
environment variables. Env vars take precedence over config file values.

Config keys:
  cookie_path          — path to cookies.json
  db_path              — path to parquet database
  pipeline_dir         — default download directory for pipeline
  log_level            — DEBUG, INFO, WARNING, ERROR
  log_file             — file path for log output
  rate_limit           — requests per second
  rate_capacity        — burst capacity
  download_default_max — default max items for download
  download_library_max — default max items for download_library
  thumbnail_max_size   — default thumbnail max dimension
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path.home() / ".config" / "amazon-photos-mcp" / "config.toml"
_cache: dict[str, Any] | None = None
_cache_lock = threading.Lock()


def _load_config() -> dict[str, Any]:
    """Load TOML config file if it exists."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _cache_config() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = _load_config()
    return _cache


def get_config(key: str, default: Any = None, env_var: str = "") -> Any:
    """Get a config value, checking env var first, then config file, then default.

    Args:
        key: Config key name (used in TOML file)
        default: Default value if not found anywhere
        env_var: Env variable name (auto-generated from key if empty)
    """
    # Env var takes precedence
    env = env_var or _key_to_env(key)
    val = os.environ.get(env)
    if val is not None:
        return _coerce(val, default)
    # Fall back to config file
    cfg = _cache_config()
    if key in cfg:
        return cfg[key]
    return default


def _key_to_env(key: str) -> str:
    """Convert snake_case key to AMAZON_PHOTOS_* env var."""
    return f"AMAZON_PHOTOS_{key.upper()}"


def _coerce(value: str, default: Any) -> Any:
    """Coerce a string env var to the type of the default."""
    if isinstance(default, bool):
        return value.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    return value


def invalidate_cache() -> None:
    """Clear the config cache (allows re-reading after file changes)."""
    global _cache
    _cache = None


_DEFAULTS: dict[str, Any] = {
    "cookie_path": str(Path.home() / ".config" / "amazon-photos-mcp" / "cookies.json"),
    "db_path": "",
    "pipeline_dir": str(Path.home() / "Downloads" / "amazon-photos-pipeline"),
    "log_level": "INFO",
    "log_file": "",
    "rate_limit": 5,
    "rate_capacity": 10,
    "download_default_max": 500,
    "download_library_max": 5000,
    "thumbnail_max_size": 400,
}


def list_all() -> dict[str, Any]:
    """Return all resolved config values for display/debugging."""
    return {key: get_config(key, default=default) for key, default in _DEFAULTS.items()}
