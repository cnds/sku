from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException, Request
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

import main
import services.job_dispatch as job_dispatch_module
from config import Settings
from db import get_db_session, init_db
from main import create_app
from models import ShopInstallation
from security.shopify import build_shopify_oauth_hmac
from services.diagnosis import DiagnosisNotFoundError
from services.ingest_auth import (
    IngestRequestExpiredError,
    InvalidIngestTokenError,
    ShopInstallationNotFoundError,
)
from services.job_dispatch import AfterCommitCallbacks, JobDispatchService
from services.shopify import InvalidShopifyOAuthCallbackError


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://example.com",
    )


def test_create_app_does_not_initialize_redis_list_client(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _fake_init_redis_client(url: str) -> None:
        nonlocal called
        del url
        called = True

    monkeypatch.setattr(main, "init_redis_client", _fake_init_redis_client, raising=False)

    create_app(_settings(sqlite_database_url, redis_url))

    assert called is False
    assert job_dispatch_module.celery_app.conf.broker_url == redis_url


@pytest.mark.asyncio
async def test_db_session_middleware_commits_successful_requests(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    @app.post("/test/context/commit")
    async def _commit_route() -> dict[str, bool]:
        session = get_db_session()
        session.add(
            ShopInstallation(
                shop_domain="committed.myshopify.com",
                public_token="token-1",
            )
        )
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/test/context/commit")

    assert response.status_code == 200
    async with app.state.session_factory() as session:
        installation = (
            await session.exec(
                select(ShopInstallation).where(
                    ShopInstallation.shop_domain == "committed.myshopify.com"
                )
            )
        ).one()

    assert installation.public_token is not None


@pytest.mark.asyncio
async def test_db_session_middleware_rolls_back_failed_requests(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    @app.post("/test/context/rollback")
    async def _rollback_route() -> None:
        session = get_db_session()
        session.add(
            ShopInstallation(
                shop_domain="rolled-back.myshopify.com",
                public_token="token-2",
            )
        )
        raise HTTPException(status_code=400, detail="boom")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/test/context/rollback")

    assert response.status_code == 400
    async with app.state.session_factory() as session:
        installation = (
            await session.exec(
                select(ShopInstallation).where(
                    ShopInstallation.shop_domain == "rolled-back.myshopify.com"
                )
            )
        ).first()

    assert installation is None


@pytest.mark.asyncio
async def test_db_session_middleware_propagates_request_id_and_logs_completed_requests(
    sqlite_database_url: str,
    redis_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    @app.get("/test/context/request-log")
    async def _request_log_route() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/test/context/request-log",
            headers={"X-SKU-Lens-Request-Id": "req-123"},
        )
    captured = capsys.readouterr().err

    assert response.status_code == 200
    assert response.headers["X-SKU-Lens-Request-Id"] == "req-123"
    assert "request completed" in captured
    assert "request_id=req-123" in captured
    assert "method=GET" in captured
    assert "path=/test/context/request-log" in captured
    assert "status=200" in captured


@pytest.mark.asyncio
async def test_job_dispatch_service_publishes_rollups_after_commit_with_job_id_as_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object]] = []
    callbacks = AfterCommitCallbacks()

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    job_ids = JobDispatchService().enqueue_rollup(
        after_commit_callbacks=callbacks,
        shop_id="shop-1",
        stat_date=date(2026, 4, 27),
    )

    assert len(job_ids) == 1
    assert sent == []

    await callbacks.run()

    assert sent == [
        {
            "name": "sku_lens.rollup.process",
            "kwargs": {"job_id": job_ids[0], "shop_id": "shop-1", "stat_date": "2026-04-27"},
            "queue": "sku-lens:rollups",
            "task_id": job_ids[0],
        }
    ]


@pytest.mark.asyncio
async def test_app_maps_diagnosis_domain_errors_to_http_responses(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    @app.get("/test/context/diagnosis-not-found")
    async def _diagnosis_not_found_route() -> None:
        raise DiagnosisNotFoundError()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/test/context/diagnosis-not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": "Diagnosis not found."}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (IngestRequestExpiredError(), 401, "Ingest request expired."),
        (InvalidIngestTokenError(), 401, "Invalid ingest token."),
        (ShopInstallationNotFoundError(), 404, "Shop installation not found."),
    ],
)
async def test_app_maps_ingest_auth_domain_errors_to_http_responses(
    sqlite_database_url: str,
    redis_url: str,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    @app.get("/test/context/ingest-auth-error")
    async def _ingest_auth_error_route() -> None:
        raise error

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/test/context/ingest-auth-error")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


@pytest.mark.asyncio
async def test_app_maps_shopify_oauth_callback_errors_to_http_responses(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    @app.get("/test/context/shopify-oauth-error")
    async def _shopify_oauth_error_route() -> None:
        raise InvalidShopifyOAuthCallbackError()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/test/context/shopify-oauth-error")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Shopify OAuth callback signature."}


@pytest.mark.asyncio
async def test_shopify_oauth_callback_rejects_unsigned_request(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/shopify/oauth/callback",
            params={
                "shop": "demo.myshopify.com",
                "code": "oauth-code",
                "timestamp": "1700000000",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Shopify OAuth callback signature."}


@pytest.mark.asyncio
async def test_shopify_oauth_callback_accepts_valid_signed_request(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    params = {
        "shop": "demo.myshopify.com",
        "timestamp": "1700000000",
    }
    params["hmac"] = build_shopify_oauth_hmac(settings.shopify_api_secret, params)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/shopify/oauth/callback",
            params=params,
        )

    assert response.status_code == 200
    assert response.json()["shop"] == "demo.myshopify.com"
    assert response.json()["public_token"]


@pytest.mark.asyncio
async def test_diagnosis_jobs_enqueue_after_commit_via_dispatch_service(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object]] = []

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)
    snapshot = {
        "views": 120,
        "add_to_carts": 9,
        "orders": 2,
        "component_clicks_distribution": {"size_chart": 0},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/products/product-1/diagnosis",
            params={"shop_id": "shop-1"},
            json=snapshot,
        )

    assert response.status_code == 200
    assert len(sent) == 1
    message = sent[0]
    payload = message["kwargs"]
    assert message["name"] == "sku_lens.diagnosis.process"
    assert message["queue"] == "sku-lens:diagnoses"
    assert isinstance(payload["job_id"], str)
    assert message["task_id"] == payload["job_id"]
    assert payload["product_id"] == "product-1"
    assert payload["shop_id"] == "shop-1"
    assert payload["snapshot"]["views"] == snapshot["views"]
    assert payload["snapshot"]["orders"] == snapshot["orders"]
    assert payload["snapshot_hash"] == response.json()["snapshot_hash"]
    assert payload["window"] == "24h"


@pytest.mark.asyncio
async def test_diagnosis_endpoint_persists_pending_report_and_avoids_duplicate_enqueue(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object]] = []

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)
    snapshot = {
        "views": 120,
        "add_to_carts": 9,
        "orders": 2,
        "component_clicks_distribution": {"size_chart": 0},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/products/product-1/diagnosis",
            params={"shop_id": "shop-1"},
            json=snapshot,
        )
        second = await client.post(
            "/api/products/product-1/diagnosis",
            params={"shop_id": "shop-1"},
            json=snapshot,
        )
        fetched = await client.get(
            "/api/products/product-1/diagnosis",
            params={"shop_id": "shop-1"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert fetched.status_code == 200
    assert first.json()["status"] == "pending"
    assert second.json()["status"] == "pending"
    assert fetched.json()["status"] == "pending"
    assert fetched.json()["snapshot_hash"] == first.json()["snapshot_hash"]
    assert len(sent) == 1
    message = sent[0]
    payload = message["kwargs"]
    assert message["name"] == "sku_lens.diagnosis.process"
    assert message["queue"] == "sku-lens:diagnoses"
    assert isinstance(payload["job_id"], str)
    assert message["task_id"] == payload["job_id"]
    assert payload["product_id"] == "product-1"
    assert payload["snapshot"]["views"] == snapshot["views"]
    assert payload["snapshot"]["orders"] == snapshot["orders"]
    assert payload["snapshot_hash"] == first.json()["snapshot_hash"]


@pytest.mark.asyncio
async def test_diagnosis_jobs_do_not_enqueue_when_request_rolls_back(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object]] = []

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, object],
            queue: str,
            task_id: str,
        ) -> None:
            sent.append(
                {
                    "name": name,
                    "kwargs": kwargs,
                    "queue": queue,
                    "task_id": task_id,
                }
            )

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    @app.post("/test/context/diagnosis-rollback")
    async def _diagnosis_rollback_route(request: Request) -> None:
        JobDispatchService().enqueue_diagnosis(
            product_id="product-1",
            after_commit_callbacks=request.state.after_commit_callbacks,
            shop_id="shop-1",
            snapshot={
                "views": 120,
                "add_to_carts": 9,
                "orders": 2,
                "component_clicks_distribution": {"size_chart": 0},
            },
            snapshot_hash="snapshot-hash-1",
            window="7d",
        )
        raise HTTPException(status_code=400, detail="boom")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/test/context/diagnosis-rollback")

    assert response.status_code == 400
    assert sent == []
