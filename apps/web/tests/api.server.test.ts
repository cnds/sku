import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createDiagnosis,
  fetchDiagnosis,
  fetchInternalCardReview,
  fetchIntegrationHealth,
  fetchOnboardingStatus,
  fetchPriorities,
  fetchProductAnalysis,
  postRecommendationFeedback,
} from "../app/lib/api.server";

describe("api.server logging", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.SERVER_API_URL = "http://localhost:8000";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("propagates request ids to backend requests", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          benchmark_product_id: "benchmark-1",
          component_comparisons: [],
          funnel: {
            benchmark: { add_to_carts: 8, orders: 4, views: 100 },
            target: { add_to_carts: 2, orders: 1, views: 50 },
          },
          gap: 4,
          product_id: "product-1",
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      ),
    ) as typeof fetch;

    await fetchProductAnalysis({
      productId: "product-1",
      requestId: "req-123",
      shopId: "shop-1",
      window: "7d",
    });

    const [, init] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(headers.get("X-SKU-Lens-Request-Id")).toBe("req-123");
  });

  it("logs unexpected backend failures with the standardized format", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = vi.fn().mockResolvedValue(
      new Response("upstream unavailable", {
        headers: { "X-SKU-Lens-Request-Id": "req-999" },
        status: 503,
      }),
    ) as typeof fetch;

    await expect(
      fetchProductAnalysis({
        productId: "product-1",
        requestId: "req-999",
        shopId: "shop-1",
        window: "7d",
      }),
    ).rejects.toEqual(
      expect.objectContaining<ApiError>({
        requestId: "req-999",
        status: 503,
      }),
    );

    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy.mock.calls[0]?.[0]).toContain("[web][api][backend.request_failed]");
    expect(errorSpy.mock.calls[0]?.[0]).toContain("request_id=req-999");
    expect(errorSpy.mock.calls[0]?.[0]).toContain("status=503");
    expect(errorSpy.mock.calls[0]?.[0]).toContain("route=product_analysis");
  });

  it("suppresses expected diagnosis 404 logs", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = vi.fn().mockResolvedValue(
      new Response("Diagnosis not found.", {
        headers: { "X-SKU-Lens-Request-Id": "req-404" },
        status: 404,
      }),
    ) as typeof fetch;

    await expect(
      fetchDiagnosis({
        productId: "product-1",
        requestId: "req-404",
        shopId: "shop-1",
        window: "7d",
      }),
    ).rejects.toEqual(
      expect.objectContaining<ApiError>({
        requestId: "req-404",
        status: 404,
      }),
    );

    expect(errorSpy).not.toHaveBeenCalled();
  });

  it("fetches today's priority cards from the backend priority endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    ) as typeof fetch;

    await fetchPriorities({
      requestId: "req-priority",
      shopId: "shop-1",
      window: "24h",
    });

    const [url, init] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(String(url)).toBe("http://localhost:8000/api/priorities?shop_id=shop-1&window=24h");
    expect(headers.get("X-SKU-Lens-Request-Id")).toBe("req-priority");
  });

  it("fetches integration health from the backend health endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          checks: [],
          coverage: {
            add_to_carts: 0,
            clicks: 0,
            component_clicks: 0,
            impressions: 0,
            orders: 0,
            views: 0,
          },
          last_event_at: null,
          status: "not_connected",
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      ),
    ) as typeof fetch;

    await fetchIntegrationHealth({
      requestId: "req-health",
      shopId: "shop-1",
      window: "24h",
    });

    const [url, init] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(String(url)).toBe("http://localhost:8000/api/integration/health?shop_id=shop-1&window=24h");
    expect(headers.get("X-SKU-Lens-Request-Id")).toBe("req-health");
  });

  it("fetches onboarding status from the backend onboarding endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          app_embed_deep_link: "https://demo.myshopify.com/admin/themes/current/editor?context=apps",
          checklist: [],
          ingest_endpoint: "https://api.example.test/ingest/events",
          installed: false,
          integration_health: {
            checks: [],
            coverage: {
              add_to_carts: 0,
              clicks: 0,
              component_clicks: 0,
              impressions: 0,
              orders: 0,
              views: 0,
            },
            last_event_at: null,
            status: "not_connected",
          },
          last_raw_event_at: null,
          public_token: null,
          shop_id: "demo.myshopify.com",
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      ),
    ) as typeof fetch;

    await fetchOnboardingStatus({
      requestId: "req-onboarding",
      shopId: "demo.myshopify.com",
      window: "24h",
    });

    const [url, init] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(String(url)).toBe(
      "http://localhost:8000/api/onboarding/status?shop_id=demo.myshopify.com&window=24h",
    );
    expect(headers.get("X-SKU-Lens-Request-Id")).toBe("req-onboarding");
  });

  it("posts lightweight recommendation feedback to the backend", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          accepted: true,
          latest_action: "will_try",
          product_id: "product-1",
          shop_id: "demo.myshopify.com",
          window: "24h",
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 201,
        },
      ),
    ) as typeof fetch;

    await postRecommendationFeedback({
      action: "will_try",
      board: "leaker",
      boardDate: "2026-05-27",
      cardRank: 1,
      context: {
        primary_step: "pdp_add_to_cart",
        surface: "today_priorities",
      },
      productId: "product-1",
      requestId: "req-feedback",
      shopId: "demo.myshopify.com",
      window: "24h",
      windowEndDate: "2026-05-27",
      windowStartDate: "2026-05-26",
    });

    const [url, init] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(String(url)).toBe("http://localhost:8000/api/recommendation-feedback");
    expect(init?.method).toBe("POST");
    expect(headers.get("X-SKU-Lens-Request-Id")).toBe("req-feedback");
    expect(JSON.parse(String(init?.body))).toEqual({
      action: "will_try",
      board: "leaker",
      board_date: "2026-05-27",
      card_rank: 1,
      context: {
        primary_step: "pdp_add_to_cart",
        surface: "today_priorities",
      },
      product_id: "product-1",
      shop_id: "demo.myshopify.com",
      window: "24h",
      window_end_date: "2026-05-27",
      window_start_date: "2026-05-26",
    });
  });

  it("fetches internal card review data from the gated review endpoint", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          cards: [],
          shop_id: "demo.myshopify.com",
          window: "24h",
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      ),
    ) as typeof fetch;

    await fetchInternalCardReview({
      requestId: "req-review",
      shopId: "demo.myshopify.com",
      window: "24h",
    });

    const [url, init] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(String(url)).toBe(
      "http://localhost:8000/api/internal/card-review?shop_id=demo.myshopify.com&window=24h",
    );
    expect(headers.get("X-SKU-Lens-Request-Id")).toBe("req-review");
  });

  it("passes force=true when manually rerunning diagnosis", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          generated_at: null,
          report_markdown: null,
          snapshot_hash: "snapshot-1",
          status: "pending",
          summary_json: {},
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 200,
        },
      ),
    ) as typeof fetch;

    await createDiagnosis({
      force: true,
      productId: "product-1",
      requestId: "req-diagnosis",
      shopId: "shop-1",
      snapshot: {
        add_to_carts: 2,
        component_clicks_distribution: {},
        orders: 1,
        views: 20,
      },
      window: "7d",
    });

    const [url] = vi.mocked(global.fetch).mock.calls[0] ?? [];

    expect(String(url)).toBe(
      "http://localhost:8000/api/products/product-1/diagnosis?shop_id=shop-1&window=7d&force=true",
    );
  });
});
