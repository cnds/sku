from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    sku_lens_log_level: str = "INFO"
    shopify_api_key: str
    shopify_api_secret: str
    shopify_app_url: str
    shopify_scopes: str
    shopify_webhook_base_url: str
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-flash"
    ingest_shared_secret: str
    ingest_token_ttl_seconds: int = 300
    benchmark_min_views: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
