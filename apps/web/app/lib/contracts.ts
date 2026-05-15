export type TimeWindow = "24h" | "7d" | "30d";
export type LeaderboardType = "black" | "red";
export type PriorityBoardType = "leaker" | "hidden_winner";
export type PrioritySignalState = "Ready" | "Weak signal" | "Insufficient data" | "Tracking issue";
export type DiagnosisStatus = "pending" | "ready" | "failed";

export interface LeaderboardEntry {
  product_id: string;
  views: number;
  add_to_carts: number;
  orders: number;
  impressions?: number;
  clicks?: number;
  score: number;
}

export interface FunnelSnapshot {
  views: number;
  add_to_carts: number;
  orders: number;
  impressions: number;
  clicks: number;
  media_interactions?: number;
  variant_changes?: number;
  total_dwell_ms?: number;
  engage_count?: number;
  avg_scroll_pct?: number;
  component_clicks_distribution?: Record<string, number>;
  component_impressions_distribution?: Record<string, number>;
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
  impressions?: number;
  clicks?: number;
  media_interactions?: number;
  variant_changes?: number;
  total_dwell_ms?: number;
  engage_count?: number;
  avg_scroll_pct?: number;
  component_impressions_distribution?: Record<string, number>;
}

export interface PriorityCard {
  product_id: string;
  board: PriorityBoardType;
  signal_state: PrioritySignalState;
  flag_reason: string;
  primary_step: string;
  evidence: string[];
  suspected_friction: string;
  first_fix: string;
  views: number;
  add_to_carts: number;
  orders: number;
  impressions: number;
  clicks: number;
  score: number;
}

export interface DiagnosisResult {
  status: DiagnosisStatus;
  snapshot_hash: string;
  report_markdown: string | null;
  summary_json: Record<string, string>;
}
