import { describe, expect, it } from "vitest";

import { dashboardPath, diagnosisResourcePath, productPath } from "../app/lib/url";

describe("embedded route URLs", () => {
  it("preserves the Shopify host parameter when building navigation paths", () => {
    const host = "admin.shopify.com/store/demo";

    expect(dashboardPath("demo.myshopify.com", "24h", host)).toBe(
      "/?shop=demo.myshopify.com&window=24h&host=admin.shopify.com%2Fstore%2Fdemo",
    );
    expect(productPath("product 1", "demo.myshopify.com", "24h", host)).toBe(
      "/products/product%201?shop=demo.myshopify.com&window=24h&host=admin.shopify.com%2Fstore%2Fdemo",
    );
    expect(diagnosisResourcePath("product 1", "demo.myshopify.com", "24h", host)).toBe(
      "/resources/products/product%201/diagnosis?"
      + "shop=demo.myshopify.com&window=24h&host=admin.shopify.com%2Fstore%2Fdemo",
    );
  });
});
