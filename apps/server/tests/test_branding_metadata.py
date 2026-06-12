from __future__ import annotations

import json
import tomllib
from pathlib import Path

from config import Settings
from main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_fastapi_metadata_exposes_current_brand(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(
        Settings(
            database_url=sqlite_database_url,
            ai_api_key="test-key",
            ingest_shared_secret="ingest-secret",
            redis_url=redis_url,
            shopify_api_key="test-key",
            shopify_api_secret="test-secret",
            shopify_app_url="https://example.com",
            shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
            shopify_webhook_base_url="https://example.com",
        )
    )

    assert app.title == "SKU Lens"
    assert "daily decision board" in app.description
    assert "Winners and Leakers" in app.description
    assert "Order Gaps" not in app.description


def test_package_metadata_uses_current_product_positioning() -> None:
    root_package = json.loads((REPO_ROOT / "package.json").read_text())
    server_project = tomllib.loads((REPO_ROOT / "apps/server/pyproject.toml").read_text())["project"]
    server_readme = (REPO_ROOT / "apps/server/README.md").read_text()

    assert root_package["description"] == "SKU Lens monorepo for a Shopify product daily decision board."
    assert server_project["description"] == "SKU Lens backend for a Shopify product daily decision board"
    assert "daily decision board backend" in server_readme
    assert "Winner & Loser" not in root_package["description"]
    assert "Winner & Loser" not in server_project["description"]
    assert "Winner & Loser" not in server_readme
