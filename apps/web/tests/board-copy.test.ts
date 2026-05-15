import { describe, expect, it } from "vitest";

import { formatLeaderboardActivity } from "../app/components/LeaderboardTable";
import { messages } from "../app/lib/messages";
import { priorityStepLabel } from "../app/routes/_index";
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
