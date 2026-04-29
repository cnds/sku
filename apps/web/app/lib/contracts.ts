export type TimeWindow = "24h" | "7d" | "30d";
export type LeaderboardType = "black" | "red";
export type DiagnosisStatus = "pending" | "ready" | "failed";

export interface LeaderboardEntry {
  product_id: string;
  views: number;
  add_to_carts: number;
  orders: number;
  score: number;
}

export interface FunnelSnapshot {
  views: number;
  add_to_carts: number;
  orders: number;
  impressions: number;
  clicks: number;
}

export interface ComponentComparison {
  component_id: string;
  target_clicks: number;
  benchmark_clicks: number;
  target_ctr: number;
  benchmark_ctr: number;
  delta: number;
}

export interface ProductAnalysisResult {
  product_id: string;
  benchmark_product_id: string;
  gap: number;
  funnel: {
    target: FunnelSnapshot;
    benchmark: FunnelSnapshot;
  };
  component_comparisons: ComponentComparison[];
}

export interface ProductSnapshot {
  views: number;
  add_to_carts: number;
  orders: number;
  component_clicks_distribution: Record<string, number>;
}

export interface DiagnosisResult {
  status: DiagnosisStatus;
  snapshot_hash: string;
  report_markdown: string | null;
  summary_json: Record<string, string>;
}

