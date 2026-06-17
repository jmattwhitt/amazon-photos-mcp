"""Configuration system for amazon-photos-mcp using Pydantic Settings.

Supports both a config file (~/.config/amazon-photos-mcp/config.toml) and
environment variables with prefix AMAZON_PHOTOS_. Env vars take precedence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import TomlConfigSettingsSource


class Settings(BaseSettings):
    """Application settings loaded from config file and environment variables."""

    # Paths
    cookie_path: str = str(Path.home() / ".config" / "amazon-photos-mcp" / "cookies.json")
    db_path: str = ""
    pipeline_dir: str = str(Path.home() / "Downloads" / "amazon-photos-pipeline")

    # Logging
    log_level: str = "TRACE"
    log_file: str = ""

    # Rate limiting
    rate_limit: float = Field(default=5.0, ge=0)
    rate_capacity: int = Field(default=10, ge=1)

    # Downloads
    download_default_max: int = Field(default=500, ge=1)
    download_library_max: int = Field(default=5000, ge=1)

    # Thumbnails
    thumbnail_max_size: int = Field(default=400, ge=0)

    model_config = SettingsConfigDict(
        toml_file=Path.home() / ".config" / "amazon-photos-mcp" / "config.toml",
        env_prefix="AMAZON_PHOTOS_",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))


settings: Any = Settings()


def get_config(key: str) -> Any:
    """Get a resolved config value by attribute name."""
    return getattr(settings, key)


def invalidate_cache() -> None:
    """Re-read config from TOML file by re-initializing settings."""
    global settings
    settings = Settings()


def list_all() -> dict[str, Any]:
    """Return all resolved config values for display/debugging."""
    return settings.model_dump()  # type: ignore[no-any-return]


def _coerce(value: str, default: Any) -> Any:
    """Coerce a string env var to the type of the default.

    Legacy helper used by tests. Pydantic Settings handles coercion
    natively for production paths.
    """
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
