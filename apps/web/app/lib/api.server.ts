import type {
  DiagnosisResult,
  LeaderboardEntry,
  LeaderboardType,
  ProductAnalysisResult,
  ProductSnapshot,
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
  productId: string;
  requestId: string;
  shopId: string;
  snapshot: ProductSnapshot;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  return fetchJson<DiagnosisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/diagnosis`, shopParams(args.shopId, args.window)),
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
