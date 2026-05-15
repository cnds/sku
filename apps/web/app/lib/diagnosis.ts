import type { DiagnosisResult, ProductAnalysisResult, ProductSnapshot } from "@/lib/contracts";
import { messages } from "@/lib/messages";

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
  const target = analysis.funnel.target;
  return {
    add_to_carts: target.add_to_carts,
    avg_scroll_pct: target.avg_scroll_pct ?? 0,
    clicks: target.clicks ?? 0,
    component_clicks_distribution: target.component_clicks_distribution ?? Object.fromEntries(
      analysis.component_comparisons.map((component) => [
        component.component_id,
        component.target_clicks,
      ]),
    ),
    component_impressions_distribution: target.component_impressions_distribution ?? {},
    engage_count: target.engage_count ?? 0,
    impressions: target.impressions ?? 0,
    media_interactions: target.media_interactions ?? 0,
    orders: target.orders,
    total_dwell_ms: target.total_dwell_ms ?? 0,
    variant_changes: target.variant_changes ?? 0,
    views: target.views,
  };
}

export interface ParsedDiagnosisSections {
  observed: string;
  evidence: string;
  suspectedFriction: string;
  firstFix: string;
}

export function parseDiagnosisSections(markdown: string | null): ParsedDiagnosisSections {
  if (!markdown) {
    return {
      evidence: "",
      firstFix: "",
      observed: messages.analysis.diagnosisNoReport,
      suspectedFriction: "",
    };
  }

  const parsed = new Map<string, string>();
  const matches = [...markdown.matchAll(/^##\s+(.+?)\s*\n([\s\S]*?)(?=^##\s+|\s*$)/gm)];
  for (const match of matches) {
    const heading = normalizeHeading(match[1] ?? "");
    parsed.set(heading, (match[2] ?? "").trim());
  }

  if (parsed.size > 0) {
    return {
      evidence: parsed.get("evidence") ?? "",
      firstFix: parsed.get("first fix to try") ?? "",
      observed: parsed.get("observed") ?? "",
      suspectedFriction: parsed.get("suspected friction") ?? "",
    };
  }

  const paragraphs = markdown.split(/\n\n+/).filter((p) => p.trim());
  return {
    evidence: paragraphs[1]?.trim() ?? "",
    firstFix: paragraphs.slice(3).join("\n\n").trim(),
    observed: paragraphs[0]?.trim() ?? markdown.trim(),
    suspectedFriction: paragraphs[2]?.trim() ?? "",
  };
}

function normalizeHeading(value: string): string {
  return value.trim().toLowerCase();
}
