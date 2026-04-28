from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast

from repositories.diagnosis import DiagnosisRepository
from schemas import DiagnosisResult, ProductSnapshot, TimeWindow


class DiagnosisNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("Diagnosis not found.")


@dataclass(slots=True)
class DiagnosisEnqueueRequest:
    product_id: str
    shop_id: str
    snapshot: dict[str, Any]
    snapshot_hash: str
    window: str


@dataclass(slots=True)
class DiagnosisPreparation:
    result: DiagnosisResult
    enqueue_request: DiagnosisEnqueueRequest | None


class ProductDiagnosisService:
    def __init__(self, repository: DiagnosisRepository | None = None) -> None:
        self._repository = repository or DiagnosisRepository()

    async def prepare_report(
        self,
        *,
        product_id: str,
        shop_id: str,
        snapshot: ProductSnapshot,
        window: TimeWindow,
    ) -> DiagnosisPreparation:
        snapshot_hash = self._snapshot_hash(snapshot)
        existing = await self._repository.get_record(
            product_id=product_id,
            shop_id=shop_id,
            window=window,
        )

        if existing and existing.snapshot_hash == snapshot_hash:
            return DiagnosisPreparation(
                result=self._repository.to_result(existing),
                enqueue_request=None,
            )

        pending = await self._repository.upsert_pending_report(
            product_id=product_id,
            shop_id=shop_id,
            snapshot_hash=snapshot_hash,
            window=window,
        )

        return DiagnosisPreparation(
            result=self._repository.to_result(pending),
            enqueue_request=DiagnosisEnqueueRequest(
                product_id=product_id,
                shop_id=shop_id,
                snapshot=snapshot.model_dump(),
                snapshot_hash=snapshot_hash,
                window=window.value,
            ),
        )

    async def get_report(
        self,
        *,
        product_id: str,
        shop_id: str,
        window: TimeWindow,
    ) -> DiagnosisResult | None:
        diagnosis = await self._repository.get_record(
            product_id=product_id,
            shop_id=shop_id,
            window=window,
        )
        if diagnosis is None:
            return None
        return self._repository.to_result(diagnosis)

    async def require_report(
        self,
        *,
        product_id: str,
        shop_id: str,
        window: TimeWindow,
    ) -> DiagnosisResult:
        diagnosis = await self.get_report(
            product_id=product_id,
            shop_id=shop_id,
            window=window,
        )
        if diagnosis is None:
            raise DiagnosisNotFoundError()
        return diagnosis

    async def ensure_report(
        self,
        *,
        product_id: str,
        shop_id: str,
        snapshot: ProductSnapshot,
        window: TimeWindow,
    ) -> DiagnosisResult:
        prepared = await self.prepare_report(
            product_id=product_id,
            shop_id=shop_id,
            snapshot=snapshot,
            window=window,
        )
        return prepared.result

    @staticmethod
    def _snapshot_hash(snapshot: ProductSnapshot) -> str:
        encoded = json.dumps(snapshot.model_dump(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def store_generated_report(
        self,
        *,
        product_id: str,
        report_markdown: str,
        shop_id: str,
        snapshot_hash: str,
        summary_json: dict[str, str],
        window: TimeWindow,
    ) -> DiagnosisResult:
        return await self._repository.store_generated_report(
            product_id=product_id,
            report_markdown=report_markdown,
            shop_id=shop_id,
            snapshot_hash=snapshot_hash,
            summary_json=cast(dict[str, str], summary_json),
            window=window,
        )
