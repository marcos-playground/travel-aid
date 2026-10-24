"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    openai_api_key: str = ""
    chat_model: str = "gpt-6-luna"
    database_url: str = ""
    database_url_unpooled: str = ""
    planning_retention_days: int = Field(default=30, ge=1, le=365)
    flight_search_timeout_seconds: float = Field(default=75, gt=0, le=90)
    flight_cache_seconds: int = Field(default=900, ge=0, le=86400)
    web_origin: str = "http://localhost:3000"
    posthog_enabled: bool = False
    posthog_project_key: str = ""
    posthog_host: str = ""
    posthog_capture_debug_content: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
