from __future__ import annotations

from config import Settings
from main import create_app


def test_fastapi_metadata_exposes_current_brand(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(
        Settings(
            database_url=sqlite_database_url,
            gemini_api_key="test-key",
            ingest_shared_secret="ingest-secret",
            redis_url=redis_url,
            shopify_api_key="test-key",
            shopify_api_secret="test-secret",
            shopify_app_url="https://example.com",
            shopify_scopes="read_orders,read_products",
            shopify_webhook_base_url="https://example.com",
        )
    )

    assert app.title == "SKU Lens"
    assert "AI Winner & Loser Analysis" in app.description
    assert "Order Gaps" in app.description
