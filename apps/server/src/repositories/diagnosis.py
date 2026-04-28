from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from db import get_db_session
from models import DiagnosisStatus, ProductDiagnosis
from schemas import DiagnosisResult, TimeWindow


class DiagnosisRepository:
    async def get_record(
        self,
        *,
        product_id: str,
        shop_id: str,
        window: TimeWindow,
    ) -> ProductDiagnosis | None:
        return (
            await get_db_session().exec(
                select(ProductDiagnosis).where(
                    ProductDiagnosis.shop_id == shop_id,
                    ProductDiagnosis.product_id == product_id,
                    ProductDiagnosis.window == window.value,
                )
            )
        ).first()

    @staticmethod
    def to_result(diagnosis: ProductDiagnosis) -> DiagnosisResult:
        return DiagnosisResult(
            status=diagnosis.status,
            snapshot_hash=diagnosis.snapshot_hash,
            report_markdown=diagnosis.report_markdown,
            summary_json=diagnosis.summary_json,
        )

    async def upsert_pending_report(
        self,
        *,
        product_id: str,
        shop_id: str,
        snapshot_hash: str,
        window: TimeWindow,
    ) -> ProductDiagnosis:
        existing = await self.get_record(
            product_id=product_id,
            shop_id=shop_id,
            window=window,
        )

        if existing is None:
            existing = ProductDiagnosis(
                product_id=product_id,
                shop_id=shop_id,
                snapshot_hash=snapshot_hash,
                status=DiagnosisStatus.PENDING,
                window=window.value,
                report_markdown=None,
                summary_json={},
                generated_at=None,
            )
            get_db_session().add(existing)
            return existing

        existing.snapshot_hash = snapshot_hash
        existing.status = DiagnosisStatus.PENDING
        existing.report_markdown = None
        existing.summary_json = {}
        existing.generated_at = None
        return existing

    async def store_generated_report(
        self,
        *,
        product_id: str,
        report_markdown: str,
        shop_id: str,
        snapshot_hash: str,
        summary_json: dict[str, Any],
        window: TimeWindow,
    ) -> DiagnosisResult:
        existing = await self.get_record(
            product_id=product_id,
            shop_id=shop_id,
            window=window,
        )

        if existing is None:
            existing = ProductDiagnosis(
                product_id=product_id,
                shop_id=shop_id,
                snapshot_hash=snapshot_hash,
                status=DiagnosisStatus.READY,
                window=window.value,
                report_markdown=report_markdown,
                summary_json=summary_json,
                generated_at=datetime.now(UTC),
            )
            get_db_session().add(existing)
        elif existing.snapshot_hash == snapshot_hash:
            existing.snapshot_hash = snapshot_hash
            existing.status = DiagnosisStatus.READY
            existing.report_markdown = report_markdown
            existing.summary_json = summary_json
            existing.generated_at = datetime.now(UTC)
        else:
            return self.to_result(existing)

        return self.to_result(existing)
