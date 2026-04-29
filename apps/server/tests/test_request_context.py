from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import HTTPException, Request
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

import job_queue
import main
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
        gemini_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://example.com",
    )


def test_create_app_initializes_redis_client(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def _fake_init_redis_client(url: str) -> None:
        seen["url"] = url

    monkeypatch.setattr(main, "init_redis_client", _fake_init_redis_client, raising=False)

    create_app(_settings(sqlite_database_url, redis_url))

    assert seen == {"url": redis_url}


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
async def test_enqueue_json_uses_initialized_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pushed: list[tuple[str, dict[str, str]]] = []

    class FakeRedis:
        async def lpush(self, queue_name: str, payload: str) -> None:
            pushed.append((queue_name, json.loads(payload)))

    monkeypatch.setattr(job_queue, "get_redis_client", lambda: FakeRedis(), raising=False)

    result = await job_queue.enqueue_json(
        payload={"shop_id": "shop-1"},
        queue_name="sku-lens:rollups",
    )

    assert result is True
    assert pushed == [("sku-lens:rollups", {"shop_id": "shop-1"})]


@pytest.mark.asyncio
async def test_job_dispatch_service_uses_plain_after_commit_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[tuple[str, dict[str, object]]] = []
    callbacks = AfterCommitCallbacks()

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

    job_ids = JobDispatchService().enqueue_rollup(
        after_commit_callbacks=callbacks,
        shop_id="shop-1",
        stat_date=date(2026, 4, 27),
    )

    assert len(job_ids) == 1
    assert enqueued == []

    await callbacks.run()

    assert enqueued == [
        (
            "sku-lens:rollups",
            {"job_id": job_ids[0], "shop_id": "shop-1", "stat_date": "2026-04-27"},
        )
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
    enqueued: list[tuple[str, dict[str, object]]] = []

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

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
    assert len(enqueued) == 1
    queue_name, payload = enqueued[0]
    assert queue_name == "sku-lens:diagnoses"
    assert isinstance(payload["job_id"], str)
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
    enqueued: list[tuple[str, dict[str, object]]] = []

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

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
    assert len(enqueued) == 1
    queue_name, payload = enqueued[0]
    assert queue_name == "sku-lens:diagnoses"
    assert isinstance(payload["job_id"], str)
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
    enqueued: list[tuple[str, dict[str, object]]] = []

    async def _fake_enqueue_json(
        *,
        payload: dict[str, object],
        queue_name: str,
    ) -> bool:
        enqueued.append((queue_name, payload))
        return True

    monkeypatch.setattr(
        "services.job_dispatch.enqueue_json",
        _fake_enqueue_json,
        raising=False,
    )

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
    assert enqueued == []
