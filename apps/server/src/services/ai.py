from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from config import Settings
from schemas import ProductSnapshot


@dataclass(slots=True)
class PriorityAdvice:
    suspected_friction: str
    first_fix: str
    source: str


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
                    "content": (
                        "You are a cautious Shopify merchandising analyst. "
                        "Use only the supplied shopper-event evidence; do not invent page content, pricing, "
                        "reviews, competitors, promotions, or campaign facts."
                    ),
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
        except httpx.HTTPError, ValueError:
            return self._fallback_report(snapshot=snapshot)
        finally:
            if should_close:
                await client.aclose()

    async def generate_priority_advice(
        self,
        *,
        fallback_first_fix: str,
        fallback_suspected_friction: str,
        snapshot: ProductSnapshot,
    ) -> PriorityAdvice:
        report_markdown, summary = await self.generate_report(snapshot=snapshot)
        if summary.get("source") != "openai-compatible":
            return PriorityAdvice(
                suspected_friction=fallback_suspected_friction,
                first_fix=fallback_first_fix,
                source=summary.get("source", "fallback"),
            )

        sections = self._extract_sections(report_markdown)
        suspected_friction = sections.get("suspected friction", "").strip() or fallback_suspected_friction
        first_fix = sections.get("first fix to try", "").strip() or fallback_first_fix
        return PriorityAdvice(
            suspected_friction=suspected_friction,
            first_fix=first_fix,
            source="openai-compatible",
        )

    @staticmethod
    def _build_prompt(*, snapshot: ProductSnapshot) -> str:
        avg_dwell_s = (
            round(snapshot.total_dwell_ms / snapshot.engage_count / 1000, 1) if snapshot.engage_count > 0 else 0
        )
        collection_ctr = AIDiagnosisService._percent(snapshot.clicks, snapshot.impressions)
        view_to_cart = AIDiagnosisService._percent(snapshot.add_to_carts, snapshot.views)
        cart_to_order = AIDiagnosisService._percent(snapshot.orders, snapshot.add_to_carts)
        component_signal = AIDiagnosisService._component_signal(snapshot=snapshot)
        return "\n".join(
            [
                "Use the following aggregated Shopify shopper-event metrics to produce a concise markdown report.",
                "The goal is a SKU-specific optimization suggestion, not a generic ecommerce checklist.",
                "",
                "Structure the report with EXACTLY these four sections using ## headings:",
                "## Observed",
                "(Name the primary shopper-journey pattern and funnel step without over-claiming)",
                "## Evidence",
                "(List 3-5 specific metrics, rates, or component signals that support the observation)",
                "## Suspected friction",
                (
                    "(Explain the likely buying hesitation or discovery constraint, and state uncertainty when "
                    "evidence is thin)"
                ),
                "## First fix to try",
                "(Give one concrete page or merchandising change to test first, plus the metric to watch next)",
                "",
                "Recommendation rules:",
                (
                    "- Anchor the diagnosis to one observed step: listing impression to PDP click, PDP view to "
                    "add-to-cart, add-to-cart to order, or PDP component engagement."
                ),
                (
                    "- Prefer component-specific advice when component impression/click data points to a concrete "
                    "component."
                ),
                "- If traffic or engagement volume is thin, recommend validation or more traffic before page redesign.",
                (
                    "- Avoid generic advice like improve images, rewrite copy, add reviews, lower price, or offer "
                    "discounts unless the supplied metrics directly support that type of issue."
                ),
                "- Do not claim causality; phrase recommendations as the next experiment to test.",
                "",
                "Metrics:",
                f"Impressions (collection pages): {snapshot.impressions}",
                f"Clicks (collection to PDP): {snapshot.clicks}",
                f"Collection/listing CTR: {collection_ctr}",
                f"Page views (all sources): {snapshot.views}",
                f"Add to carts: {snapshot.add_to_carts}",
                f"PDP view to add-to-cart rate: {view_to_cart}",
                f"Orders: {snapshot.orders}",
                f"Add-to-cart to order rate: {cart_to_order}",
                f"Media interactions: {snapshot.media_interactions}",
                f"Variant changes: {snapshot.variant_changes}",
                f"Avg dwell time: {avg_dwell_s}s",
                f"Avg scroll depth: {snapshot.avg_scroll_pct}%",
                f"Strongest component signal: {component_signal}",
                f"Component click distribution: {snapshot.component_clicks_distribution}",
                f"Component impression distribution: {snapshot.component_impressions_distribution}",
            ]
        )

    @staticmethod
    def _percent(numerator: int, denominator: int) -> str:
        if denominator <= 0:
            return "n/a"
        return f"{numerator / denominator:.1%}"

    @staticmethod
    def _component_signal(*, snapshot: ProductSnapshot) -> str:
        candidates: list[tuple[float, str, int, int]] = []
        for component_id, impressions in snapshot.component_impressions_distribution.items():
            if impressions <= 0:
                continue
            clicks = snapshot.component_clicks_distribution.get(component_id, 0)
            candidates.append((clicks / impressions, component_id, clicks, impressions))

        if not candidates:
            if snapshot.component_clicks_distribution:
                return "component clicks are present, but component impressions are not available"
            return "n/a"

        ctr, component_id, clicks, impressions = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        return f"{component_id}: {clicks} clicks from {impressions} impressions ({ctr:.1%} CTR)"

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
    def _extract_sections(markdown: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        for match in re.finditer(r"^##\s+(.+?)\s*\n([\s\S]*?)(?=^##\s+|\s*$)", markdown, re.MULTILINE):
            sections[match.group(1).strip().lower()] = match.group(2).strip()
        return sections

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
