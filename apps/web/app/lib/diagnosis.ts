import type { DiagnosisResult, ProductAnalysisResult, ProductSnapshot } from "@/lib/contracts";

export function createFailedDiagnosis(message: string): DiagnosisResult {
  return {
    report_markdown: message,
    snapshot_hash: "",
    status: "failed",
    summary_json: { error: message },
  };
}

export function createPendingDiagnosis(): DiagnosisResult {
  return {
    report_markdown: null,
    snapshot_hash: "",
    status: "pending",
    summary_json: {},
  };
}

export function snapshotFromAnalysis(analysis: ProductAnalysisResult): ProductSnapshot {
  return {
    add_to_carts: analysis.funnel.target.add_to_carts,
    component_clicks_distribution: Object.fromEntries(
      analysis.component_comparisons.map((component) => [
        component.component_id,
        component.target_clicks,
      ]),
    ),
    orders: analysis.funnel.target.orders,
    views: analysis.funnel.target.views,
  };
}
