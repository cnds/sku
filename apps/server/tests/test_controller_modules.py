from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

import controllers.analytics as analytics_controller
import controllers.diagnosis as diagnosis_controller
import controllers.ingestion as ingestion_controller
from config import Settings
from main import create_app
from schemas import (
    ComponentComparison,
    DiagnosisResult,
    FunnelComparison,
    FunnelSnapshot,
    LeaderboardEntry,
    LeaderboardType,
    ProductAnalysisResult,
    TimeWindow,
)
from services.diagnosis import DiagnosisNotFoundError
from services.ingest_auth import IngestRequestExpiredError


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


def _route_entries(app: FastAPI, path: str) -> list[tuple[tuple[str, ...], str]]:
    return sorted(
        (
            tuple(sorted(route.methods - {"HEAD", "OPTIONS"})),
            route.endpoint.__module__,
        )
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == path
    )


def test_analytics_routes_are_owned_by_expected_modules(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    assert _route_entries(app, "/api/leaderboard") == [
        (("GET",), "controllers.analytics"),
    ]
    assert _route_entries(app, "/api/products/{product_id}/analysis") == [
        (("GET",), "controllers.analytics"),
    ]
    assert _route_entries(app, "/api/products/{product_id}/diagnosis") == [
        (("GET",), "controllers.diagnosis"),
        (("POST",), "controllers.diagnosis"),
    ]


def test_diagnosis_routes_are_owned_by_diagnosis_controller(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    assert _route_entries(app, "/api/products/{product_id}/diagnosis") == [
        (("GET",), "controllers.diagnosis"),
        (("POST",), "controllers.diagnosis"),
    ]


def test_ingest_route_is_owned_by_ingestion_controller(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    assert _route_entries(app, "/ingest/events") == [
        (("POST",), "controllers.ingestion"),
    ]


def test_shopify_routes_are_owned_by_shopify_controller(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    assert _route_entries(app, "/shopify/oauth/callback") == [
        (("POST",), "controllers.shopify"),
    ]
    assert _route_entries(app, "/shopify/webhooks/orders/create") == [
        (("POST",), "controllers.shopify"),
    ]


def test_all_business_routes_are_owned_by_controller_modules(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    expected = {
        ("/api/leaderboard", ("GET",), "controllers.analytics"),
        ("/api/products/{product_id}/analysis", ("GET",), "controllers.analytics"),
        ("/api/products/{product_id}/diagnosis", ("GET",), "controllers.diagnosis"),
        ("/api/products/{product_id}/diagnosis", ("POST",), "controllers.diagnosis"),
        ("/ingest/events", ("POST",), "controllers.ingestion"),
        ("/shopify/oauth/callback", ("POST",), "controllers.shopify"),
        ("/shopify/webhooks/orders/create", ("POST",), "controllers.shopify"),
    }
    actual = {
        (
            route.path,
            tuple(sorted(route.methods - {"HEAD", "OPTIONS"})),
            route.endpoint.__module__,
        )
        for route in app.routes
        if isinstance(route, APIRoute)
    }

    assert actual == expected


@pytest.mark.asyncio
async def test_leaderboard_endpoint_smoke(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    seen: dict[str, object] = {}
    expected = [
        LeaderboardEntry(
            product_id="prod-1",
            views=11,
            add_to_carts=3,
            orders=2,
            score=1.5,
        )
    ]

    class FakeProductAnalysisService:
        def __init__(self, *, settings: Settings | None = None) -> None:
            seen["settings"] = settings

        async def get_leaderboard(
            self,
            *,
            board: LeaderboardType,
            shop_id: str,
            window: TimeWindow,
        ) -> list[LeaderboardEntry]:
            seen["board"] = board
            seen["shop_id"] = shop_id
            seen["window"] = window
            return expected

    monkeypatch.setattr(
        analytics_controller,
        "ProductAnalysisService",
        FakeProductAnalysisService,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/leaderboard", params={"shop_id": "shop-123"})

    assert response.status_code == 200
    assert response.json() == [entry.model_dump(mode="json") for entry in expected]
    assert seen == {
        "settings": None,
        "board": LeaderboardType.BLACK,
        "shop_id": "shop-123",
        "window": TimeWindow.HOURS_24,
    }


@pytest.mark.asyncio
async def test_product_analysis_endpoint_smoke(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    seen: dict[str, object] = {}
    expected = ProductAnalysisResult(
        product_id="prod-1",
        benchmark_product_id="benchmark-1",
        gap=2.5,
        funnel=FunnelComparison(
            target=FunnelSnapshot(views=11, add_to_carts=3, orders=2),
            benchmark=FunnelSnapshot(views=40, add_to_carts=10, orders=8),
        ),
        component_comparisons=[
            ComponentComparison(
                component_id="reviews",
                target_clicks=5,
                benchmark_clicks=8,
                target_ctr=0.45,
                benchmark_ctr=0.2,
                delta=-0.25,
            )
        ],
    )

    class FakeProductAnalysisService:
        def __init__(self, *, settings: Settings | None = None) -> None:
            seen["settings"] = settings

        async def get_product_analysis(
            self,
            *,
            product_id: str,
            shop_id: str,
            window: TimeWindow,
        ) -> ProductAnalysisResult:
            seen["product_id"] = product_id
            seen["shop_id"] = shop_id
            seen["window"] = window
            return expected

    monkeypatch.setattr(
        analytics_controller,
        "ProductAnalysisService",
        FakeProductAnalysisService,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/products/prod-1/analysis",
            params={"shop_id": "shop-123"},
        )

    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")
    assert seen == {
        "settings": settings,
        "product_id": "prod-1",
        "shop_id": "shop-123",
        "window": TimeWindow.HOURS_24,
    }


@pytest.mark.asyncio
async def test_ingestion_endpoint_maps_domain_auth_errors_to_http(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    seen: dict[str, object] = {}

    class FakeIngestAuthService:
        def __init__(self, service_settings: Settings) -> None:
            seen["settings"] = service_settings

        async def verify_public_token(
            self,
            *,
            shop_domain: str,
            public_token: str,
            timestamp: int,
        ) -> None:
            seen["shop_domain"] = shop_domain
            seen["public_token"] = public_token
            seen["timestamp"] = timestamp
            raise IngestRequestExpiredError()

    monkeypatch.setattr(
        ingestion_controller,
        "IngestAuthService",
        FakeIngestAuthService,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/ingest/events",
            json={
                "shop_domain": "demo.myshopify.com",
                "visitor_id": "visitor-1",
                "session_id": "session-1",
                "events": [],
            },
            headers={
                "X-SKU-Lens-Public-Token": "public-1",
                "X-SKU-Lens-Timestamp": "1700000000",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Ingest request expired."}
    assert seen == {
        "settings": settings,
        "shop_domain": "demo.myshopify.com",
        "public_token": "public-1",
        "timestamp": 1700000000,
    }


@pytest.mark.asyncio
async def test_diagnosis_endpoint_maps_domain_not_found_to_http(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    seen: dict[str, object] = {}

    class FakeProductDiagnosisService:
        async def require_report(
            self,
            *,
            product_id: str,
            shop_id: str,
            window: TimeWindow,
        ) -> DiagnosisResult:
            seen["product_id"] = product_id
            seen["shop_id"] = shop_id
            seen["window"] = window
            raise DiagnosisNotFoundError()

    monkeypatch.setattr(
        diagnosis_controller,
        "ProductDiagnosisService",
        FakeProductDiagnosisService,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/products/missing-product/diagnosis",
            params={"shop_id": "shop-1"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Diagnosis not found."}
    assert seen == {
        "product_id": "missing-product",
        "shop_id": "shop-1",
        "window": TimeWindow.HOURS_24,
    }
