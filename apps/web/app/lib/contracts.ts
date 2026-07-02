export type TimeWindow = "24h" | "7d" | "30d";
export type LeaderboardType = "black" | "red";
export type PriorityBoardType = "leaker" | "hidden_winner";
export type PrioritySignalState = "Ready" | "Weak signal" | "Insufficient data" | "Tracking issue";
export type PriorityTrendState = "New" | "Worsening" | "Improving" | "Stable";
export type DiagnosisStatus = "pending" | "ready" | "failed";
export type IntegrationHealthStatus = "healthy" | "partial" | "not_connected";
export type IntegrationCheckStatus = "ok" | "missing";
export type OnboardingChecklistStatus = "done" | "action" | "pending";
export type RecommendationFeedbackAction = "will_try" | "not_useful" | "already_fixed" | "remind_later";
export type BillingPlan = "starter" | "growth" | "pro";
export type BillingInterval = "monthly" | "annual";
export type BillingStatus = "unsubscribed" | "trialing" | "active" | "frozen" | "cancelled" | "expired";

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
  board_date: string;
  window_start_date: string;
  window_end_date: string;
  card_rank: number;
  signal_state: PrioritySignalState;
  trend_state: PriorityTrendState;
  trend_reason: string;
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
  generated_at: string | null;
}

export interface IntegrationHealthCoverage {
  impressions: number;
  clicks: number;
  views: number;
  component_clicks: number;
  add_to_carts: number;
  orders: number;
}

export interface IntegrationHealthCheck {
  key: string;
  label: string;
  status: IntegrationCheckStatus;
  message: string;
}

export interface IntegrationHealthResponse {
  status: IntegrationHealthStatus;
  last_event_at: string | null;
  coverage: IntegrationHealthCoverage;
  checks: IntegrationHealthCheck[];
}

export interface OnboardingChecklistItem {
  key: string;
  label: string;
  status: OnboardingChecklistStatus;
  message: string;
}

export interface OnboardingStatusResponse {
  shop_id: string;
  installed: boolean;
  public_token: string | null;
  ingest_endpoint: string;
  app_embed_deep_link: string;
  integration_health: IntegrationHealthResponse;
  last_raw_event_at: string | null;
  checklist: OnboardingChecklistItem[];
}

export interface RecommendationFeedbackResponse {
  accepted: boolean;
  latest_action: RecommendationFeedbackAction;
  product_id: string;
  shop_id: string;
  window: TimeWindow;
}

export interface BillingPlanConfigResponse {
  plan: BillingPlan;
  name: string;
  monthly_price: number;
  annual_price_monthly_equivalent: number;
  ai_refresh_limit: number;
  pdp_view_soft_limit: number;
  history_days: number;
  recommended: boolean;
}

export interface BillingQuotaResponse {
  used: number;
  limit: number;
  remaining: number;
  period_key: string;
}

export interface PdpViewsQuotaResponse {
  used: number;
  limit: number;
  over_limit: boolean;
}

export interface BillingStatusResponse {
  shop_id: string;
  installed: boolean;
  is_entitled: boolean;
  subscription_status: BillingStatus;
  current_plan: BillingPlan | null;
  pending_plan: BillingPlan | null;
  billing_interval: BillingInterval | null;
  trial_ends_at: string | null;
  current_period_ends_at: string | null;
  pending_effective_at: string | null;
  ai_refresh: BillingQuotaResponse;
  pdp_views: PdpViewsQuotaResponse;
  plans: BillingPlanConfigResponse[];
}

export interface BillingSubscribeResponse {
  confirmation_url: string;
  plan: BillingPlan;
  billing_interval: BillingInterval;
  replacement_behavior: string;
}

export interface InternalCardReviewItem {
  priority_card: PriorityCard;
  raw_event_counts: Record<string, number>;
  aggregate_evidence: Record<string, unknown>;
  derived_signal: Record<string, unknown>;
  ai_summary: Record<string, unknown>;
  merchant_copy: Record<string, unknown>;
}

export interface InternalCardReviewResponse {
  shop_id: string;
  window: TimeWindow;
  cards: InternalCardReviewItem[];
}
