import { describe, expect, it } from "vitest";

import { formatLeaderboardActivity } from "../app/components/LeaderboardTable";
import { messages } from "../app/lib/messages";
import {
  healthBannerContent,
  priorityActionLabel,
  prioritySignalTone,
  priorityStepLabel,
  priorityTrendTone,
} from "../app/routes/_index";
import { boardLabelForGap } from "../app/routes/products.$productId";

describe("board copy", () => {
  it("uses Winners and Leakers as the merchant-facing board labels", () => {
    expect(messages.dashboard.redboardTitle).toBe("Winners");
    expect(messages.dashboard.blackboardTitle).toBe("Leakers");
    expect(messages.dashboard.redboardSubtitle).toBe("High intent, underexposed");
    expect(messages.dashboard.blackboardSubtitle).toBe("High attention, weak progression");
    expect(messages.dashboard.bannerText(2, "24 Hours")).toContain("Winners");
    expect(messages.dashboard.bannerText(2, "24 Hours")).toContain("Leakers");
  });

  it("frames SKU Lens as a daily decision board instead of a scoring dashboard", () => {
    expect(messages.dashboard.subtitle).toBe("Daily decision board for product priorities");
    expect(messages.dashboard.errorMessage).toBe("Failed to load the board. The analytics server may be unavailable.");
    expect(messages.dashboard.prioritiesKicker).toBe("Decision queue");
    expect(messages.dashboard.prioritiesActionCount(3)).toBe("3 actions");
    expect(messages.dashboard.priorityRecommendedMove).toBe("Recommended move");
    expect(messages.product.subtitle("benchmark-1")).toBe("Shopper journey and diagnosis · benchmark: benchmark-1");
    expect("scoringHeading" in messages.analysis).toBe(false);
  });

  it("maps product analysis badges to Winners and Leakers", () => {
    expect(boardLabelForGap(-1)).toEqual({
      label: "Winners",
      tone: "success",
    });
    expect(boardLabelForGap(1)).toEqual({
      label: "Leakers",
      tone: "critical",
    });
  });

  it("labels priority card drop-off and opportunity steps", () => {
    expect(priorityStepLabel("pdp_add_to_cart")).toBe("Drop-off: PDP view to add-to-cart");
    expect(priorityStepLabel("cart_to_order")).toBe("Drop-off: add-to-cart to order");
    expect(priorityStepLabel("merchandising_reach")).toBe("Opportunity: merchandising reach");
  });

  it("labels priority card trend states", () => {
    expect(priorityTrendTone("Worsening")).toBe("critical");
    expect(priorityTrendTone("Improving")).toBe("success");
    expect(priorityTrendTone("New")).toBe("info");
    expect(priorityTrendTone("Stable")).toBeUndefined();
  });

  it("hides ready signal badges but keeps non-ready signal badges visible", () => {
    expect(prioritySignalTone("Ready")).toBeUndefined();
    expect(prioritySignalTone("Weak signal")).toBe("info");
    expect(prioritySignalTone("Insufficient data")).toBe("info");
    expect(prioritySignalTone("Tracking issue")).toBe("attention");
  });

  it("labels priority cards by the action merchants should take first", () => {
    expect(priorityActionLabel({ board: "leaker", card_rank: 1 })).toBe("Fix first");
    expect(priorityActionLabel({ board: "leaker", card_rank: 2 })).toBe("Fix next");
    expect(priorityActionLabel({ board: "hidden_winner", card_rank: 3 })).toBe("Scale carefully");
  });

  it("summarizes integration health for the board banner", () => {
    expect(
      healthBannerContent({
        checks: [],
        coverage: {
          add_to_carts: 12,
          clicks: 30,
          component_clicks: 18,
          impressions: 120,
          orders: 4,
          views: 80,
        },
        last_event_at: "2026-04-29T12:00:00Z",
        status: "healthy",
      }),
    ).toEqual({
      message: "Integration healthy: tracker, PDP, buy-box, and order coverage are present.",
      tone: "success",
    });

    expect(
      healthBannerContent({
        checks: [
          {
            key: "component_tracking",
            label: "Component tracking",
            message: "No PDP component interactions are present for this window.",
            status: "missing",
          },
          {
            key: "orders_webhook",
            label: "Orders / webhook",
            message: "No order or webhook events are present for this window.",
            status: "missing",
          },
        ],
        coverage: {
          add_to_carts: 0,
          clicks: 0,
          component_clicks: 0,
          impressions: 0,
          orders: 0,
          views: 20,
        },
        last_event_at: "2026-04-29T12:00:00Z",
        status: "partial",
      }),
    ).toEqual({
      message: "Integration partial: missing Component tracking and Orders / webhook.",
      tone: "warning",
    });
  });

  it("keeps secondary product lists focused on activity instead of exposed scores", () => {
    expect(messages.leaderboard.columnSignal).toBe("Recent signal");
    expect("columnScore" in messages.leaderboard).toBe(false);
    expect(formatLeaderboardActivity({
      add_to_carts: 8,
      orders: 1,
      product_id: "demo-size-confidence-leaker",
      score: 4.2,
      views: 120,
    })).toBe("120 views · 8 carts · 1 order");
  });
});
