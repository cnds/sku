from __future__ import annotations

from typing import Any

import httpx

from config import Settings
from schemas import ProductSnapshot


class AIDiagnosisService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def generate_report(self, *, snapshot: ProductSnapshot) -> tuple[str, dict[str, str]]:
        if not self._settings.ai_api_key or self._settings.ai_api_key == "replace-me":
            return self._fallback_report(snapshot=snapshot)

        payload = {
            "model": self._settings.ai_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are diagnosing a Shopify product detail page.",
                },
                {
                    "role": "user",
                    "content": self._build_prompt(snapshot=snapshot),
                },
            ],
        }

        client = self._http_client or httpx.AsyncClient(timeout=20.0)
        should_close = self._http_client is None
        try:
            response = await client.post(
                f"{self._settings.ai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.ai_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            report_markdown = self._extract_text(response.json())
            if not report_markdown:
                return self._fallback_report(snapshot=snapshot)

            primary_issue = report_markdown.splitlines()[0].lstrip("# ").strip() or "AI diagnosis"
            return report_markdown, {
                "primary_issue": primary_issue,
                "recommended_action": "Review the markdown report and prioritize the first action item.",
                "source": "openai-compatible",
            }
        except (httpx.HTTPError, ValueError):
            return self._fallback_report(snapshot=snapshot)
        finally:
            if should_close:
                await client.aclose()

    @staticmethod
    def _build_prompt(*, snapshot: ProductSnapshot) -> str:
        avg_dwell_s = (
            round(snapshot.total_dwell_ms / snapshot.engage_count / 1000, 1)
            if snapshot.engage_count > 0
            else 0
        )
        return "\n".join(
            [
                "Use the following aggregated metrics to produce a concise markdown report.",
                "",
                "Structure the report with EXACTLY these four sections using ## headings:",
                "## Observed",
                "(State the visible shopper-journey pattern without over-claiming)",
                "## Evidence",
                "(List the specific metrics that support the observation)",
                "## Suspected friction",
                "(Explain the likely buying hesitation or discovery constraint)",
                "## First fix to try",
                "(Give one concrete page or merchandising change to test first)",
                "",
                "Metrics:",
                f"Impressions (collection pages): {snapshot.impressions}",
                f"Clicks (collection to PDP): {snapshot.clicks}",
                f"Page views (all sources): {snapshot.views}",
                f"Add to carts: {snapshot.add_to_carts}",
                f"Orders: {snapshot.orders}",
                f"Media interactions: {snapshot.media_interactions}",
                f"Variant changes: {snapshot.variant_changes}",
                f"Avg dwell time: {avg_dwell_s}s",
                f"Avg scroll depth: {snapshot.avg_scroll_pct}%",
                f"Component click distribution: {snapshot.component_clicks_distribution}",
                f"Component impression distribution: {snapshot.component_impressions_distribution}",
            ]
        )

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return ""

        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            return ""

        content = message.get("content", "")
        return content.strip() if isinstance(content, str) else ""

    @staticmethod
    def _fallback_report(*, snapshot: ProductSnapshot) -> tuple[str, dict[str, str]]:
        conversion_rate = 0.0 if snapshot.views == 0 else snapshot.orders / snapshot.views
        size_chart_clicks = snapshot.component_clicks_distribution.get("size_chart", 0)

        observed = "Traffic is healthy but conversion is under index."
        friction = "Buyers may lack confidence due to insufficient product detail or social proof."
        first_fix = "Lift trust and fit clarity above the fold."

        if snapshot.views < 50:
            observed = "Traffic is too thin to confirm demand with confidence."
            friction = "The product has low visibility in collections and search results."
            first_fix = "Invest in a small traffic test before large page redesigns."
        elif size_chart_clicks == 0:
            observed = "Fit intent is present, but the size-chart interaction is missing."
            friction = "Size guidance is not prominent enough to attract clicks."
            first_fix = "Expose size guidance earlier and repeat it near the CTA."
        elif conversion_rate >= 0.08:
            observed = "The product converts well once viewed."
            friction = "Strong product-market fit is visible, but limited traffic caps total revenue."
            first_fix = "Scale traffic and protect merchandising consistency."

        report_markdown = "\n".join(
            [
                "## Observed",
                observed,
                "",
                "## Evidence",
                f"- Views: {snapshot.views}",
                f"- Add to carts: {snapshot.add_to_carts}",
                f"- Orders: {snapshot.orders}",
                f"- Conversion rate: {conversion_rate:.2%}",
                "",
                "## Suspected friction",
                friction,
                "",
                "## First fix to try",
                first_fix,
            ]
        )
        return report_markdown, {
            "primary_issue": observed,
            "recommended_action": first_fix,
            "source": "fallback",
        }
