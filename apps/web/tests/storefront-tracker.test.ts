import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const source = readFileSync(
  new URL("../../extension/assets/sku-lens-tracker.js", import.meta.url),
  "utf8",
);

describe("storefront tracker event surface", () => {
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

  it.each([
    ["Dawn", "product__media", "product__description", "product-form__input"],
    ["Refresh", "product__media-wrapper", "product__accordion", "product-form__input"],
    ["Sense", "product-media", "product__details", "product-form__input"],
    ["Impulse", "product-single__media-wrapper", "product-single__description", "variant-wrapper"],
    ["Prestige", "Product__Slideshow", "ProductMeta__Description", "ProductForm__Variants"],
    ["Debutify", "product-single__media-group", "product-single__description", "selector-wrapper"],
  ])(
    "executes the tracker against %s PDP markup and emits stable component labels",
    async (_theme, mediaClass, descriptionClass, variantClass) => {
      const capturedBatches = await runTrackerFixture({
        descriptionClass,
        mediaClass,
        variantClass,
      });
      const events = capturedBatches.flatMap((batch) => batch.events);

      expect(events.map((event) => event.event_type)).toEqual(
        expect.arrayContaining(["view", "component_click", "add_to_cart", "media", "variant"]),
      );
      expect(componentIds(events)).toEqual(
        expect.arrayContaining(["buy_box", "product_media", "product_description"]),
      );
      expect(capturedBatches[0]).toMatchObject({
        shop_domain: "fixture.myshopify.com",
      });
    },
  );
});

interface TrackerFixtureArgs {
  descriptionClass: string;
  mediaClass: string;
  variantClass: string;
}

interface CapturedBatch {
  events: Array<{
    component_id: string | null;
    event_type: string;
  }>;
  shop_domain: string;
}

async function runTrackerFixture(args: TrackerFixtureArgs): Promise<CapturedBatch[]> {
  const capturedBatches: CapturedBatch[] = [];
  const globalNames = [
    "document",
    "fetch",
    "HTMLElement",
    "HTMLScriptElement",
    "localStorage",
    "window",
  ] as const;
  const previousGlobals = new Map(
    globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
  );

  class FixtureElement {
    attributes: Record<string, string>;
    children: FixtureElement[] = [];
    classList: { contains: (className: string) => boolean };
    className: string;
    id: string;
    parentElement: FixtureElement | null = null;
    tagName: string;
    textContent: string;
    value = "";

    constructor(tagName: string, options: {
      attributes?: Record<string, string>;
      className?: string;
      id?: string;
      textContent?: string;
      value?: string;
    } = {}) {
      this.attributes = options.attributes ?? {};
      this.className = options.className ?? "";
      this.classList = { contains: (className: string) => this.hasClass(className) };
      this.id = options.id ?? "";
      this.tagName = tagName.toUpperCase();
      this.textContent = options.textContent ?? "";
      this.value = options.value ?? "";
    }

    append(child: FixtureElement): void {
      child.parentElement = this;
      this.children.push(child);
    }

    get name(): string {
      return this.attributes.name ?? "";
    }

    closest(selectorList: string): FixtureElement | null {
      let current: FixtureElement | null = this;
      while (current) {
        if (current.matches(selectorList)) {
          return current;
        }
        current = current.parentElement;
      }
      return null;
    }

    getAttribute(name: string): string | null {
      if (name === "class") return this.className;
      if (name === "id") return this.id;
      if (name === "name") return this.attributes.name ?? null;
      return this.attributes[name] ?? null;
    }

    matches(selectorList: string): boolean {
      return selectorList.split(",").some((selector) => this.matchesSingle(selector.trim()));
    }

    querySelector(selector: string): FixtureElement | null {
      return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector: string): FixtureElement[] {
      const results: FixtureElement[] = [];
      for (const child of this.children) {
        if (child.matches(selector)) {
          results.push(child);
        }
        results.push(...child.querySelectorAll(selector));
      }
      return results;
    }

    private matchesSingle(selector: string): boolean {
      if (!selector) return false;
      if (selector.includes(" ")) {
        const [ancestorSelector, childSelector] = selector.split(/\s+/, 2);
        return this.matchesSingle(childSelector) && Boolean(this.parentElement?.closest(ancestorSelector));
      }
      if (selector === "form[action*=\"/cart/add\"]") {
        return this.tagName === "FORM" && this.attributes.action?.includes("/cart/add") === true;
      }
      if (selector === "form[action*=\"/cart/add\"] button[type=\"submit\"]") {
        return this.tagName === "BUTTON"
          && this.attributes.type === "submit"
          && Boolean(this.parentElement?.closest("form[action*=\"/cart/add\"]"));
      }
      if (selector === "button[name=\"add\"]") {
        return this.tagName === "BUTTON" && this.attributes.name === "add";
      }
      if (selector === "[data-add-to-cart]") {
        return this.attributes["data-add-to-cart"] !== undefined;
      }
      if (selector === "[data-sku-lens-component]") {
        return this.attributes["data-sku-lens-component"] !== undefined;
      }
      if (selector === "[data-media-id]") {
        return this.attributes["data-media-id"] !== undefined;
      }
      if (selector === "[name=\"id\"]") {
        return this.attributes.name === "id";
      }
      if (selector === "variant-selects select") {
        return this.tagName === "SELECT" && this.parentElement?.tagName === "VARIANT-SELECTS";
      }
      if (selector === ".single-option-selector") {
        return this.hasClass("single-option-selector");
      }
      if (selector.startsWith("[class*=")) {
        const needle = selector.slice(9, -2).toLowerCase();
        return this.className.toLowerCase().includes(needle);
      }
      if (selector.startsWith(".")) {
        return this.hasClass(selector.slice(1));
      }
      return this.tagName.toLowerCase() === selector.toLowerCase();
    }

    private hasClass(className: string): boolean {
      return this.className.split(/\s+/).includes(className);
    }
  }

  class FixtureScriptElement extends FixtureElement {
    dataset: Record<string, string>;

    constructor() {
      super("script");
      this.dataset = {
        endpoint: "https://api.example.test/ingest/events",
        publicToken: "public-1",
        shopDomain: "fixture.myshopify.com",
      };
    }
  }

  const documentListeners: Record<string, Array<(event: { target: FixtureElement }) => void>> = {};
  const windowListeners: Record<string, Array<() => void>> = {};
  const body = new FixtureElement("body");
  const script = new FixtureScriptElement();
  const media = new FixtureElement("div", {
    attributes: { "data-media-id": "media-1" },
    className: args.mediaClass,
    textContent: "Product media",
  });
  const description = new FixtureElement("div", {
    className: args.descriptionClass,
    textContent: "Product description and materials",
  });
  const form = new FixtureElement("form", {
    attributes: { action: "/cart/add" },
  });
  const button = new FixtureElement("button", {
    attributes: { name: "add", type: "submit" },
    textContent: "Add to cart",
  });
  const variants = new FixtureElement("variant-selects", { className: args.variantClass });
  const select = new FixtureElement("select", {
    value: "Blue",
  });
  const hiddenVariant = new FixtureElement("input", {
    attributes: { name: "id" },
    value: "variant-1",
  });

  form.append(hiddenVariant);
  form.append(button);
  variants.append(select);
  body.append(media);
  body.append(description);
  body.append(form);
  body.append(variants);

  const fixtureDocument = {
    addEventListener: (event: string, handler: (evt: { target: FixtureElement }) => void) => {
      documentListeners[event] ??= [];
      documentListeners[event].push(handler);
    },
    body,
    currentScript: script,
    documentElement: { scrollHeight: 1000, scrollTop: 0 },
    querySelector: (selector: string) => body.querySelector(selector),
    querySelectorAll: (selector: string) => body.querySelectorAll(selector),
    visibilityState: "visible",
  };
  const storage = new Map<string, string>();
  const fixtureWindow = {
    addEventListener: (event: string, handler: () => void) => {
      windowListeners[event] ??= [];
      windowListeners[event].push(handler);
    },
    innerHeight: 600,
    location: { pathname: "/products/demo-product", search: "" },
    pageYOffset: 0,
    ShopifyAnalytics: {
      meta: {
        page: { pageType: "product" },
        product: { id: 12345 },
      },
    },
  };

  setGlobal("document", fixtureDocument);
  setGlobal("fetch", (url: string, init?: RequestInit) => {
      expect(url).toBe("https://api.example.test/ingest/events");
      capturedBatches.push(JSON.parse(String(init?.body)) as CapturedBatch);
      return Promise.resolve(new Response("{}", { status: 202 }));
  });
  setGlobal("HTMLElement", FixtureElement);
  setGlobal("HTMLScriptElement", FixtureScriptElement);
  setGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  });
  setGlobal("window", fixtureWindow);

  try {
    Function(source)();
    for (const target of [description, media, select, button]) {
      const type = target === select ? "change" : "click";
      for (const listener of documentListeners[type] ?? []) {
        listener({ target });
      }
    }
    globalThis.window.SkuLens.flush();
    await Promise.resolve();
    return capturedBatches;
  } finally {
    for (const [name, descriptor] of previousGlobals) {
      if (descriptor) {
        Object.defineProperty(globalThis, name, descriptor);
      } else {
        delete (globalThis as Record<string, unknown>)[name];
      }
    }
  }
}

function setGlobal(name: string, value: unknown): void {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value,
    writable: true,
  });
}

function componentIds(events: CapturedBatch["events"]): string[] {
  return events
    .map((event) => event.component_id)
    .filter((componentId): componentId is string => typeof componentId === "string");
}
