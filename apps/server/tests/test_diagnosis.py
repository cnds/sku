from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import select

from db import create_session_factory, db_session_context, init_db
from models import DiagnosisStatus, ProductDiagnosis
from schemas import ProductSnapshot, TimeWindow
from services.diagnosis import DiagnosisNotFoundError, ProductDiagnosisService


@pytest.mark.asyncio
async def test_diagnosis_service_reuses_cached_report_when_snapshot_hash_matches(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ProductDiagnosisService()
    snapshot = ProductSnapshot(
        add_to_carts=12,
        component_clicks_distribution={"size_chart": 1},
        orders=4,
        views=100,
    )

    async with db_session_context(session_factory):
        cached = await service.ensure_report(
            shop_id="shop-1",
            product_id="product-1",
            snapshot=snapshot,
            window=TimeWindow.DAYS_7,
        )

    async with session_factory() as session:
        report = ProductDiagnosis(
            shop_id="shop-1",
            product_id="product-1",
            window=TimeWindow.DAYS_7.value,
            snapshot_hash=cached.snapshot_hash,
            status=DiagnosisStatus.READY,
            report_markdown="Existing report",
            generated_at=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
            summary_json={"summary": "cached"},
        )
        session.add(report)
        await session.commit()

    async with db_session_context(session_factory):
        reused = await service.ensure_report(
            shop_id="shop-1",
            product_id="product-1",
            snapshot=snapshot,
            window=TimeWindow.DAYS_7,
        )

    assert reused.status is DiagnosisStatus.READY
    assert reused.report_markdown == "Existing report"


@pytest.mark.asyncio
async def test_diagnosis_service_prepares_enqueue_request_for_pending_report(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ProductDiagnosisService()
    snapshot = ProductSnapshot(
        add_to_carts=12,
        component_clicks_distribution={"size_chart": 1},
        orders=4,
        views=100,
    )

    async with db_session_context(session_factory) as session:
        prepared = await service.prepare_report(
            shop_id="shop-1",
            product_id="product-1",
            snapshot=snapshot,
            window=TimeWindow.DAYS_7,
        )
        await session.commit()

    assert prepared.result.status is DiagnosisStatus.PENDING
    assert prepared.enqueue_request is not None
    assert prepared.enqueue_request.product_id == "product-1"
    assert prepared.enqueue_request.shop_id == "shop-1"
    assert prepared.enqueue_request.snapshot == snapshot.model_dump()
    assert prepared.enqueue_request.snapshot_hash == prepared.result.snapshot_hash
    assert prepared.enqueue_request.window == TimeWindow.DAYS_7.value

    async with session_factory() as session:
        stored = (
            await session.exec(
                select(ProductDiagnosis).where(
                    ProductDiagnosis.shop_id == "shop-1",
                    ProductDiagnosis.product_id == "product-1",
                    ProductDiagnosis.window == TimeWindow.DAYS_7.value,
                )
            )
        ).one()

    assert stored.status is DiagnosisStatus.PENDING
    assert stored.snapshot_hash == prepared.result.snapshot_hash
    assert stored.report_markdown is None
    assert stored.summary_json == {}


@pytest.mark.asyncio
async def test_diagnosis_service_does_not_prepare_duplicate_enqueue_for_same_pending_snapshot(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ProductDiagnosisService()
    snapshot = ProductSnapshot(
        add_to_carts=12,
        component_clicks_distribution={"size_chart": 1},
        orders=4,
        views=100,
    )

    async with db_session_context(session_factory) as session:
        first = await service.prepare_report(
            shop_id="shop-1",
            product_id="product-1",
            snapshot=snapshot,
            window=TimeWindow.DAYS_7,
        )
        await session.commit()

    async with db_session_context(session_factory):
        second = await service.prepare_report(
            shop_id="shop-1",
            product_id="product-1",
            snapshot=snapshot,
            window=TimeWindow.DAYS_7,
        )

    assert first.enqueue_request is not None
    assert second.result.status is DiagnosisStatus.PENDING
    assert second.result.snapshot_hash == first.result.snapshot_hash
    assert second.enqueue_request is None


@pytest.mark.asyncio
async def test_diagnosis_service_returns_stored_report_without_controller_repo_access(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ProductDiagnosisService()

    async with db_session_context(session_factory) as session:
        session.add(
            ProductDiagnosis(
                shop_id="shop-1",
                product_id="product-1",
                window=TimeWindow.DAYS_7.value,
                snapshot_hash="hash-1",
                status=DiagnosisStatus.READY,
                report_markdown="Stored report",
                generated_at=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
                summary_json={"summary": "stored"},
            )
        )
        await session.commit()

    async with db_session_context(session_factory):
        fetched = await service.get_report(
            shop_id="shop-1",
            product_id="product-1",
            window=TimeWindow.DAYS_7,
        )

    assert fetched is not None
    assert fetched.status is DiagnosisStatus.READY
    assert fetched.report_markdown == "Stored report"
    assert fetched.summary_json == {"summary": "stored"}


@pytest.mark.asyncio
async def test_diagnosis_service_raises_domain_error_when_report_is_missing(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ProductDiagnosisService()

    async with db_session_context(session_factory):
        with pytest.raises(DiagnosisNotFoundError) as exc_info:
            await service.require_report(
                shop_id="shop-1",
                product_id="missing-product",
                window=TimeWindow.DAYS_7,
            )

    assert str(exc_info.value) == "Diagnosis not found."


@pytest.mark.asyncio
async def test_diagnosis_service_ignores_stale_generated_report_for_older_snapshot(
    sqlite_database_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    service = ProductDiagnosisService()

    async with db_session_context(session_factory) as session:
        session.add(
            ProductDiagnosis(
                shop_id="shop-1",
                product_id="product-1",
                window=TimeWindow.DAYS_7.value,
                snapshot_hash="new-hash",
                status=DiagnosisStatus.READY,
                report_markdown="Newest report",
                generated_at=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
                summary_json={"summary": "newest"},
            )
        )
        await session.commit()

    async with db_session_context(session_factory):
        stored = await service.store_generated_report(
            product_id="product-1",
            report_markdown="Stale report",
            shop_id="shop-1",
            snapshot_hash="old-hash",
            summary_json={"summary": "stale"},
            window=TimeWindow.DAYS_7,
        )

    assert stored.status is DiagnosisStatus.READY
    assert stored.snapshot_hash == "new-hash"
    assert stored.report_markdown == "Newest report"
    assert stored.summary_json == {"summary": "newest"}
