import { describe, expect, it } from "vitest";

import { parseDiagnosisSections, snapshotFromAnalysis } from "../app/lib/diagnosis";

describe("diagnosis contract", () => {
  it("posts every backend-supported snapshot field from product analysis", () => {
    const snapshot = snapshotFromAnalysis({
      benchmark_product_id: "benchmark-1",
      component_comparisons: [
        {
          benchmark_clicks: 8,
          benchmark_ctr: 0.08,
          component_id: "size_chart",
          delta: 0.07,
          target_clicks: 1,
          target_ctr: 0.01,
        },
      ],
      funnel: {
        benchmark: {
          add_to_carts: 20,
          avg_scroll_pct: 70,
          clicks: 56,
          component_clicks_distribution: { size_chart: 8 },
          component_impressions_distribution: { size_chart: 88 },
          engage_count: 22,
          impressions: 240,
          media_interactions: 14,
          orders: 12,
          total_dwell_ms: 260000,
          variant_changes: 9,
          views: 120,
        },
        target: {
          add_to_carts: 8,
          avg_scroll_pct: 54,
          clicks: 44,
          component_clicks_distribution: { size_chart: 1 },
          component_impressions_distribution: { size_chart: 70 },
          engage_count: 16,
          impressions: 220,
          media_interactions: 3,
          orders: 1,
          total_dwell_ms: 140000,
          variant_changes: 5,
          views: 100,
        },
      },
      gap: 4,
      product_id: "product-1",
    });

    expect(snapshot).toEqual({
      add_to_carts: 8,
      avg_scroll_pct: 54,
      clicks: 44,
      component_clicks_distribution: { size_chart: 1 },
      component_impressions_distribution: { size_chart: 70 },
      engage_count: 16,
      impressions: 220,
      media_interactions: 3,
      orders: 1,
      total_dwell_ms: 140000,
      variant_changes: 5,
      views: 100,
    });
  });

  it("parses the four diagnosis sections used by backend reports", () => {
    expect(
      parseDiagnosisSections(
        "## Observed\nOrders trail traffic.\n\n"
          + "## Evidence\n100 views, 1 order.\n\n"
          + "## Suspected friction\nSize confidence is weak.\n\n"
          + "## First fix to try\nMove the size chart beside the variant selector.",
      ),
    ).toEqual({
      evidence: "100 views, 1 order.",
      firstFix: "Move the size chart beside the variant selector.",
      observed: "Orders trail traffic.",
      suspectedFriction: "Size confidence is weak.",
    });
  });
});
