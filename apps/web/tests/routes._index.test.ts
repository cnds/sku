import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppProvider } from "@shopify/polaris";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PriorityCard } from "../app/lib/contracts";

const {
  fetchIntegrationHealthMock,
  fetchLeaderboardMock,
  fetchPrioritiesMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchIntegrationHealthMock: vi.fn(),
  fetchLeaderboardMock: vi.fn(),
  fetchPrioritiesMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchIntegrationHealth: fetchIntegrationHealthMock,
  fetchLeaderboard: fetchLeaderboardMock,
  fetchPriorities: fetchPrioritiesMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { messages } from "../app/lib/messages";
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
    fetchLeaderboardMock.mockReset();
    fetchPrioritiesMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("24h");
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

    expect(fetchPrioritiesMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "sku-dev-uaop8pff.myshopify.com",
      window: "24h",
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
