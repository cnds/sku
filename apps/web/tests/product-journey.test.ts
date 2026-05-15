import { describe, expect, it } from "vitest";

import { buildShopperJourney } from "../app/components/AnalysisPanel";

describe("product shopper journey", () => {
  it("highlights the primary drop-off step with supporting evidence", () => {
    const journey = buildShopperJourney({
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
    });

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
});
