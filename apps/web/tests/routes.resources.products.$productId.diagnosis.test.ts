import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  createDiagnosisMock,
  fetchDiagnosisMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  createDiagnosisMock: vi.fn(),
  fetchDiagnosisMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  createDiagnosis: createDiagnosisMock,
  fetchDiagnosis: fetchDiagnosisMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { action, loader } from "../app/routes/resources.products.$productId.diagnosis";

describe("diagnosis resource route", () => {
  beforeEach(() => {
    createDiagnosisMock.mockReset();
    fetchDiagnosisMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("7d");
  });

  it("proxies diagnosis reads without requiring analysis data", async () => {
    fetchDiagnosisMock.mockResolvedValue({
      report_markdown: null,
      snapshot_hash: "snapshot-1",
      status: "pending",
      summary_json: {},
    });

    const response = await loader({
      params: { productId: "product-1" },
      request: new Request(
        "https://example.test/resources/products/product-1/diagnosis?shop=test-shop.myshopify.com&window=7d",
      ),
    } as never);

    expect(fetchDiagnosisMock).toHaveBeenCalledWith({
      productId: "product-1",
      shopId: "test-shop.myshopify.com",
      window: "7d",
    });
    expect(await response.json()).toEqual({
      report_markdown: null,
      snapshot_hash: "snapshot-1",
      status: "pending",
      summary_json: {},
    });
  });

  it("creates a diagnosis when the browser posts a snapshot", async () => {
    createDiagnosisMock.mockResolvedValue({
      report_markdown: null,
      snapshot_hash: "snapshot-2",
      status: "pending",
      summary_json: {},
    });

    const response = await action({
      params: { productId: "product-1" },
      request: new Request(
        "https://example.test/resources/products/product-1/diagnosis?shop=test-shop.myshopify.com&window=7d",
        {
          body: JSON.stringify({
            add_to_carts: 2,
            component_clicks_distribution: { review_tab: 1 },
            orders: 1,
            views: 50,
          }),
          headers: { "Content-Type": "application/json" },
          method: "POST",
        },
      ),
    } as never);

    expect(createDiagnosisMock).toHaveBeenCalledWith({
      productId: "product-1",
      shopId: "test-shop.myshopify.com",
      snapshot: {
        add_to_carts: 2,
        component_clicks_distribution: { review_tab: 1 },
        orders: 1,
        views: 50,
      },
      window: "7d",
    });
    expect(await response.json()).toEqual({
      report_markdown: null,
      snapshot_hash: "snapshot-2",
      status: "pending",
      summary_json: {},
    });
  });
});
