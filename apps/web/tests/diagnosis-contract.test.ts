import { describe, expect, it } from "vitest";

import {
  createFailedDiagnosis,
  createPendingDiagnosis,
  diagnosisFreshnessText,
  diagnosisRerunPath,
  parseDiagnosisSections,
  snapshotFromAnalysis,
} from "../app/lib/diagnosis";

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

  it("keeps generated_at in synthetic pending and failed diagnosis states", () => {
    expect(createPendingDiagnosis().generated_at).toBeNull();
    expect(createFailedDiagnosis("No report.").generated_at).toBeNull();
  });

  it("formats diagnosis freshness by status", () => {
    expect(
      diagnosisFreshnessText({
        generated_at: "2026-04-29T12:00:00Z",
        report_markdown: "Ready",
        snapshot_hash: "hash-1",
        status: "ready",
        summary_json: {},
      }),
    ).toBe("Generated Apr 29, 2026, 12:00 PM");
    expect(
      diagnosisFreshnessText({
        generated_at: null,
        report_markdown: null,
        snapshot_hash: "hash-2",
        status: "pending",
        summary_json: {},
      }),
    ).toBe("Generating new diagnosis");
    expect(
      diagnosisFreshnessText({
        generated_at: null,
        report_markdown: null,
        snapshot_hash: "hash-3",
        status: "failed",
        summary_json: {},
      }),
    ).toBe("Last diagnosis failed");
  });

  it("builds a forced diagnosis rerun resource path", () => {
    expect(
      diagnosisRerunPath("/resources/products/product-1/diagnosis?shop=shop-1&window=7d"),
    ).toBe("/resources/products/product-1/diagnosis?shop=shop-1&window=7d&force=true");
  });
});
