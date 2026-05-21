import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  fetchOnboardingStatusMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchOnboardingStatusMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchOnboardingStatus: fetchOnboardingStatusMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { loader } from "../app/routes/onboarding";

describe("onboarding route loader", () => {
  beforeEach(() => {
    fetchOnboardingStatusMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("24h");
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
    expect(payload).toMatchObject({
      shopId: "demo.myshopify.com",
      status: {
        installed: true,
        public_token: "public-1",
      },
      window: "24h",
    });
  });
});
