import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppProvider } from "@shopify/polaris";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import { describe, expect, it } from "vitest";

import { AnalysisPanel, buildShopperJourney } from "../app/components/AnalysisPanel";
import type { PriorityCard, ProductAnalysisResult } from "../app/lib/contracts";

describe("product shopper journey", () => {
  it("highlights the primary drop-off step with supporting evidence", () => {
    const journey = buildShopperJourney(productAnalysisFixture());

    expect(journey.primaryDropOff.stepId).toBe("pdp_add_to_cart");
    expect(journey.primaryDropOff.evidence).toContain("8.0% PDP view to add-to-cart");
    expect(journey.steps.map((step) => step.label)).toEqual([
      "Exposure",
      "Click",
      "PDP view",
      "Engagement",
      "Add to cart",
      "Order",
    ]);
  });

  it("renders the matched priority card as the product detail conclusion", () => {
    const markup = renderToStaticMarkup(
      createElement(
        AppProvider,
        { i18n: polarisTranslations },
        createElement(AnalysisPanel, {
          analysis: productAnalysisFixture(),
          diagnosisPath: "/resources/products/product-1/diagnosis?shop=demo.myshopify.com&window=24h",
          priorityCard: priorityCardFixture(),
        }),
      ),
    );

    expect(markup).toContain("Priority detail");
    expect(markup).toContain("Move the trust cue beside the buy box.");
    expect(markup).toContain("50 PDP views");
    expect(markup).toContain("2 add-to-carts");
    expect(markup).toContain("Drop-off: PDP view to add-to-cart");
    expect(markup).toContain("Gap worsened versus the previous window.");
  });
});

function productAnalysisFixture(): ProductAnalysisResult {
  return {
    benchmark_product_id: "benchmark-1",
    component_comparisons: [
      {
        benchmark_clicks: 10,
        benchmark_ctr: 0.08,
        component_id: "size_chart",
        delta: 0.07,
        target_clicks: 1,
        target_ctr: 0.01,
      },
    ],
    funnel: {
      benchmark: {
        add_to_carts: 24,
        avg_scroll_pct: 72,
        clicks: 60,
        component_clicks_distribution: { size_chart: 10 },
        component_impressions_distribution: { size_chart: 80 },
        engage_count: 24,
        impressions: 260,
        media_interactions: 18,
        orders: 16,
        total_dwell_ms: 300000,
        variant_changes: 12,
        views: 120,
      },
      target: {
        add_to_carts: 8,
        avg_scroll_pct: 55,
        clicks: 44,
        component_clicks_distribution: { size_chart: 1 },
        component_impressions_distribution: { size_chart: 70 },
        engage_count: 16,
        impressions: 220,
        media_interactions: 4,
        orders: 1,
        total_dwell_ms: 140000,
        variant_changes: 5,
        views: 100,
      },
    },
    gap: 5,
    product_id: "product-1",
  };
}

function priorityCardFixture(): PriorityCard {
  return {
    add_to_carts: 2,
    board: "leaker",
    board_date: "2026-05-27",
    card_rank: 1,
    clicks: 5,
    evidence: ["50 PDP views", "2 add-to-carts"],
    first_fix: "Move the trust cue beside the buy box.",
    flag_reason: "Orders lag similar traffic",
    impressions: 20,
    orders: 1,
    primary_step: "pdp_add_to_cart",
    product_id: "product-1",
    score: 3,
    signal_state: "Ready",
    suspected_friction: "Shoppers need more confidence before checkout.",
    trend_reason: "Gap worsened versus the previous window.",
    trend_state: "Worsening",
    views: 50,
    window_end_date: "2026-05-27",
    window_start_date: "2026-05-20",
  };
}
