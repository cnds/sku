from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_env_files() -> tuple[Path, Path, str]:
    server_dir = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    return (
        repo_root / ".env",
        server_dir / ".env",
        ".env",
    )


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    celery_broker_url: str | None = None
    sku_lens_log_level: str = "INFO"
    shopify_api_key: str
    shopify_api_secret: str
    shopify_app_url: str
    shopify_scopes: str
    shopify_webhook_base_url: str
    shopify_billing_test: bool = False
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ingest_shared_secret: str
    ingest_token_ttl_seconds: int = 300
    benchmark_min_views: int = 50
    sku_lens_internal_review: bool = False

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
