import { describe, expect, it } from "vitest";

import { messages } from "../app/lib/messages";
import { boardLabelForGap } from "../app/routes/products.$productId";

describe("board copy", () => {
  it("uses Winners and Leakers as the merchant-facing board labels", () => {
    expect(messages.dashboard.redboardTitle).toBe("Winners");
    expect(messages.dashboard.blackboardTitle).toBe("Leakers");
    expect(messages.dashboard.bannerText(2, "24 Hours")).toContain("Winners");
    expect(messages.dashboard.bannerText(2, "24 Hours")).toContain("Leakers");
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
});
