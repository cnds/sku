import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  fetchLeaderboardMock,
  fetchPrioritiesMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchLeaderboardMock: vi.fn(),
  fetchPrioritiesMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchLeaderboard: fetchLeaderboardMock,
  fetchPriorities: fetchPrioritiesMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { loader } from "../app/routes/_index";

describe("dashboard route loader", () => {
  beforeEach(() => {
    fetchLeaderboardMock.mockReset();
    fetchPrioritiesMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("24h");
    fetchLeaderboardMock.mockResolvedValue([]);
    fetchPrioritiesMock.mockResolvedValue([]);
  });

  it("loads today's priority cards from the backend priority API", async () => {
    const payload = await loader({
      request: new Request(
        "https://example.test/?shop=test-shop.myshopify.com&window=24h",
      ),
    } as never);

    expect(fetchPrioritiesMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "test-shop.myshopify.com",
      window: "24h",
    });
    expect(fetchLeaderboardMock).toHaveBeenCalledTimes(2);
    expect(payload).toMatchObject({
      priorities: [],
      shopId: "test-shop.myshopify.com",
      window: "24h",
    });
  });
});
