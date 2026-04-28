from __future__ import annotations

from models import ShopInstallation
from repositories.installations import InstallationRepository


class ShopInstallationService:
    def __init__(self, repository: InstallationRepository | None = None) -> None:
        self._repository = repository or InstallationRepository()

    async def upsert_installation(
        self,
        *,
        shop_domain: str,
        public_token: str,
        access_token: str | None,
    ) -> ShopInstallation:
        return await self._repository.upsert(
            shop_domain=shop_domain,
            public_token=public_token,
            access_token=access_token,
        )
