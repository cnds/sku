from __future__ import annotations

import pytest
from sqlmodel import select

from db import create_session_factory, db_session_context, init_db
from models import ShopInstallation
from services.shop_installations import ShopInstallationService


@pytest.mark.asyncio
async def test_shop_installation_service_upserts_public_and_access_tokens(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ShopInstallationService()
    initial_public = "alpha"
    updated_public = "beta"
    initial_access = "gamma"
    updated_access = "delta"

    async with db_session_context(session_factory) as session:
        created = await service.upsert_installation(
            shop_domain="demo.myshopify.com",
            public_token=initial_public,
            access_token=initial_access,
        )
        await session.commit()

    async with db_session_context(session_factory) as session:
        await service.upsert_installation(
            shop_domain="demo.myshopify.com",
            public_token=updated_public,
            access_token=updated_access,
        )
        await session.commit()

    async with session_factory() as session:
        installations = (
            await session.exec(
                select(ShopInstallation).where(
                    ShopInstallation.shop_domain == "demo.myshopify.com"
                )
            )
        ).all()

    assert created.shop_domain == "demo.myshopify.com"
    assert len(installations) == 1
    assert installations[0].shop_domain == "demo.myshopify.com"
    assert installations[0].public_token == updated_public
    assert installations[0].access_token == updated_access
