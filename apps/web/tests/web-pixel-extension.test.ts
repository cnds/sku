import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const source = readFileSync(
  new URL("../../../extensions/web-pixel/src/index.js", import.meta.url),
  "utf8",
);
const toml = readFileSync(
  new URL("../../../extensions/web-pixel/shopify.extension.toml", import.meta.url),
  "utf8",
);

describe("web pixel extension", () => {
  it("subscribes to Shopify standard events and posts to the pixel ingest endpoint", () => {
    expect(source).toContain('"product_viewed"');
    expect(source).toContain('"product_added_to_cart"');
    expect(source).toContain('"checkout_completed"');
    expect(source).toContain('"checkout_shipping_info_submitted"');
    expect(source).toContain("X-SKU-Lens-Public-Token");
    expect(source).toContain("session_id");
  });

  it("declares endpoint, token, and shop settings with Web Pixel permissions", () => {
    expect(toml).toContain('type = "web_pixel_extension"');
    expect(toml).toContain("runtime_context = \"strict\"");
    expect(toml).toContain("[settings.fields.endpoint]");
    expect(toml).toContain("[settings.fields.publicToken]");
    expect(toml).toContain("[settings.fields.shopDomain]");
    expect(toml).toContain("analytics = true");
    expect(toml).toContain('sale_of_data = "disabled"');
  });
});
