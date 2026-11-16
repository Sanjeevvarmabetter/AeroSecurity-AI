"""Centralised application configuration (12-factor, environment driven)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # Database. Credentials come only from the environment; there is no default password.
    database_url: SecretStr = Field(
        description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/db"
    )
    db_connect_timeout_s: int = Field(default=5, ge=1, le=60)

    # HTTP
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Auth: static bearer tokens per role. Empty = that role is disabled (fail closed).
    api_token_viewer: SecretStr = SecretStr("")
    api_token_analyst: SecretStr = SecretStr("")
    api_token_admin: SecretStr = SecretStr("")
    rate_limit_per_minute: int = Field(default=120, ge=1)

    # Ingestion
    ingest_batch_size: int = Field(default=5000, ge=100, le=50_000)
    ingest_max_file_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    ingest_max_rows: int = Field(default=5_000_000, ge=1)
    opensky_api_base_url: str = "https://opensky-network.org/api"
    opensky_token_url: str = (
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"  # noqa: E501,S105
    )
    opensky_client_id: SecretStr = SecretStr("")
    opensky_client_secret: SecretStr = SecretStr("")
    opensky_min_interval_s: float = Field(default=10.0, ge=1.0)
    opensky_max_retries: int = Field(default=4, ge=0, le=10)

    # AI (consumed from Phase 6; declared here so configuration stays centralised)
    ai_provider: Literal["ollama", "openrouter"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_timeout_s: float = Field(default=120.0, ge=1, le=600)
    ai_max_output_tokens: int = Field(default=1800, ge=64, le=8000)
    ai_max_context_chars: int = Field(default=24_000, ge=1000, le=200_000)
    ai_temperature: float = Field(default=0.2, ge=0, le=1)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_rate_limit_per_minute: int = Field(default=10, ge=1)
    chat_max_tool_calls: int = Field(default=4, ge=0, le=8)
    chat_tool_result_chars: int = Field(default=6000, ge=500, le=30_000)
    chat_history_messages: int = Field(default=8, ge=0, le=30)
    chat_max_messages_per_conversation: int = Field(default=100, ge=2, le=1000)
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError("Wildcard CORS origin is not permitted")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
