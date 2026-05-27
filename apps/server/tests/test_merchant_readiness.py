from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlmodel import select

from config import Settings
from db import create_session_factory, db_session_context, init_db
from main import create_app
from models import (
    DailyProductStat,
    DiagnosisStatus,
    EventType,
    ProductDiagnosis,
    RawEvent,
    RecommendationFeedback,
    ShopInstallation,
)
from security.shopify import build_shopify_oauth_hmac
from services.shopify import ShopifyOAuthService


def _settings(
    sqlite_database_url: str,
    redis_url: str,
    *,
    internal_review: bool = False,
) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-api-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://app.example.test",
        shopify_scopes="read_orders,read_products",
        shopify_webhook_base_url="https://api.example.test",
        sku_lens_internal_review=internal_review,
    )


@pytest.mark.asyncio
async def test_oauth_start_redirects_to_shopify_authorization_with_state_cookie(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    async with AsyncClient(
        follow_redirects=False,
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/shopify/oauth/start",
            params={"shop": "demo.myshopify.com"},
        )

    assert response.status_code == 307
    state_cookie = response.cookies.get("sku_lens_oauth_state")
    assert state_cookie
    location = urlparse(response.headers["location"])
    assert location.scheme == "https"
    assert location.netloc == "demo.myshopify.com"
    assert location.path == "/admin/oauth/authorize"
    query = parse_qs(location.query)
    assert query["client_id"] == ["test-api-key"]
    assert query["scope"] == ["read_orders,read_products"]
    assert query["redirect_uri"] == ["https://api.example.test/shopify/oauth/callback"]
    assert query["state"] == [state_cookie]


@pytest.mark.asyncio
async def test_oauth_start_rejects_invalid_shop_domain(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/shopify/oauth/start",
            params={"shop": "https://evil.example"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Shopify shop domain."}


@pytest.mark.asyncio
async def test_oauth_callback_requires_matching_state_cookie(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    params = {
        "code": "oauth-code",
        "shop": "demo.myshopify.com",
        "state": "returned-state",
        "timestamp": "1700000000",
    }
    params["hmac"] = build_shopify_oauth_hmac(settings.shopify_api_secret, params)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        client.cookies.set("sku_lens_oauth_state", "different-state")
        response = await client.get(
            "/shopify/oauth/callback",
            params=params,
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Shopify OAuth state."}


@pytest.mark.asyncio
async def test_oauth_callback_installs_shop_and_redirects_to_onboarding(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    await init_db(app.state.session_factory.engine)
    expected_oauth_value = "oauth-value"

    async def fake_exchange_access_token(
        self: ShopifyOAuthService,
        *,
        code: str,
        shop_domain: str,
    ) -> str:
        del self
        assert code == "oauth-code"
        assert shop_domain == "demo.myshopify.com"
        return expected_oauth_value

    async def fake_fetch_shop_timezone(
        self: ShopifyOAuthService,
        *,
        access_token: str,
        shop_domain: str,
    ) -> str:
        del self
        assert access_token == expected_oauth_value
        assert shop_domain == "demo.myshopify.com"
        return "America/New_York"

    monkeypatch.setattr(ShopifyOAuthService, "exchange_access_token", fake_exchange_access_token)
    monkeypatch.setattr(ShopifyOAuthService, "fetch_shop_timezone", fake_fetch_shop_timezone)

    params = {
        "code": "oauth-code",
        "host": "admin.shopify.com/store/demo",
        "shop": "demo.myshopify.com",
        "state": "state-1",
        "timestamp": "1700000000",
    }
    params["hmac"] = build_shopify_oauth_hmac(settings.shopify_api_secret, params)

    async with AsyncClient(
        follow_redirects=False,
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        client.cookies.set("sku_lens_oauth_state", "state-1")
        response = await client.get(
            "/shopify/oauth/callback",
            params=params,
        )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://app.example.test/onboarding?"
        "shop=demo.myshopify.com&window=24h&host=admin.shopify.com%2Fstore%2Fdemo"
    )
    assert response.cookies.get("sku_lens_oauth_state") is None

    async with app.state.session_factory() as session:
        installation = (
            await session.exec(
                select(ShopInstallation).where(
                    ShopInstallation.shop_domain == "demo.myshopify.com"
                )
            )
        ).one()

    assert installation.access_token == expected_oauth_value
    assert installation.timezone_name == "America/New_York"


@pytest.mark.asyncio
async def test_oauth_callback_requires_authorization_code(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    settings = _settings(sqlite_database_url, redis_url)
    app = create_app(settings)
    params = {
        "shop": "demo.myshopify.com",
        "state": "state-1",
        "timestamp": "1700000000",
    }
    params["hmac"] = build_shopify_oauth_hmac(settings.shopify_api_secret, params)

    async with AsyncClient(
        follow_redirects=False,
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        client.cookies.set("sku_lens_oauth_state", "state-1")
        response = await client.get(
            "/shopify/oauth/callback",
            params=params,
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Missing Shopify OAuth authorization code."}


@pytest.mark.asyncio
async def test_onboarding_status_explains_missing_installation(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/onboarding/status",
            params={"shop_id": "missing.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["installed"] is False
    assert payload["public_token"] is None
    assert payload["ingest_endpoint"] == "https://api.example.test/ingest/events"
    assert payload["app_embed_deep_link"].startswith(
        "https://missing.myshopify.com/admin/themes/current/editor"
    )
    assert payload["integration_health"]["status"] == "not_connected"
    checklist = {item["key"]: item for item in payload["checklist"]}
    assert checklist["install"]["status"] == "action"
    assert checklist["first_raw_event"]["status"] == "pending"


@pytest.mark.asyncio
async def test_onboarding_status_returns_token_health_and_next_steps_for_installed_shop(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    now_utc = datetime.now(UTC).replace(microsecond=0)
    expected_public_value = "public-1"

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="UTC",
            )
        )
        session.add(
            RawEvent(
                shop_id="demo.myshopify.com",
                shop_domain="demo.myshopify.com",
                visitor_id="visitor-1",
                session_id="session-1",
                event_type=EventType.VIEW,
                product_id="product-1",
                channel="sdk",
                occurred_at=now_utc,
            )
        )
        session.add(
            DailyProductStat(
                shop_id="demo.myshopify.com",
                product_id="product-1",
                stat_date=now_utc.date(),
                views=8,
            )
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/onboarding/status",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["installed"] is True
    assert payload["public_token"] == expected_public_value
    assert payload["last_raw_event_at"] == now_utc.isoformat().replace("+00:00", "Z")
    assert payload["integration_health"]["coverage"]["views"] == 8
    checklist = {item["key"]: item for item in payload["checklist"]}
    assert checklist["install"]["status"] == "done"
    assert checklist["first_raw_event"]["status"] == "done"
    assert checklist["pdp_views"]["status"] == "done"
    assert checklist["component_tracking"]["status"] == "action"


@pytest.mark.asyncio
async def test_recommendation_feedback_appends_rows_and_reports_latest_action(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/recommendation-feedback",
            json={
                "action": "will_try",
                "board": "leaker",
                "product_id": "product-1",
                "shop_id": "demo.myshopify.com",
                "window": "24h",
            },
        )
        second = await client.post(
            "/api/recommendation-feedback",
            json={
                "action": "already_fixed",
                "board": "leaker",
                "product_id": "product-1",
                "shop_id": "demo.myshopify.com",
                "window": "24h",
            },
        )

    assert first.status_code == 201
    assert first.json()["latest_action"] == "will_try"
    assert second.status_code == 201
    assert second.json()["latest_action"] == "already_fixed"

    async with app.state.session_factory() as session:
        rows = (
            await session.exec(
                text(
                    "SELECT action FROM recommendation_feedback "
                    "WHERE shop_id = 'demo.myshopify.com' "
                    "ORDER BY id"
                )
            )
        ).all()

    assert [row[0] for row in rows] == ["will_try", "already_fixed"]


@pytest.mark.asyncio
async def test_recommendation_feedback_persists_board_window_and_card_context(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/recommendation-feedback",
            json={
                "action": "will_try",
                "board": "leaker",
                "board_date": "2026-05-27",
                "card_rank": 1,
                "context": {
                    "primary_step": "pdp_add_to_cart",
                    "surface": "today_priorities",
                },
                "product_id": "product-1",
                "shop_id": "demo.myshopify.com",
                "window": "24h",
                "window_end_date": "2026-05-27",
                "window_start_date": "2026-05-26",
            },
        )

    assert response.status_code == 201

    async with app.state.session_factory() as session:
        feedback = (
            await session.exec(
                select(RecommendationFeedback).where(
                    RecommendationFeedback.product_id == "product-1"
                )
            )
        ).one()

    assert feedback.board_date == date(2026, 5, 27)
    assert feedback.window_start_date == date(2026, 5, 26)
    assert feedback.window_end_date == date(2026, 5, 27)
    assert feedback.card_rank == 1
    assert feedback.context_json == {
        "primary_step": "pdp_add_to_cart",
        "surface": "today_priorities",
    }


@pytest.mark.asyncio
async def test_recommendation_feedback_rejects_unknown_action(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/recommendation-feedback",
            json={
                "action": "maybe_later",
                "product_id": "product-1",
                "shop_id": "demo.myshopify.com",
                "window": "24h",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_internal_card_review_is_gated_when_disabled(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    app = create_app(_settings(sqlite_database_url, redis_url, internal_review=False))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/internal/card-review",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_internal_card_review_returns_evidence_chain_when_enabled(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    now_utc = datetime.now(UTC).replace(microsecond=0)

    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                timezone_name="UTC",
            )
        )
        session.add_all(
            [
                DailyProductStat(
                    shop_id="demo.myshopify.com",
                    product_id="leaker-1",
                    stat_date=date.today(),
                    views=100,
                    add_to_carts=3,
                    orders=0,
                    impressions=200,
                    clicks=30,
                    component_clicks_distribution={"buy_box": 3},
                    component_impressions_distribution={"buy_box": 80},
                ),
                DailyProductStat(
                    shop_id="demo.myshopify.com",
                    product_id="winner-1",
                    stat_date=date.today(),
                    views=20,
                    add_to_carts=8,
                    orders=4,
                    impressions=100,
                    clicks=20,
                    component_clicks_distribution={"buy_box": 8},
                    component_impressions_distribution={"buy_box": 20},
                ),
                ProductDiagnosis(
                    shop_id="demo.myshopify.com",
                    product_id="leaker-1",
                    window="24h",
                    snapshot_hash="hash-1",
                    status=DiagnosisStatus.READY,
                    report_markdown="Observed\nEvidence\nSuspected friction\nFirst fix",
                    summary_json={"summary": "Leaker summary"},
                    generated_at=now_utc,
                ),
                RawEvent(
                    shop_id="demo.myshopify.com",
                    shop_domain="demo.myshopify.com",
                    visitor_id="visitor-1",
                    session_id="session-1",
                    event_type=EventType.ADD_TO_CART,
                    product_id="leaker-1",
                    component_id="buy_box",
                    channel="sdk",
                    occurred_at=now_utc,
                ),
            ]
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url, internal_review=True))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/internal/card-review",
            params={"shop_id": "demo.myshopify.com", "window": "24h"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["shop_id"] == "demo.myshopify.com"
    assert payload["window"] == "24h"
    assert len(payload["cards"]) >= 1
    first_card = payload["cards"][0]
    assert first_card["priority_card"]["product_id"] == "leaker-1"
    assert first_card["aggregate_evidence"]["views"] == 100
    assert first_card["raw_event_counts"]["add_to_cart"] == 1
    assert first_card["derived_signal"]["signal_state"] in {
        "Ready",
        "Weak signal",
        "Insufficient data",
        "Tracking issue",
    }
    assert first_card["ai_summary"]["summary"] == "Leaker summary"
    assert first_card["merchant_copy"]["first_fix"]
