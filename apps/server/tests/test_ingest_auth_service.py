from __future__ import annotations

import pytest

from config import Settings
from db import create_session_factory, db_session_context, init_db
from models import ShopInstallation
from services.ingest_auth import (
    IngestAuthService,
    IngestRequestExpiredError,
    InvalidIngestTokenError,
    ShopInstallationNotFoundError,
)


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
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


@pytest.mark.asyncio
async def test_ingest_auth_service_rejects_expired_request(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
            )
        )
        await session.commit()

    service = IngestAuthService(
        _settings(sqlite_database_url, redis_url),
        time_provider=lambda: 1_700_000_000,
    )

    async with db_session_context(session_factory):
        with pytest.raises(IngestRequestExpiredError) as exc_info:
            await service.verify_public_token(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timestamp=1_699_999_600,
            )

    assert str(exc_info.value) == "Ingest request expired."


@pytest.mark.asyncio
async def test_ingest_auth_service_rejects_unknown_shop_installation(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = IngestAuthService(
        _settings(sqlite_database_url, redis_url),
        time_provider=lambda: 1_700_000_000,
    )

    async with db_session_context(session_factory):
        with pytest.raises(ShopInstallationNotFoundError) as exc_info:
            await service.verify_public_token(
                shop_domain="missing.myshopify.com",
                public_token="public-1",
                timestamp=1_700_000_000,
            )

    assert str(exc_info.value) == "Shop installation not found."


@pytest.mark.asyncio
async def test_ingest_auth_service_rejects_token_for_different_shop_owner(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
            )
        )
        await session.commit()

    service = IngestAuthService(
        _settings(sqlite_database_url, redis_url),
        time_provider=lambda: 1_700_000_000,
    )

    async with db_session_context(session_factory):
        with pytest.raises(InvalidIngestTokenError) as exc_info:
            await service.verify_public_token(
                shop_domain="demo.myshopify.com",
                public_token="public-2",
                timestamp=1_700_000_000,
            )

    assert str(exc_info.value) == "Invalid ingest token."
