import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchDiagnosis, fetchProductAnalysis } from "../app/lib/api.server";

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
});
