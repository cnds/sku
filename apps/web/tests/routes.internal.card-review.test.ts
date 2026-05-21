import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  fetchInternalCardReviewMock,
  parseTimeWindowMock,
} = vi.hoisted(() => ({
  fetchInternalCardReviewMock: vi.fn(),
  parseTimeWindowMock: vi.fn(),
}));

vi.mock("../app/lib/api.server", () => ({
  fetchInternalCardReview: fetchInternalCardReviewMock,
  parseTimeWindow: parseTimeWindowMock,
}));

import { loader } from "../app/routes/internal.card-review";

describe("internal card review route loader", () => {
  beforeEach(() => {
    fetchInternalCardReviewMock.mockReset();
    parseTimeWindowMock.mockReset();
    parseTimeWindowMock.mockReturnValue("24h");
    fetchInternalCardReviewMock.mockResolvedValue({
      cards: [
        {
          aggregate_evidence: { views: 100 },
          ai_summary: { summary: "AI summary" },
          derived_signal: { signal_state: "Ready" },
          merchant_copy: { first_fix: "Move trust copy above the fold." },
          priority_card: { product_id: "product-1" },
          raw_event_counts: { view: 100 },
        },
      ],
      shop_id: "demo.myshopify.com",
      window: "24h",
    });
  });

  it("loads gated review data for the requested shop and window", async () => {
    const payload = await loader({
      request: new Request(
        "https://example.test/internal/card-review?shop=demo.myshopify.com&window=24h",
      ),
    } as never);

    expect(fetchInternalCardReviewMock).toHaveBeenCalledWith({
      requestId: expect.any(String),
      shopId: "demo.myshopify.com",
      window: "24h",
    });
    expect(payload.review.cards[0].merchant_copy.first_fix).toBe(
      "Move trust copy above the fold.",
    );
  });
});
