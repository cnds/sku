from __future__ import annotations

import json

import httpx
import pytest

from config import Settings
from schemas import ProductSnapshot
from services.ai import AIDiagnosisService


def _settings(
    *,
    api_key: str = "test-key",
    base_url: str = "https://ai.example.test/v1",
    model: str = "sku-diagnosis-model",
) -> Settings:
    return Settings(
        ai_api_key=api_key,
        ai_base_url=base_url,
        ai_model=model,
        database_url="sqlite+aiosqlite:///test.db",
        ingest_shared_secret="ingest-secret",
        redis_url="redis://localhost:6379/0",
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
        shopify_webhook_base_url="https://example.com",
    )


def _settings_without_api_key() -> Settings:
    return Settings(
        ai_api_key="",
        ai_base_url="https://ai.example.test/v1",
        ai_model="sku-diagnosis-model",
        database_url="sqlite+aiosqlite:///test.db",
        ingest_shared_secret="ingest-secret",
        redis_url="redis://localhost:6379/0",
        shopify_api_key="test-key",
        shopify_api_secret="test-secret",
        shopify_app_url="https://example.com",
        shopify_scopes="read_products,read_orders,write_pixels,read_customer_events",
        shopify_webhook_base_url="https://example.com",
    )


def _snapshot() -> ProductSnapshot:
    return ProductSnapshot(
        views=120,
        add_to_carts=9,
        orders=2,
        component_clicks_distribution={"size_chart": 0},
        impressions=320,
        clicks=42,
        media_interactions=8,
        variant_changes=5,
        total_dwell_ms=185_000,
        engage_count=20,
        avg_scroll_pct=61,
        component_impressions_distribution={"size_chart": 30},
    )


@pytest.mark.asyncio
async def test_ai_service_posts_chat_completions_request_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "## Observed\nTraffic is engaged but not converting.\n\n"
                                "## Evidence\n120 views and 2 orders.\n\n"
                                "## Suspected friction\nFit confidence is weak.\n\n"
                                "## First fix to try\nClarify fit."
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        report_markdown, summary = await AIDiagnosisService(
            _settings(),
            http_client=client,
        ).generate_report(snapshot=_snapshot())

    assert len(requests) == 1
    assert str(requests[0].url) == "https://ai.example.test/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "sku-diagnosis-model"
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    assert "cautious Shopify merchandising analyst" in payload["messages"][0]["content"]
    assert "do not invent page content" in payload["messages"][0]["content"]
    prompt = payload["messages"][1]["content"]
    assert "## Observed" in prompt
    assert "## First fix to try" in prompt
    assert "not a generic ecommerce checklist" in prompt
    assert "Anchor the diagnosis to one observed step" in prompt
    assert "Do not claim causality" in prompt
    assert "Page views (all sources): 120" in prompt
    assert "Collection/listing CTR: 13.1%" in prompt
    assert "PDP view to add-to-cart rate: 7.5%" in prompt
    assert "Add-to-cart to order rate: 22.2%" in prompt
    assert "Strongest component signal: size_chart: 0 clicks from 30 impressions (0.0% CTR)" in prompt
    assert report_markdown.startswith("## Observed")
    assert summary == {
        "primary_issue": "Observed",
        "recommended_action": "Review the markdown report and prioritize the first action item.",
        "source": "openai-compatible",
    }


@pytest.mark.asyncio
async def test_ai_service_derives_priority_advice_from_diagnosis_sections() -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "## Observed\nTraffic is engaged but not converting.\n\n"
                                "## Evidence\n120 views and 2 orders.\n\n"
                                "## Suspected friction\nAI says fit confidence is weak.\n\n"
                                "## First fix to try\nAI says move fit guidance beside the buy box."
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        advice = await AIDiagnosisService(
            _settings(),
            http_client=client,
        ).generate_priority_advice(
            fallback_first_fix="Fallback first fix.",
            fallback_suspected_friction="Fallback friction.",
            snapshot=_snapshot(),
        )

    assert advice.suspected_friction == "AI says fit confidence is weak."
    assert advice.first_fix == "AI says move fit guidance beside the buy box."
    assert advice.source == "openai-compatible"


@pytest.mark.asyncio
async def test_ai_service_uses_fallback_when_api_key_is_placeholder() -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        report_markdown, summary = await AIDiagnosisService(
            _settings(api_key="replace-me"),
            http_client=client,
        ).generate_report(snapshot=_snapshot())

    assert "## Observed" in report_markdown
    assert "## Evidence" in report_markdown
    assert "## Suspected friction" in report_markdown
    assert "## First fix to try" in report_markdown
    assert summary["source"] == "fallback"


@pytest.mark.asyncio
async def test_ai_service_uses_fallback_when_api_key_is_not_configured() -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        report_markdown, summary = await AIDiagnosisService(
            _settings_without_api_key(),
            http_client=client,
        ).generate_report(snapshot=_snapshot())

    assert "## First fix to try" in report_markdown
    assert summary["source"] == "fallback"


@pytest.mark.asyncio
async def test_ai_service_uses_fallback_when_chat_response_content_is_empty() -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"choices": [{"message": {"content": ""}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        report_markdown, summary = await AIDiagnosisService(
            _settings(),
            http_client=client,
        ).generate_report(snapshot=_snapshot())

    assert "## First fix to try" in report_markdown
    assert summary["source"] == "fallback"


@pytest.mark.asyncio
async def test_ai_service_uses_fallback_when_chat_request_fails() -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"error": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        report_markdown, summary = await AIDiagnosisService(
            _settings(),
            http_client=client,
        ).generate_report(snapshot=_snapshot())

    assert "## First fix to try" in report_markdown
    assert summary["source"] == "fallback"
