import type {
  BillingInterval,
  BillingPlan,
  BillingStatusResponse,
  BillingSubscribeResponse,
  DiagnosisResult,
  InternalCardReviewResponse,
  IntegrationHealthResponse,
  LeaderboardEntry,
  LeaderboardType,
  OnboardingStatusResponse,
  PriorityCard,
  ProductAnalysisResult,
  ProductSnapshot,
  RecommendationFeedbackAction,
  RecommendationFeedbackResponse,
  TimeWindow,
} from "@/lib/contracts";
import { snapshotFromAnalysis } from "@/lib/diagnosis";
import { REQUEST_ID_HEADER, logServerEvent } from "@/lib/logging";

const API_BASE_URL = process.env.SERVER_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId: string,
  ) {
    super(message);
  }
}

function apiPath(path: string, params: Record<string, string>): string {
  const qs = new URLSearchParams(params).toString();
  return `${path}?${qs}`;
}

function shopParams(shopId: string, window: TimeWindow): Record<string, string> {
  return { shop_id: shopId, window };
}

export async function fetchLeaderboard(args: {
  board: LeaderboardType;
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<LeaderboardEntry[]> {
  return fetchJson<LeaderboardEntry[]>(
    apiPath("/api/leaderboard", { ...shopParams(args.shopId, args.window), board: args.board }),
    {
      requestId: args.requestId,
      route: "leaderboard",
    },
  );
}

export async function fetchPriorities(args: {
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<PriorityCard[]> {
  return fetchJson<PriorityCard[]>(
    apiPath("/api/priorities", shopParams(args.shopId, args.window)),
    {
      requestId: args.requestId,
      route: "priorities",
    },
  );
}

export async function fetchIntegrationHealth(args: {
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<IntegrationHealthResponse> {
  return fetchJson<IntegrationHealthResponse>(
    apiPath("/api/integration/health", shopParams(args.shopId, args.window)),
    {
      requestId: args.requestId,
      route: "integration_health",
    },
  );
}

export async function fetchOnboardingStatus(args: {
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<OnboardingStatusResponse> {
  return fetchJson<OnboardingStatusResponse>(
    apiPath("/api/onboarding/status", shopParams(args.shopId, args.window)),
    {
      requestId: args.requestId,
      route: "onboarding_status",
    },
  );
}

export async function fetchBillingStatus(args: {
  requestId: string;
  shopId: string;
}): Promise<BillingStatusResponse> {
  return fetchJson<BillingStatusResponse>(
    apiPath("/api/billing/status", { shop_id: args.shopId }),
    {
      requestId: args.requestId,
      route: "billing_status",
    },
  );
}

export async function subscribeToPlan(args: {
  billingInterval: BillingInterval;
  plan: BillingPlan;
  requestId: string;
  shopId: string;
}): Promise<BillingSubscribeResponse> {
  return fetchJson<BillingSubscribeResponse>(
    "/api/billing/subscribe",
    {
      requestId: args.requestId,
      route: "billing_subscribe",
    },
    {
      body: JSON.stringify({
        billing_interval: args.billingInterval,
        plan: args.plan,
        shop_id: args.shopId,
      }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  );
}

export async function changeBillingPlan(args: {
  billingInterval: BillingInterval;
  plan: BillingPlan;
  requestId: string;
  shopId: string;
}): Promise<BillingSubscribeResponse> {
  return fetchJson<BillingSubscribeResponse>(
    "/api/billing/change-plan",
    {
      requestId: args.requestId,
      route: "billing_change_plan",
    },
    {
      body: JSON.stringify({
        billing_interval: args.billingInterval,
        plan: args.plan,
        shop_id: args.shopId,
      }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  );
}

export async function cancelBillingPlan(args: {
  requestId: string;
  shopId: string;
}): Promise<BillingStatusResponse> {
  return fetchJson<BillingStatusResponse>(
    "/api/billing/cancel",
    {
      requestId: args.requestId,
      route: "billing_cancel",
    },
    {
      body: JSON.stringify({
        shop_id: args.shopId,
      }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  );
}

export async function postRecommendationFeedback(args: {
  action: RecommendationFeedbackAction;
  board?: string | null;
  boardDate?: string | null;
  cardRank?: number | null;
  context?: Record<string, unknown> | null;
  productId: string;
  requestId: string;
  shopId: string;
  window: TimeWindow;
  windowEndDate?: string | null;
  windowStartDate?: string | null;
}): Promise<RecommendationFeedbackResponse> {
  const body: Record<string, unknown> = {
    action: args.action,
    product_id: args.productId,
    shop_id: args.shopId,
    window: args.window,
  };
  if (args.board) {
    body.board = args.board;
  }
  if (args.boardDate) {
    body.board_date = args.boardDate;
  }
  if (args.windowStartDate) {
    body.window_start_date = args.windowStartDate;
  }
  if (args.windowEndDate) {
    body.window_end_date = args.windowEndDate;
  }
  if (typeof args.cardRank === "number") {
    body.card_rank = args.cardRank;
  }
  if (args.context && Object.keys(args.context).length > 0) {
    body.context = args.context;
  }
  return fetchJson<RecommendationFeedbackResponse>(
    "/api/recommendation-feedback",
    {
      requestId: args.requestId,
      route: "recommendation_feedback",
    },
    {
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  );
}

export async function fetchInternalCardReview(args: {
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<InternalCardReviewResponse> {
  return fetchJson<InternalCardReviewResponse>(
    apiPath("/api/internal/card-review", shopParams(args.shopId, args.window)),
    {
      requestId: args.requestId,
      route: "internal_card_review",
    },
  );
}

export async function fetchProductAnalysis(args: {
  productId: string;
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<ProductAnalysisResult> {
  return fetchJson<ProductAnalysisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/analysis`, shopParams(args.shopId, args.window)),
    {
      requestId: args.requestId,
      route: "product_analysis",
    },
  );
}

export async function fetchOrCreateDiagnosis(args: {
  analysis: ProductAnalysisResult;
  productId: string;
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  const path = apiPath(
    `/api/products/${encodeURIComponent(args.productId)}/diagnosis`,
    shopParams(args.shopId, args.window),
  );

  try {
    return await fetchJson<DiagnosisResult>(path, {
      requestId: args.requestId,
      route: "diagnosis.fetch",
      silentStatuses: [404],
    });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) {
      throw error;
    }

    return fetchJson<DiagnosisResult>(
      path,
      {
        requestId: args.requestId,
        route: "diagnosis.create",
      },
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(snapshotFromAnalysis(args.analysis)),
      },
    );
  }
}

export async function fetchDiagnosis(args: {
  productId: string;
  requestId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  return fetchJson<DiagnosisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/diagnosis`, shopParams(args.shopId, args.window)),
    {
      requestId: args.requestId,
      route: "diagnosis.fetch",
      silentStatuses: [404],
    },
  );
}

export async function createDiagnosis(args: {
  force?: boolean;
  productId: string;
  requestId: string;
  shopId: string;
  snapshot: ProductSnapshot;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  const params = args.force
    ? { ...shopParams(args.shopId, args.window), force: "true" }
    : shopParams(args.shopId, args.window);
  return fetchJson<DiagnosisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/diagnosis`, params),
    {
      requestId: args.requestId,
      route: "diagnosis.create",
    },
    {
      body: JSON.stringify(args.snapshot),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  );
}

export function parseTimeWindow(value: string | null): TimeWindow {
  if (value === "7d" || value === "30d") {
    return value;
  }
  return "24h";
}

async function fetchJson<T>(
  path: string,
  meta: {
    requestId: string;
    route: string;
    silentStatuses?: number[];
  },
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set(REQUEST_ID_HEADER, meta.requestId);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
    });
  } catch (error) {
    logServerEvent("error", "backend.request_failed", {
      error: error instanceof Error ? error.message : String(error),
      path,
      request_id: meta.requestId,
      route: meta.route,
    });
    throw error;
  }

  if (!response.ok) {
    const body = await response.text();
    const responseRequestId = response.headers.get(REQUEST_ID_HEADER) ?? meta.requestId;

    if (!meta.silentStatuses?.includes(response.status)) {
      logServerEvent("error", "backend.request_failed", {
        path,
        request_id: meta.requestId,
        response_request_id: responseRequestId,
        route: meta.route,
        status: response.status,
      });
    }

    throw new ApiError(body, response.status, responseRequestId);
  }
  return (await response.json()) as T;
}
