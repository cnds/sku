import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppProvider } from "@shopify/polaris";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PriorityCard } from "../app/lib/contracts";

const {
  fetchBillingStatusMock,
  fetchIntegrationHealthMock,
  fetchLeaderboardMock,
  fetchPrioritiesMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchBillingStatusMock: vi.fn(),
  fetchIntegrationHealthMock: vi.fn(),
  fetchLeaderboardMock: vi.fn(),
  fetchPrioritiesMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchBillingStatus: fetchBillingStatusMock,
  fetchIntegrationHealth: fetchIntegrationHealthMock,
  fetchLeaderboard: fetchLeaderboardMock,
  fetchPriorities: fetchPrioritiesMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { messages } from "../app/lib/messages";
import { PageBottomSpacer } from "../app/components/PageBottomSpacer";
import {
  ErrorBoundary,
  PriorityRecommendation,
  PriorityWhyNow,
  TimeWindowSelector,
  loader,
  readinessBannerContent,
} from "../app/routes/_index";

describe("dashboard route loader", () => {
  beforeEach(() => {
    fetchBillingStatusMock.mockReset();
    fetchIntegrationHealthMock.mockReset();
    fetchLeaderboardMock.mockReset();
    fetchPrioritiesMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("24h");
    fetchBillingStatusMock.mockResolvedValue(billingStatusFixture());
    fetchIntegrationHealthMock.mockResolvedValue({
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
    });
    fetchLeaderboardMock.mockResolvedValue([]);
    fetchPrioritiesMock.mockResolvedValue([]);
  });

  it("loads today's priority cards from the backend priority API", async () => {
    const payload = await loader({
      request: new Request(
        "https://example.test/?shop=test-shop.myshopify.com&window=24h&host=admin.shopify.com%2Fstore%2Ftest",
      ),
    } as never);

    expect(fetchPrioritiesMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
      window: "24h",
    });
    expect(fetchBillingStatusMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
    });
    expect(fetchIntegrationHealthMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
      window: "24h",
    });
    expect(fetchLeaderboardMock).toHaveBeenCalledTimes(2);
    expect(payload).toMatchObject({
      health: {
        status: "not_connected",
      },
      host: "admin.shopify.com/store/test",
      priorities: [],
      shopId: "test-shop.myshopify.com",
      window: "24h",
    });
  });

  it("defaults local board requests to the configured test shop", async () => {
    await loader({
      request: new Request("https://example.test/?window=24h"),
    } as never);

    expect(fetchBillingStatusMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "sku-dev-uaop8pff.myshopify.com",
    });
    expect(fetchPrioritiesMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "sku-dev-uaop8pff.myshopify.com",
      window: "24h",
    });
  });

  it("does not fetch board data when the shop is not subscribed", async () => {
    fetchBillingStatusMock.mockResolvedValue({
      ...billingStatusFixture(),
      current_plan: null,
      is_entitled: false,
      subscription_status: "unsubscribed",
    });

    const payload = await loader({
      request: new Request("https://example.test/?shop=test-shop.myshopify.com&window=24h"),
    } as never);

    expect(fetchIntegrationHealthMock).not.toHaveBeenCalled();
    expect(fetchPrioritiesMock).not.toHaveBeenCalled();
    expect(fetchLeaderboardMock).not.toHaveBeenCalled();
    expect(payload).toMatchObject({
      blackboard: [],
      health: null,
      priorities: [],
      redboard: [],
    });
  });

  it("renders the route error fallback without Remix route hooks", () => {
    const markup = renderToStaticMarkup(
      createElement(AppProvider, { i18n: polarisTranslations }, createElement(ErrorBoundary)),
    );

    expect(markup).toContain(messages.dashboard.errorMessage);
  });

  it("always renders all time window links for an empty selected window", () => {
    const markup = renderToStaticMarkup(
      createElement(TimeWindowSelector, {
        host: "admin.shopify.com/store/test",
        selectedWindow: "7d",
        shopId: "test-shop.myshopify.com",
      }),
    );

    expect(markup).toContain("24 Hours");
    expect(markup).toContain("7 Days");
    expect(markup).toContain("30 Days");
    expect(markup).toContain("window=24h");
    expect(markup).toContain("window=7d");
    expect(markup).toContain("window=30d");
    expect(markup).toContain('aria-current="page"');
    expect(markup).toContain('data-selected="true"');
    expect(markup).toContain("timeWindowOptionActive");
  });

  it("renders markdown emphasis in dashboard priority card copy", () => {
    const card = priorityCardFixture();
    const markup = renderToStaticMarkup(
      createElement(
        AppProvider,
        { i18n: polarisTranslations },
        createElement("div", null, [
          createElement(PriorityRecommendation, { card, key: "recommendation" }),
          createElement(PriorityWhyNow, { card, key: "why-now" }),
        ]),
      ),
    );

    expect(markup).toContain("<strong>trust cue</strong>");
    expect(markup).toContain("<strong>more confidence</strong>");
    expect(markup).toContain("<strong>50 PDP views</strong>");
    expect(markup).toContain("<strong>2 add-to-carts</strong>");
    expect(markup).not.toContain("**");
  });

  it("renders a bottom spacer so the dashboard content does not touch the viewport edge", () => {
    const markup = renderToStaticMarkup(createElement(PageBottomSpacer));

    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain("height:3rem");
  });

  it("separates missing install, missing raw events, low PDP traffic, and partial coverage states", () => {
    expect(
      readinessBannerContent({
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
      }).message,
    ).toContain("No installation record");

    expect(
      readinessBannerContent({
        checks: [{ key: "installation", label: "Installation", message: "ok", status: "ok" }],
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
      }).message,
    ).toContain("No raw storefront events");

    expect(
      readinessBannerContent({
        checks: [],
        coverage: {
          add_to_carts: 0,
          clicks: 0,
          component_clicks: 0,
          impressions: 0,
          orders: 0,
          views: 4,
        },
        last_event_at: "2026-05-21T01:00:00Z",
        status: "partial",
      }).message,
    ).toContain("Only 4 PDP views");

    expect(
      readinessBannerContent({
        checks: [],
        coverage: {
          add_to_carts: 0,
          clicks: 0,
          component_clicks: 0,
          impressions: 8,
          orders: 0,
          views: 24,
        },
        last_event_at: "2026-05-21T01:00:00Z",
        status: "partial",
      }).message,
    ).toContain("Partial coverage");
  });
});

function priorityCardFixture(): PriorityCard {
  return {
    add_to_carts: 2,
    board: "leaker",
    board_date: "2026-05-27",
    card_rank: 1,
    clicks: 5,
    evidence: ["**50 PDP views**", "**2 add-to-carts**"],
    first_fix: "Move the **trust cue** beside the buy box.",
    flag_reason: "Orders lag similar traffic",
    impressions: 20,
    orders: 1,
    primary_step: "pdp_add_to_cart",
    product_id: "product-1",
    score: 3,
    signal_state: "Ready",
    suspected_friction: "Shoppers need **more confidence** before checkout.",
    trend_reason: "**Gap worsened** versus the previous window.",
    trend_state: "Worsening",
    views: 50,
    window_end_date: "2026-05-27",
    window_start_date: "2026-05-20",
  };
}

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
    ],
    shop_id: "test-shop.myshopify.com",
    subscription_status: "active",
    trial_ends_at: null,
  };
}
