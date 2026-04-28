from __future__ import annotations

from sqlmodel import select

from db import get_db_session
from models import ShopInstallation


class InstallationRepository:
    async def get_by_shop_domain(self, shop_domain: str) -> ShopInstallation | None:
        session = get_db_session()
        return (
            await session.exec(
                select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
            )
        ).first()

    async def upsert(
        self,
        *,
        shop_domain: str,
        public_token: str,
        access_token: str | None,
    ) -> ShopInstallation:
        installation = await self.get_by_shop_domain(shop_domain)
        if installation is None:
            installation = ShopInstallation(
                shop_domain=shop_domain,
                public_token=public_token,
                access_token=access_token,
            )
            get_db_session().add(installation)
            return installation

        installation.public_token = public_token
        installation.access_token = access_token
        return installation
