import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppProvider } from "@shopify/polaris";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBottomSpacer } from "../app/components/PageBottomSpacer";

const {
  fetchBillingStatusMock,
  fetchPrioritiesMock,
  fetchProductAnalysisMock,
  fetchOrCreateDiagnosisMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchBillingStatusMock: vi.fn(),
  fetchOrCreateDiagnosisMock: vi.fn(),
  fetchPrioritiesMock: vi.fn(),
  fetchProductAnalysisMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchBillingStatus: fetchBillingStatusMock,
  fetchPriorities: fetchPrioritiesMock,
  fetchOrCreateDiagnosis: fetchOrCreateDiagnosisMock,
  fetchProductAnalysis: fetchProductAnalysisMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { messages } from "../app/lib/messages";
import { ErrorBoundary, loader } from "../app/routes/products.$productId";

describe("product analysis route loader", () => {
  beforeEach(() => {
    fetchBillingStatusMock.mockReset();
    fetchPrioritiesMock.mockReset();
    fetchProductAnalysisMock.mockReset();
    fetchOrCreateDiagnosisMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("7d");
    fetchBillingStatusMock.mockResolvedValue(billingStatusFixture());
    fetchPrioritiesMock.mockResolvedValue([]);
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
        "https://example.test/products/product-1?"
        + "shop=test-shop.myshopify.com&window=7d&host=admin.shopify.com%2Fstore%2Ftest",
      ),
    } as never);

    expect(fetchProductAnalysisMock).toHaveBeenCalledWith({
      productId: "product-1",
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
      window: "7d",
    });
    expect(fetchBillingStatusMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
    });
    expect(fetchPrioritiesMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
      window: "7d",
    });
    expect(fetchOrCreateDiagnosisMock).not.toHaveBeenCalled();
    expect(payload).toMatchObject({
      analysis: {
        benchmark_product_id: "benchmark-1",
        product_id: "product-1",
      },
      billing: {
        current_plan: "growth",
        is_entitled: true,
      },
      diagnosisPath:
        "/resources/products/product-1/diagnosis?"
        + "shop=test-shop.myshopify.com&window=7d&host=admin.shopify.com%2Fstore%2Ftest",
      host: "admin.shopify.com/store/test",
      productId: "product-1",
      priorityCard: null,
      shopId: "test-shop.myshopify.com",
      window: "7d",
    });
  });

  it("includes the matching priority card for the product detail page", async () => {
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
    fetchPrioritiesMock.mockResolvedValue([
      {
        add_to_carts: 2,
        board: "leaker",
        board_date: "2026-05-27",
        card_rank: 1,
        clicks: 5,
        evidence: ["50 PDP views", "2 add-to-carts"],
        first_fix: "Move the trust cue beside the buy box.",
        flag_reason: "Orders lag similar traffic",
        impressions: 20,
        orders: 1,
        primary_step: "pdp_add_to_cart",
        product_id: "product-1",
        score: 3,
        signal_state: "Ready",
        suspected_friction: "Shoppers need more confidence before checkout.",
        trend_reason: "Gap worsened versus the previous window.",
        trend_state: "Worsening",
        views: 50,
        window_end_date: "2026-05-27",
        window_start_date: "2026-05-20",
      },
    ]);

    const payload = await loader({
      params: { productId: "product-1" },
      request: new Request("https://example.test/products/product-1?shop=test-shop.myshopify.com&window=7d"),
    } as never);

    expect(payload).toMatchObject({
      priorityCard: {
        board: "leaker",
        first_fix: "Move the trust cue beside the buy box.",
        primary_step: "pdp_add_to_cart",
        product_id: "product-1",
      },
    });
  });

  it("does not load product analysis when billing is not entitled", async () => {
    fetchBillingStatusMock.mockResolvedValue({
      ...billingStatusFixture(),
      current_plan: null,
      is_entitled: false,
      subscription_status: "unsubscribed",
    });

    const payload = await loader({
      params: { productId: "product-1" },
      request: new Request("https://example.test/products/product-1?shop=test-shop.myshopify.com&window=7d"),
    } as never);

    expect(fetchProductAnalysisMock).not.toHaveBeenCalled();
    expect(fetchPrioritiesMock).not.toHaveBeenCalled();
    expect(payload).toMatchObject({
      analysis: null,
      diagnosisPath: null,
      productId: "product-1",
    });
  });

  it("renders the route error fallback without Remix route hooks", () => {
    const markup = renderToStaticMarkup(
      createElement(AppProvider, { i18n: polarisTranslations }, createElement(ErrorBoundary)),
    );

    expect(markup).toContain(messages.product.errorMessage);
  });

  it("uses the shared bottom spacer so product detail content does not touch the viewport edge", () => {
    const markup = renderToStaticMarkup(createElement(PageBottomSpacer));

    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain("height:3rem");
  });
});

function billingStatusFixture() {
  return {
    ai_refresh: {
      limit: 150,
      period_key: "2026-07",
      remaining: 144,
      used: 6,
    },
    billing_interval: "monthly",
    current_period_ends_at: "2026-08-02T00:00:00Z",
    current_plan: "growth",
    installed: true,
    is_entitled: true,
    pdp_views: {
      limit: 100000,
      over_limit: false,
      used: 2400,
    },
    pending_effective_at: null,
    pending_plan: null,
    plans: [],
    shop_id: "test-shop.myshopify.com",
    subscription_status: "active",
    trial_ends_at: null,
  };
}
