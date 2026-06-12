import {register} from "@shopify/web-pixels-extension";

const STANDARD_EVENTS = [
  "page_viewed",
  "product_viewed",
  "collection_viewed",
  "search_submitted",
  "cart_viewed",
  "product_added_to_cart",
  "product_removed_from_cart",
  "checkout_started",
  "checkout_contact_info_submitted",
  "checkout_address_info_submitted",
  "checkout_shipping_info_submitted",
  "payment_info_submitted",
  "checkout_completed",
];

register(async ({analytics, browser, configuration, settings}) => {
  const resolvedSettings = settings || configuration || {};
  const endpoint = resolvedSettings.endpoint;
  const publicToken = resolvedSettings.publicToken;
  const shopDomain = resolvedSettings.shopDomain;
  if (!endpoint || !publicToken || !shopDomain) return;

  const visitorId = await resolveVisitorId(browser);
  const sessionId = await resolveSessionId(browser);

  STANDARD_EVENTS.forEach((eventName) => {
    analytics.subscribe(eventName, (event) => {
      const events = normalizeEvent(event);
      if (events.length === 0) return;

      fetch(endpoint, {
        body: JSON.stringify({
          events,
          session_id: sessionId,
          shop_domain: shopDomain,
          visitor_id: visitorId,
        }),
        headers: {
          "Content-Type": "application/json",
          "X-SKU-Lens-Public-Token": publicToken,
          "X-SKU-Lens-Request-Id": generateId(),
          "X-SKU-Lens-Timestamp": String(Math.floor(Date.now() / 1000)),
        },
        keepalive: true,
        method: "POST",
      }).catch(() => undefined);
    });
  });
});

async function resolveVisitorId(browser) {
  const existing = await browser.cookie.get("sku_lens_pixel_visitor_id");
  if (existing) return existing;

  const next = generateId();
  await browser.cookie.set("sku_lens_pixel_visitor_id", next);
  return next;
}

async function resolveSessionId(browser) {
  const existing = await browser.cookie.get("sku_lens_pixel_session_id");
  if (existing) return existing;

  const next = generateId();
  await browser.cookie.set("sku_lens_pixel_session_id", next);
  return next;
}

function normalizeEvent(event) {
  const base = {
    event_id: String(event.id || generateId()),
    occurred_at: event.timestamp || new Date().toISOString(),
    source_event_name: event.name,
  };

  if (event.name === "product_viewed") {
    return [
      {
        ...base,
        product_id: normalizeId(event.data?.productVariant?.product?.id),
        variant_id: normalizeId(event.data?.productVariant?.id),
        context: pageContext(event),
      },
    ];
  }

  if (event.name === "product_added_to_cart" || event.name === "product_removed_from_cart") {
    const cartLine = event.data?.cartLine;
    const merchandise = cartLine?.merchandise;
    return [
      {
        ...base,
        product_id: normalizeId(merchandise?.product?.id),
        variant_id: normalizeId(merchandise?.id),
        context: {
          ...pageContext(event),
          line_item_id: normalizeId(cartLine?.id),
          quantity: numberOrNull(cartLine?.quantity),
        },
      },
    ];
  }

  if (event.name === "checkout_completed") {
    return checkoutLineEvents(event, base, {
      checkout_token: event.data?.checkout?.token || null,
      order_id: normalizeId(event.data?.checkout?.order?.id),
    });
  }

  if (isCheckoutStepEvent(event.name)) {
    return checkoutLineEvents(event, base, {
      checkout_token: event.data?.checkout?.token || null,
      checkout_step: event.name,
    });
  }

  return [
    {
      ...base,
      context: {
        ...pageContext(event),
        collection_id: normalizeId(event.data?.collection?.id),
        search_query: event.data?.searchResult?.query || event.data?.search?.query || null,
      },
    },
  ];
}

function checkoutLineEvents(event, base, extraContext) {
  const lineItems = event.data?.checkout?.lineItems || [];
  if (!Array.isArray(lineItems) || lineItems.length === 0) {
    return [
      {
        ...base,
        context: {
          ...pageContext(event),
          ...extraContext,
        },
      },
    ];
  }

  return lineItems.map((lineItem, index) => {
    const variant = lineItem.variant || lineItem.merchandise;
    return {
      ...base,
      product_id: normalizeId(variant?.product?.id),
      variant_id: normalizeId(variant?.id),
      context: {
        ...pageContext(event),
        ...extraContext,
        line_item_id: normalizeId(lineItem.id),
        line_item_index: index,
        quantity: numberOrNull(lineItem.quantity),
      },
    };
  });
}

function isCheckoutStepEvent(eventName) {
  return eventName === "checkout_started"
    || eventName === "checkout_contact_info_submitted"
    || eventName === "checkout_address_info_submitted"
    || eventName === "checkout_shipping_info_submitted"
    || eventName === "payment_info_submitted";
}

function pageContext(event) {
  const location = event.context?.window?.location;
  return {
    page_path: location?.pathname || null,
    page_title: event.context?.document?.title || null,
    page_url: location?.href || null,
  };
}

function normalizeId(value) {
  if (value === undefined || value === null || value === "") return null;
  const text = String(value);
  const match = text.match(/\/([^/]+)$/);
  return match ? match[1] : text;
}

function numberOrNull(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function generateId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : Date.now() + "-" + Math.random().toString(36).slice(2);
}
