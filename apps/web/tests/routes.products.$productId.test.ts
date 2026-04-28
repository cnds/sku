import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  fetchProductAnalysisMock,
  fetchOrCreateDiagnosisMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchOrCreateDiagnosisMock: vi.fn(),
  fetchProductAnalysisMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchOrCreateDiagnosis: fetchOrCreateDiagnosisMock,
  fetchProductAnalysis: fetchProductAnalysisMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { loader } from "../app/routes/products.$productId";

describe("product analysis route loader", () => {
  beforeEach(() => {
    fetchProductAnalysisMock.mockReset();
    fetchOrCreateDiagnosisMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("7d");
  });

  it("does not block the page on diagnosis generation", async () => {
    fetchProductAnalysisMock.mockResolvedValue({
      benchmark_product_id: "benchmark-1",
      component_comparisons: [],
      funnel: {
        benchmark: { add_to_carts: 8, orders: 4, views: 100 },
        target: { add_to_carts: 2, orders: 1, views: 50 },
      },
      gap: 4,
      product_id: "product-1",
    });
    fetchOrCreateDiagnosisMock.mockResolvedValue({
      report_markdown: "should not be fetched in the route loader",
      snapshot_hash: "hash-1",
      status: "ready",
      summary_json: {},
    });

    const payload = await loader({
      params: { productId: "product-1" },
      request: new Request(
        "https://example.test/products/product-1?shop=test-shop.myshopify.com&window=7d",
      ),
    } as never);

    expect(fetchProductAnalysisMock).toHaveBeenCalledWith({
      productId: "product-1",
      shopId: "test-shop.myshopify.com",
      window: "7d",
    });
    expect(fetchOrCreateDiagnosisMock).not.toHaveBeenCalled();
    expect(payload).toMatchObject({
      analysis: {
        benchmark_product_id: "benchmark-1",
        product_id: "product-1",
      },
      diagnosisPath:
        "/resources/products/product-1/diagnosis?shop=test-shop.myshopify.com&window=7d",
      productId: "product-1",
      shopId: "test-shop.myshopify.com",
      window: "7d",
    });
  });
});
