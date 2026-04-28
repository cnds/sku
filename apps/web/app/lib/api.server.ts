import type {
  DiagnosisResult,
  LeaderboardEntry,
  LeaderboardType,
  ProductAnalysisResult,
  ProductSnapshot,
  TimeWindow,
} from "@/lib/contracts";
import { snapshotFromAnalysis } from "@/lib/diagnosis";

const API_BASE_URL = process.env.SERVER_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
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
  shopId: string;
  window: TimeWindow;
}): Promise<LeaderboardEntry[]> {
  return fetchJson<LeaderboardEntry[]>(
    apiPath("/api/leaderboard", { ...shopParams(args.shopId, args.window), board: args.board }),
  );
}

export async function fetchProductAnalysis(args: {
  productId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<ProductAnalysisResult> {
  return fetchJson<ProductAnalysisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/analysis`, shopParams(args.shopId, args.window)),
  );
}

export async function fetchOrCreateDiagnosis(args: {
  analysis: ProductAnalysisResult;
  productId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  const path = apiPath(
    `/api/products/${encodeURIComponent(args.productId)}/diagnosis`,
    shopParams(args.shopId, args.window),
  );

  try {
    return await fetchJson<DiagnosisResult>(path);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) {
      throw error;
    }

    return fetchJson<DiagnosisResult>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshotFromAnalysis(args.analysis)),
    });
  }
}

export async function fetchDiagnosis(args: {
  productId: string;
  shopId: string;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  return fetchJson<DiagnosisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/diagnosis`, shopParams(args.shopId, args.window)),
  );
}

export async function createDiagnosis(args: {
  productId: string;
  shopId: string;
  snapshot: ProductSnapshot;
  window: TimeWindow;
}): Promise<DiagnosisResult> {
  return fetchJson<DiagnosisResult>(
    apiPath(`/api/products/${encodeURIComponent(args.productId)}/diagnosis`, shopParams(args.shopId, args.window)),
    {
      body: JSON.stringify(args.snapshot),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  );
}

export function parseTimeWindow(value: string | null): TimeWindow {
  if (value === "24h" || value === "30d") {
    return value;
  }
  return "7d";
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new ApiError(await response.text(), response.status);
  }
  return (await response.json()) as T;
}
