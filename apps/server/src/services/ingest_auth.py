from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Callable

from config import Settings
from models import ShopInstallation
from repositories.installations import InstallationRepository


class IngestAuthError(Exception):
    detail = "Ingest authentication failed."

    def __init__(self) -> None:
        super().__init__(self.detail)


class IngestRequestExpiredError(IngestAuthError):
    detail = "Ingest request expired."


class ShopInstallationNotFoundError(IngestAuthError):
    detail = "Shop installation not found."


class InvalidIngestTokenError(IngestAuthError):
    detail = "Invalid ingest token."


class IngestAuthService:
    def __init__(
        self,
        settings: Settings,
        *,
        repository: InstallationRepository | None = None,
        time_provider: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository or InstallationRepository()
        self._time_provider = time_provider or time.time

    async def verify_public_token(
        self,
        *,
        shop_domain: str,
        public_token: str,
        timestamp: int,
    ) -> ShopInstallation:
        current_time = int(self._time_provider())
        if abs(current_time - timestamp) > self._settings.ingest_token_ttl_seconds:
            raise IngestRequestExpiredError()

        installation = await self._repository.get_by_shop_domain(shop_domain)
        if installation is None:
            raise ShopInstallationNotFoundError()

        expected = hashlib.sha256(
            f"{shop_domain}:{public_token}:{timestamp}".encode()
        ).hexdigest()
        current = hashlib.sha256(
            f"{shop_domain}:{installation.public_token}:{timestamp}".encode()
        ).hexdigest()
        if not secrets.compare_digest(expected, current):
            raise InvalidIngestTokenError()
        return installation
