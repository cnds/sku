import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useLoaderDataMock = vi.fn();

vi.mock("@remix-run/react", async () => {
  const actual = await vi.importActual<typeof import("@remix-run/react")>("@remix-run/react");

  return {
    ...actual,
    Links: () => null,
    Meta: () => null,
    Outlet: () => null,
    Scripts: () => null,
    ScrollRestoration: () => null,
    useLoaderData: () => useLoaderDataMock(),
    useNavigation: () => ({ state: "idle" }),
  };
});

vi.mock("@shopify/polaris/build/esm/styles.css?url", () => ({
  default: "/polaris.css",
}));

import App, { links, loader } from "../app/root";

describe("root app shell", () => {
  beforeEach(() => {
    process.env.SHOPIFY_API_KEY = "test-api-key";
    useLoaderDataMock.mockReturnValue({ shopifyApiKey: "test-api-key" });
  });

  it("publishes the shopify api key and app bridge script", async () => {
    const payload = await loader({ request: new Request("https://example.test") } as never);
    const markup = renderToStaticMarkup(<App />);

    expect(payload).toEqual({ shopifyApiKey: "test-api-key" });
    expect(markup).toContain('name="shopify-api-key"');
    expect(markup).toContain('content="test-api-key"');
    expect(markup).toContain("https://cdn.shopify.com/shopifycloud/app-bridge.js");
  });

  it("keeps the polaris stylesheet registered", () => {
    expect(links()).toEqual([{ href: "/polaris.css", rel: "stylesheet" }]);
  });
});
