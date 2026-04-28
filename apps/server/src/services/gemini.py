from __future__ import annotations

from typing import Any

import httpx

from config import Settings
from schemas import ProductSnapshot


class GeminiDiagnosisService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def generate_report(self, *, snapshot: ProductSnapshot) -> tuple[str, dict[str, str]]:
        if not self._settings.gemini_api_key or self._settings.gemini_api_key == "replace-me":
            return self._fallback_report(snapshot=snapshot)

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": self._build_prompt(snapshot=snapshot),
                        }
                    ]
                }
            ]
        }

        client = self._http_client or httpx.AsyncClient(timeout=20.0)
        should_close = self._http_client is None
        try:
            response = await client.post(
                (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self._settings.gemini_model}:generateContent"
                ),
                params={"key": self._settings.gemini_api_key},
                json=payload,
            )
            response.raise_for_status()
            report_markdown = self._extract_text(response.json())
            if not report_markdown:
                return self._fallback_report(snapshot=snapshot)

            primary_issue = (
                report_markdown.splitlines()[0].lstrip("# ").strip() or "Gemini diagnosis"
            )
            return report_markdown, {
                "primary_issue": primary_issue,
                "recommended_action": (
                    "Review the markdown report and prioritize the first action item."
                ),
                "source": "gemini",
            }
        except httpx.HTTPError:
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
                "You are diagnosing a Shopify product detail page.",
                "Use the following aggregated metrics to produce a concise markdown report with:",
                "1. Anomaly identification",
                "2. Likely buyer hesitation",
                "3. Concrete page fixes",
                "",
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
        candidates = payload.get("candidates", [])
        if not candidates:
            return ""

        parts = candidates[0].get("content", {}).get("parts", [])
        return "\n".join(part.get("text", "").strip() for part in parts if part.get("text")).strip()

    @staticmethod
    def _fallback_report(*, snapshot: ProductSnapshot) -> tuple[str, dict[str, str]]:
        conversion_rate = 0.0 if snapshot.views == 0 else snapshot.orders / snapshot.views
        size_chart_clicks = snapshot.component_clicks_distribution.get("size_chart", 0)

        primary_issue = "Traffic is healthy but conversion is under index."
        recommended_action = "Lift trust and fit clarity above the fold."

        if snapshot.views < 50:
            primary_issue = "Traffic is too thin to confirm demand with confidence."
            recommended_action = "Invest in traffic acquisition before large page redesigns."
        elif size_chart_clicks == 0:
            primary_issue = "Fit intent is present, but the size-chart interaction is missing."
            recommended_action = "Expose size guidance earlier and repeat it near the CTA."
        elif conversion_rate >= 0.08:
            primary_issue = "The product converts well once viewed."
            recommended_action = "Scale traffic and protect merchandising consistency."

        report_markdown = "\n".join(
            [
                "# SKU Lens",
                "",
                "AI Winner & Loser Analysis",
                "",
                "Use AI to audit product pages by tracking component-level engagement and "
                "quantifying Order Gaps.",
                "",
                f"- Views: {snapshot.views}",
                f"- Add to carts: {snapshot.add_to_carts}",
                f"- Orders: {snapshot.orders}",
                f"- Conversion rate: {conversion_rate:.2%}",
                "",
                "## Diagnosis",
                primary_issue,
                "",
                "## Recommendation",
                recommended_action,
            ]
        )
        return report_markdown, {
            "primary_issue": primary_issue,
            "recommended_action": recommended_action,
            "source": "fallback",
        }
