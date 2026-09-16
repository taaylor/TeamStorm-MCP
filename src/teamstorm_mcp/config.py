"""Environment-backed TeamStorm MCP configuration."""

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from teamstorm_mcp.constants import (
    DEFAULT_MAX_CONTEXT_ITEMS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTEXT_ITEMS_LIMIT,
    MAX_TIMEOUT_SECONDS,
)


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    teamstorm_url: HttpUrl
    teamstorm_token: SecretStr
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
