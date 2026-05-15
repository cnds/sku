import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("storefront tracker event surface", () => {
  const source = readFileSync(
    new URL("../../extension/assets/sku-lens-tracker.js", import.meta.url),
    "utf8",
  );

  it("emits PDP view, buy-box intent, add-to-cart, and component PDP events", () => {
    expect(source).toContain('track("view"');
    expect(source).toContain('track("add_to_cart"');
    expect(source).toContain('track("component_click"');
    expect(source).toContain('componentId: "buy_box"');
    expect(source).toContain('componentId: "product_media"');
  });

  it("maps common PDP sections into stable component labels with debug hints", () => {
    expect(source).toContain('"product_description"');
    expect(source).toContain('"shipping_returns"');
    expect(source).toContain('"recommendations"');
    expect(source).toContain('"product_details"');
    expect(source).toContain("section_hint");
    expect(source).toContain("class_hint");
  });
});
