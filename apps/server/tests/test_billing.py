from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from config import Settings
from db import create_session_factory, db_session_context, init_db
from main import create_app
from models import AiRefreshUsage, BillingInterval, BillingPlan, BillingStatus, ShopInstallation, ShopSubscription
from schemas import ProductSnapshot
from services import billing as billing_module

TEST_ACCESS_VALUE = "access-1"


def _settings(sqlite_database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=sqlite_database_url,
        ai_api_key="test-key",
        ingest_shared_secret="ingest-secret",
        redis_url=redis_url,
        shopify_api_key="test-api-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://app.example.test",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
        shopify_webhook_base_url="https://api.example.test",
    )


@pytest.mark.asyncio
async def test_billing_status_returns_plan_matrix_for_installed_unsubscribed_shop(
    sqlite_database_url: str,
    redis_url: str,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                access_token=TEST_ACCESS_VALUE,
            )
        )
        await session.commit()

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/billing/status", params={"shop_id": "demo.myshopify.com"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["shop_id"] == "demo.myshopify.com"
    assert payload["installed"] is True
    assert payload["is_entitled"] is False
    assert payload["subscription_status"] == "unsubscribed"
    assert payload["current_plan"] is None
    assert payload["ai_refresh"]["used"] == 0
    assert payload["ai_refresh"]["limit"] == 0
    assert payload["pdp_views"]["limit"] == 0
    assert [plan["plan"] for plan in payload["plans"]] == ["starter", "growth", "pro"]
    growth = next(plan for plan in payload["plans"] if plan["plan"] == "growth")
    assert growth["monthly_price"] == 39
    assert growth["annual_price_monthly_equivalent"] == 29
    assert growth["recommended"] is True


@pytest.mark.asyncio
async def test_subscribe_creates_shopify_subscription_and_returns_confirmation_url(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                access_token=TEST_ACCESS_VALUE,
            )
        )
        await session.commit()

    captured: dict[str, object] = {}

    async def fake_create_subscription(
        self: billing_module.ShopifyBillingClient,
        *,
        access_token: str,
        billing_interval: BillingInterval,
        plan: BillingPlan,
        replacement_behavior: str,
        return_url: str,
        shop_domain: str,
        test: bool,
        trial_days: int,
    ) -> billing_module.ShopifySubscriptionCreateResult:
        del self
        captured.update(
            {
                "access_token": access_token,
                "billing_interval": billing_interval,
                "plan": plan,
                "replacement_behavior": replacement_behavior,
                "return_url": return_url,
                "shop_domain": shop_domain,
                "test": test,
                "trial_days": trial_days,
            }
        )
        return billing_module.ShopifySubscriptionCreateResult(
            confirmation_url="https://demo.myshopify.com/admin/charges/confirm",
            subscription_id="gid://shopify/AppSubscription/1",
        )

    monkeypatch.setattr(billing_module.ShopifyBillingClient, "create_subscription", fake_create_subscription)

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/billing/subscribe",
            json={
                "billing_interval": "monthly",
                "plan": "growth",
                "shop_id": "demo.myshopify.com",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "billing_interval": "monthly",
        "confirmation_url": "https://demo.myshopify.com/admin/charges/confirm",
        "plan": "growth",
        "replacement_behavior": "STANDARD",
    }
    assert captured["access_token"] == TEST_ACCESS_VALUE
    assert captured["billing_interval"] is BillingInterval.MONTHLY
    assert captured["plan"] is BillingPlan.GROWTH
    assert captured["replacement_behavior"] == "STANDARD"
    assert captured["return_url"] == "https://api.example.test/shopify/billing/callback?shop=demo.myshopify.com"
    assert captured["shop_domain"] == "demo.myshopify.com"
    assert captured["trial_days"] == 14

    async with session_factory() as session:
        subscription = (
            await session.exec(select(ShopSubscription).where(ShopSubscription.shop_id == "demo.myshopify.com"))
        ).one()

    assert subscription.current_plan is None
    assert subscription.pending_plan is BillingPlan.GROWTH
    assert subscription.status is BillingStatus.UNSUBSCRIBED


@pytest.mark.asyncio
async def test_billing_callback_syncs_active_subscription_from_shopify(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                access_token=TEST_ACCESS_VALUE,
            )
        )
        await session.commit()

    async def fake_fetch_active_subscription(
        self: billing_module.ShopifyBillingClient,
        *,
        access_token: str,
        shop_domain: str,
    ) -> billing_module.ShopifyActiveSubscription | None:
        del self
        assert access_token == TEST_ACCESS_VALUE
        assert shop_domain == "demo.myshopify.com"
        return billing_module.ShopifyActiveSubscription(
            billing_interval=BillingInterval.MONTHLY,
            current_period_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
            name="SKU Lens Growth",
            plan=BillingPlan.GROWTH,
            shopify_subscription_id="gid://shopify/AppSubscription/2",
            status=BillingStatus.ACTIVE,
        )

    monkeypatch.setattr(
        billing_module.ShopifyBillingClient,
        "fetch_active_subscription",
        fake_fetch_active_subscription,
    )

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        follow_redirects=False,
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/shopify/billing/callback", params={"shop": "demo.myshopify.com"})

    assert response.status_code == 307
    assert response.headers["location"] == "https://app.example.test/?shop=demo.myshopify.com&window=24h"

    async with session_factory() as session:
        subscription = (
            await session.exec(select(ShopSubscription).where(ShopSubscription.shop_id == "demo.myshopify.com"))
        ).one()

    assert subscription.current_plan is BillingPlan.GROWTH
    assert subscription.status is BillingStatus.ACTIVE
    assert subscription.billing_interval is BillingInterval.MONTHLY
    assert subscription.shopify_subscription_id == "gid://shopify/AppSubscription/2"
    assert subscription.current_period_ends_at == datetime(2026, 8, 2, 0, 0)


@pytest.mark.asyncio
async def test_billing_callback_preserves_pending_downgrade(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                access_token=TEST_ACCESS_VALUE,
            )
        )
        session.add(
            ShopSubscription(
                billing_interval=BillingInterval.MONTHLY,
                current_plan=BillingPlan.PRO,
                current_period_started_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
                current_period_ends_at=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
                pending_effective_at=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
                pending_plan=BillingPlan.GROWTH,
                shop_id="demo.myshopify.com",
                shopify_subscription_id="gid://shopify/AppSubscription/current",
                status=BillingStatus.ACTIVE,
            )
        )
        await session.commit()

    async def fake_fetch_active_subscription(
        self: billing_module.ShopifyBillingClient,
        *,
        access_token: str,
        shop_domain: str,
    ) -> billing_module.ShopifyActiveSubscription | None:
        del self
        assert access_token == TEST_ACCESS_VALUE
        assert shop_domain == "demo.myshopify.com"
        return billing_module.ShopifyActiveSubscription(
            billing_interval=BillingInterval.MONTHLY,
            current_period_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
            name="SKU Lens Pro",
            plan=BillingPlan.PRO,
            shopify_subscription_id="gid://shopify/AppSubscription/current",
            status=BillingStatus.ACTIVE,
        )

    monkeypatch.setattr(
        billing_module.ShopifyBillingClient,
        "fetch_active_subscription",
        fake_fetch_active_subscription,
    )

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(
        follow_redirects=False,
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/shopify/billing/callback", params={"shop": "demo.myshopify.com"})

    assert response.status_code == 307

    async with session_factory() as session:
        subscription = (
            await session.exec(select(ShopSubscription).where(ShopSubscription.shop_id == "demo.myshopify.com"))
        ).one()

    assert subscription.current_plan is BillingPlan.PRO
    assert subscription.pending_plan is BillingPlan.GROWTH
    assert subscription.pending_effective_at == datetime(2026, 8, 2, 0, 0)


@pytest.mark.asyncio
async def test_cancelled_subscription_remains_entitled_until_period_end(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                access_token=TEST_ACCESS_VALUE,
            )
        )
        session.add(
            ShopSubscription(
                billing_interval=BillingInterval.MONTHLY,
                current_plan=BillingPlan.GROWTH,
                current_period_started_at=datetime(2099, 7, 1, 0, 0, tzinfo=UTC),
                current_period_ends_at=datetime(2099, 8, 1, 0, 0, tzinfo=UTC),
                shop_id="demo.myshopify.com",
                shopify_subscription_id="gid://shopify/AppSubscription/active",
                status=BillingStatus.ACTIVE,
            )
        )
        await session.commit()

    captured: dict[str, object] = {}

    async def fake_cancel_subscription(
        self: billing_module.ShopifyBillingClient,
        *,
        access_token: str,
        prorate: bool,
        shop_domain: str,
        subscription_id: str,
    ) -> None:
        del self
        captured.update(
            {
                "access_token": access_token,
                "prorate": prorate,
                "shop_domain": shop_domain,
                "subscription_id": subscription_id,
            }
        )

    monkeypatch.setattr(billing_module.ShopifyBillingClient, "cancel_subscription", fake_cancel_subscription)

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/billing/cancel",
            json={
                "prorate": False,
                "shop_id": "demo.myshopify.com",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["subscription_status"] == "cancelled"
    assert payload["is_entitled"] is True
    assert payload["current_plan"] == "growth"
    assert captured == {
        "access_token": TEST_ACCESS_VALUE,
        "prorate": False,
        "shop_domain": "demo.myshopify.com",
        "subscription_id": "gid://shopify/AppSubscription/active",
    }


@pytest.mark.asyncio
async def test_manual_diagnosis_refresh_consumes_quota_and_blocks_when_exhausted(
    sqlite_database_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import job_dispatch as job_dispatch_module

    session_factory = create_session_factory(sqlite_database_url)
    await init_db(session_factory.engine)
    async with db_session_context(session_factory) as session:
        session.add(
            ShopInstallation(
                shop_domain="demo.myshopify.com",
                public_token="public-1",
                access_token=TEST_ACCESS_VALUE,
            )
        )
        session.add(
            ShopSubscription(
                billing_interval=BillingInterval.MONTHLY,
                current_plan=BillingPlan.STARTER,
                current_period_started_at=datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
                current_period_ends_at=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                shop_id="demo.myshopify.com",
                status=BillingStatus.ACTIVE,
            )
        )
        session.add(AiRefreshUsage(shop_id="demo.myshopify.com", period_key="2026-07", manual_refresh_count=49))
        await session.commit()

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
            sent.append({"kwargs": kwargs, "name": name, "queue": queue, "task_id": task_id})

    monkeypatch.setattr(job_dispatch_module, "celery_app", FakeCeleryApp(), raising=False)

    app = create_app(_settings(sqlite_database_url, redis_url))
    await init_db(app.state.session_factory.engine)
    snapshot = ProductSnapshot(
        add_to_carts=12,
        component_clicks_distribution={"size_chart": 1},
        orders=4,
        views=100,
    ).model_dump()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        allowed = await client.post(
            "/api/products/product-1/diagnosis",
            params={"force": "true", "shop_id": "demo.myshopify.com", "window": "7d"},
            json=snapshot,
        )
        blocked = await client.post(
            "/api/products/product-1/diagnosis",
            params={"force": "true", "shop_id": "demo.myshopify.com", "window": "7d"},
            json=snapshot,
        )

    assert allowed.status_code == 200
    assert allowed.json()["status"] == "pending"
    assert len(sent) == 1
    assert blocked.status_code == 402
    assert blocked.json() == {
        "detail": "AI refresh quota exceeded for the current billing period.",
    }
    assert len(sent) == 1

    async with session_factory() as session:
        usage = (
            await session.exec(
                select(AiRefreshUsage).where(
                    AiRefreshUsage.shop_id == "demo.myshopify.com",
                    AiRefreshUsage.period_key == "2026-07",
                )
            )
        ).one()

    assert usage.manual_refresh_count == 50
