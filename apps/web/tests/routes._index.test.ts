import { beforeEach, describe, expect, it, vi } from "vitest";

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

import { loader, readinessBannerContent } from "../app/routes/_index";

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
