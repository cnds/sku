import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  changeBillingPlanMock,
  fetchBillingStatusMock,
  fetchOnboardingStatusMock,
  parseTimeWindowMock,
  subscribeToPlanMock,
} = vi.hoisted(() => ({
  changeBillingPlanMock: vi.fn(),
  fetchBillingStatusMock: vi.fn(),
  fetchOnboardingStatusMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
  subscribeToPlanMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  cancelBillingPlan: vi.fn(),
  changeBillingPlan: changeBillingPlanMock,
  fetchBillingStatus: fetchBillingStatusMock,
  fetchOnboardingStatus: fetchOnboardingStatusMock,
  parseTimeWindow: parseTimeWindowMock,
  subscribeToPlan: subscribeToPlanMock,
}));

import { action, loader } from "../app/routes/onboarding";

describe("onboarding route loader", () => {
  beforeEach(() => {
    changeBillingPlanMock.mockReset();
    fetchBillingStatusMock.mockReset();
    fetchOnboardingStatusMock.mockReset();
    parseTimeWindowMock.mockReset();
    subscribeToPlanMock.mockReset();
    parseTimeWindowMock.mockReturnValue("24h");
    fetchBillingStatusMock.mockResolvedValue(billingStatusFixture());
    fetchOnboardingStatusMock.mockResolvedValue({
      app_embed_deep_link: "https://demo.myshopify.com/admin/themes/current/editor?context=apps",
      checklist: [],
      ingest_endpoint: "https://api.example.test/ingest/events",
      installed: true,
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
        status: "partial",
      },
      last_raw_event_at: null,
      public_token: "public-1",
      shop_id: "demo.myshopify.com",
    });
  });

  it("loads onboarding status for the requested shop and window", async () => {
    const payload = await loader({
      request: new Request(
        "https://example.test/onboarding?shop=demo.myshopify.com&window=24h",
      ),
    } as never);

    expect(fetchOnboardingStatusMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "demo.myshopify.com",
      window: "24h",
    });
    expect(fetchBillingStatusMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "demo.myshopify.com",
    });
    expect(payload).toMatchObject({
      billing: {
        is_entitled: false,
        subscription_status: "unsubscribed",
      },
      shopId: "demo.myshopify.com",
      status: {
        installed: true,
        public_token: "public-1",
      },
      window: "24h",
    });
  });

  it("submits selected plans through the Shopify billing subscribe flow", async () => {
    subscribeToPlanMock.mockResolvedValue({
      billing_interval: "monthly",
      confirmation_url: "https://demo.myshopify.com/admin/charges/confirm",
      plan: "growth",
      replacement_behavior: "STANDARD",
    });

    const body = new URLSearchParams({
      billing_interval: "monthly",
      intent: "subscribe",
      plan: "growth",
      shop_id: "demo.myshopify.com",
    });
    const response = await action({
      request: new Request("https://example.test/onboarding?shop=demo.myshopify.com&window=24h", {
        body,
        method: "POST",
      }),
    } as never);

    expect(subscribeToPlanMock).toHaveBeenCalledWith({
      billingInterval: "monthly",
      plan: "growth",
      requestId: expect.any(String),
      shopId: "demo.myshopify.com",
    });
    expect(changeBillingPlanMock).not.toHaveBeenCalled();
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://demo.myshopify.com/admin/charges/confirm");
  });
});

function billingStatusFixture() {
  return {
    ai_refresh: {
      limit: 0,
      period_key: "2026-07",
      remaining: 0,
      used: 0,
    },
    billing_interval: null,
    current_period_ends_at: null,
    current_plan: null,
    installed: true,
    is_entitled: false,
    pdp_views: {
      limit: 0,
      over_limit: false,
      used: 0,
    },
    pending_effective_at: null,
    pending_plan: null,
    plans: [
      {
        ai_refresh_limit: 50,
        annual_price_monthly_equivalent: 15,
        history_days: 30,
        monthly_price: 19,
        name: "SKU Lens Starter",
        pdp_view_soft_limit: 25000,
        plan: "starter",
        recommended: false,
      },
      {
        ai_refresh_limit: 150,
        annual_price_monthly_equivalent: 29,
        history_days: 90,
        monthly_price: 39,
        name: "SKU Lens Growth",
        pdp_view_soft_limit: 100000,
        plan: "growth",
        recommended: true,
      },
      {
        ai_refresh_limit: 500,
        annual_price_monthly_equivalent: 59,
        history_days: 365,
        monthly_price: 79,
        name: "SKU Lens Pro",
        pdp_view_soft_limit: 500000,
        plan: "pro",
        recommended: false,
      },
    ],
    shop_id: "demo.myshopify.com",
    subscription_status: "unsubscribed",
    trial_ends_at: null,
  };
}
