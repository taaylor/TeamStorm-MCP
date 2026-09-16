"""Environment-backed TeamStorm MCP configuration."""

from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from teamstorm_mcp.adapters.teamstorm.constants import DEFAULT_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS
from teamstorm_mcp.application.constants import DEFAULT_MAX_CONTEXT_ITEMS, MAX_CONTEXT_ITEMS_LIMIT


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    teamstorm_url: HttpUrl
    teamstorm_token: SecretStr
    teamstorm_queue_path: Path = Field(
        default_factory=lambda: Path.home() / ".local/state/teamstorm-mcp/queue.sqlite3"
    )
    teamstorm_daemon_interval: float = Field(default=30, gt=0, le=3600)
    teamstorm_timeout: float = Field(
        default=DEFAULT_TIMEOUT_SECONDS,
        gt=0,
        le=MAX_TIMEOUT_SECONDS,
    )
    teamstorm_max_context_items: int = Field(
        default=DEFAULT_MAX_CONTEXT_ITEMS,
        ge=1,
        le=MAX_CONTEXT_ITEMS_LIMIT,
    )
