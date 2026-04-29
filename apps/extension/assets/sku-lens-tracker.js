(function () {
  var script = document.currentScript;
  if (!(script instanceof HTMLScriptElement)) return;

  var DEBUG_STORAGE_KEY = "sku-lens:debug";
  var REQUEST_ID_HEADER = "X-SKU-Lens-Request-Id";

  function generateId() {
    return crypto.randomUUID
      ? crypto.randomUUID()
      : Date.now() + "-" + Math.random().toString(36).slice(2);
  }

  function debugEnabled() {
    try {
      return localStorage.getItem(DEBUG_STORAGE_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  function log(level, event, fields) {
    if (!debugEnabled()) return;

    var timestamp = new Date().toISOString();
    var keys = [
      "request_id",
      "status",
      "path",
      "event_count",
      "shop_domain",
      "error",
    ];
    var entries = [];
    var seen = {};

    for (var i = 0; i < keys.length; i++) {
      var orderedKey = keys[i];
      if (fields[orderedKey] === undefined || fields[orderedKey] === null || fields[orderedKey] === "") continue;
      seen[orderedKey] = true;
      entries.push(orderedKey + "=" + formatLogValue(fields[orderedKey]));
    }

    var extraKeys = Object.keys(fields).sort();
    for (var j = 0; j < extraKeys.length; j++) {
      var key = extraKeys[j];
      if (seen[key]) continue;
      if (fields[key] === undefined || fields[key] === null || fields[key] === "") continue;
      entries.push(key + "=" + formatLogValue(fields[key]));
    }

    var line = timestamp + " " + level.toUpperCase() + " [extension][tracker][" + event + "]";
    if (entries.length) {
      line += " " + entries.join(" ");
    }

    if (level === "debug") console.debug(line);
    else if (level === "info") console.info(line);
    else if (level === "warn") console.warn(line);
    else console.error(line);
  }

  function formatLogValue(value) {
    if (typeof value === "boolean" || typeof value === "number") return String(value);
    if (typeof value === "object") return JSON.stringify(value);

    var text = String(value);
    if (!text) return "\"\"";
    if (/\s|["'=]/.test(text)) return JSON.stringify(text);
    return text;
  }

  var endpoint = script.dataset.endpoint;
  var publicToken = script.dataset.publicToken;
  var shopDomain = script.dataset.shopDomain;
  if (!endpoint || !publicToken || !shopDomain) {
    log("info", "tracker.boot_skipped", { error: "missing tracker config" });
    return;
  }

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var MAX_QUEUE_SIZE = 50;
  var FLUSH_THRESHOLD = 5;
  var SESSION_TTL_MS = 30 * 60 * 1000;
  var IMPRESSION_DWELL_MS = 1000;

  var PRODUCT_CARD_SELECTORS = [
    "product-card",
    ".product-card",
    ".card--product",
    ".grid-product",
    ".product-item",
    ".product-grid-item",
    "[data-product-id]",
    "[data-sku-lens-component]",
  ].join(",");

  var MEDIA_TRIGGER_SELECTORS = [
    ".product__media-toggle",
    ".slider-button",
    ".product__media-icon",
    ".product-gallery__nav-item",
    'button[name="previous"]',
    'button[name="next"]',
    "deferred-media button",
    "[data-media-id]",
  ].join(",");

  var VARIANT_SELECTORS = [
    "variant-selects select",
    'variant-radios input[type="radio"]',
    ".single-option-selector",
    ".product-form__input select",
    '.product-form__input input[type="radio"]',
    ".swatch-element input",
    '[name="id"]',
  ].join(",");

  // ---------------------------------------------------------------------------
  // Identity & session
  // ---------------------------------------------------------------------------

  function ensureId(key) {
    var v = localStorage.getItem(key);
    if (v) return v;
    var next = generateId();
    localStorage.setItem(key, next);
    return next;
  }

  function getSessionId() {
    var sKey = "sku-lens:session-id";
    var tKey = "sku-lens:session-ts";
    var now = Date.now();
    if (now - (Number(localStorage.getItem(tKey)) || 0) > SESSION_TTL_MS) {
      localStorage.setItem(sKey, generateId());
    }
    localStorage.setItem(tKey, String(now));
    return ensureId(sKey);
  }

  var queue = [];
  var visitorId = ensureId("sku-lens:visitor-id");
  var sessionId = getSessionId();

  // ---------------------------------------------------------------------------
  // Product ID resolution
  // ---------------------------------------------------------------------------

  function resolveProductId(element) {
    if (element) {
      var card = element.closest("[data-product-id]");
      if (card) return card.getAttribute("data-product-id");

      var link = element.closest('a[href*="/products/"]');
      if (link) {
        var m = link.getAttribute("href").match(/\/products\/([^?#/]+)/);
        if (m) return "handle:" + m[1];
      }
    }

    if (
      window.ShopifyAnalytics &&
      window.ShopifyAnalytics.meta &&
      window.ShopifyAnalytics.meta.product
    ) {
      return String(window.ShopifyAnalytics.meta.product.id);
    }

    var node = document.querySelector("[data-product-id]");
    return node ? node.getAttribute("data-product-id") : null;
  }

  function resolvePageType() {
    var meta = window.ShopifyAnalytics && window.ShopifyAnalytics.meta;
    if (meta && meta.page) {
      var pt = meta.page.pageType || "";
      if (pt === "product") return "pdp";
      if (pt === "collection") return "collection";
      if (pt === "search") return "search";
      if (pt === "home" || pt === "index") return "home";
    }
    var p = window.location.pathname;
    if (/^\/products\//.test(p)) return "pdp";
    if (/^\/collections\//.test(p)) return "collection";
    if (/^\/search/.test(p)) return "search";
    if (p === "/" || p === "") return "home";
    return "other";
  }

  function findSectionName(element) {
    var section = element.closest(".shopify-section");
    if (section) {
      var id = section.id || "";
      var m = id.match(/__(.+)$/);
      return m ? m[1] : id;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Queue & flush
  // ---------------------------------------------------------------------------

  function track(eventType, options) {
    if (queue.length >= MAX_QUEUE_SIZE) {
      var dropped = queue.shift();
      log("warn", "tracker.queue_dropped", {
        event_count: 1,
        event_type: dropped ? dropped.event_type : null,
        shop_domain: shopDomain,
      });
    }
    queue.push({
      event_type: eventType,
      occurred_at: new Date().toISOString(),
      product_id: (options && options.productId !== undefined) ? options.productId : null,
      variant_id: (options && options.variantId) || null,
      component_id: (options && options.componentId) || null,
      context: (options && options.context) || {},
    });
    if (queue.length >= FLUSH_THRESHOLD) flush();
  }

  function flush() {
    if (!queue.length) return;
    var events = queue.splice(0, queue.length);
    var requestId = generateId();
    log("debug", "tracker.flush_started", {
      event_count: events.length,
      path: endpoint,
      request_id: requestId,
      shop_domain: shopDomain,
    });
    fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-SKU-Lens-Public-Token": publicToken,
        "X-SKU-Lens-Request-Id": requestId,
        "X-SKU-Lens-Timestamp": String(Math.floor(Date.now() / 1000)),
      },
      body: JSON.stringify({
        events: events,
        session_id: sessionId,
        shop_domain: shopDomain,
        visitor_id: visitorId,
      }),
      keepalive: true,
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("Tracker flush failed with status " + response.status + ".");
      }

      log("debug", "tracker.flush_completed", {
        event_count: events.length,
        request_id: requestId,
        shop_domain: shopDomain,
        status: response.status,
      });
    }).catch(function (error) {
      var remaining = MAX_QUEUE_SIZE - queue.length;
      if (remaining > 0) queue.unshift.apply(queue, events.slice(0, remaining));
      log("error", "tracker.flush_failed", {
        error: error && error.message ? error.message : String(error),
        event_count: events.length,
        path: endpoint,
        request_id: requestId,
        shop_domain: shopDomain,
      });
    });
  }

  // ---------------------------------------------------------------------------
  // impression — IntersectionObserver on product cards
  // ---------------------------------------------------------------------------

  function initImpressionTracking() {
    if (typeof IntersectionObserver === "undefined") return null;

    var fired = new WeakSet();
    var timers = new WeakMap();

    var observer = new IntersectionObserver(
      function (entries) {
        for (var i = 0; i < entries.length; i++) {
          var entry = entries[i];
          var el = entry.target;

          if (entry.isIntersecting && !fired.has(el)) {
            (function (target) {
              var t = setTimeout(function () {
                if (fired.has(target)) return;
                fired.add(target);
                var productId = resolveProductId(target);
                if (!productId) return;
                var cards = document.querySelectorAll(PRODUCT_CARD_SELECTORS);
                var pos = -1;
                for (var j = 0; j < cards.length; j++) {
                  if (cards[j] === target) { pos = j; break; }
                }
                track("impression", {
                  productId: productId,
                  componentId: findSectionName(target),
                  context: { position: pos >= 0 ? pos : null },
                });
              }, IMPRESSION_DWELL_MS);
              timers.set(target, t);
            })(el);
          } else if (!entry.isIntersecting) {
            var existing = timers.get(el);
            if (existing) {
              clearTimeout(existing);
              timers.delete(el);
            }
          }
        }
      },
      { threshold: 0.5 }
    );

    function observeCards() {
      var cards = document.querySelectorAll(PRODUCT_CARD_SELECTORS);
      for (var i = 0; i < cards.length; i++) {
        if (!fired.has(cards[i])) observer.observe(cards[i]);
      }
    }

    observeCards();
    return { refresh: observeCards };
  }

  // ---------------------------------------------------------------------------
  // click — event delegation on product cards
  // ---------------------------------------------------------------------------

  function initClickTracking() {
    document.addEventListener(
      "click",
      function (event) {
        var target =
          event.target instanceof HTMLElement ? event.target : null;
        if (!target || !target.closest) return;

        var card = target.closest(PRODUCT_CARD_SELECTORS);
        if (!card) return;

        var productId = resolveProductId(card);
        if (!productId) return;

        var cards = document.querySelectorAll(PRODUCT_CARD_SELECTORS);
        var pos = -1;
        for (var i = 0; i < cards.length; i++) {
          if (cards[i] === card) { pos = i; break; }
        }

        var link =
          card.querySelector('a[href*="/products/"]') || target.closest("a");
        var targetUrl = link ? link.getAttribute("href") : null;

        track("click", {
          productId: productId,
          componentId: findSectionName(card),
          context: { position: pos >= 0 ? pos : null, target_url: targetUrl },
        });
      },
      true
    );
  }

  // ---------------------------------------------------------------------------
  // media — PDP gallery interactions
  // ---------------------------------------------------------------------------

  function initMediaTracking() {
    if (resolvePageType() !== "pdp") return;

    document.addEventListener(
      "click",
      function (event) {
        var target =
          event.target instanceof HTMLElement ? event.target : null;
        if (!target || !target.closest) return;

        var trigger = target.closest(MEDIA_TRIGGER_SELECTORS);
        if (!trigger) return;

        var productId = resolveProductId(null);
        if (!productId) return;

        track("media", {
          productId: productId,
          context: {
            action: classifyMediaAction(trigger),
            media_index: resolveMediaIndex(trigger),
          },
        });
      },
      true
    );
  }

  function classifyMediaAction(el) {
    var name = el.getAttribute("name") || "";
    if (name === "previous" || el.classList.contains("slider-prev")) return "prev";
    if (name === "next" || el.classList.contains("slider-next")) return "next";
    if (
      el.closest(".product__media-icon") ||
      el.closest("[data-zoom]") ||
      el.classList.contains("zoom-button")
    ) return "zoom";
    if (
      el.closest("deferred-media") ||
      el.closest('[data-type="video"]') ||
      el.closest('[data-type="external_video"]')
    ) return "video_play";
    return "next";
  }

  function resolveMediaIndex(el) {
    var item = el.closest("[data-media-id]") || el.closest(".product__media-item");
    if (!item || !item.parentElement) return null;
    var siblings = item.parentElement.children;
    for (var i = 0; i < siblings.length; i++) {
      if (siblings[i] === item) return i;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // variant — selector change events
  // ---------------------------------------------------------------------------

  function initVariantTracking() {
    if (resolvePageType() !== "pdp") return;

    document.addEventListener(
      "change",
      function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (!target.matches(VARIANT_SELECTORS)) return;

        var productId = resolveProductId(null);
        if (!productId) return;

        track("variant", {
          productId: productId,
          variantId: resolveSelectedVariantId(),
          context: { options: collectSelectedOptions() },
        });
      },
      true
    );
  }

  function resolveSelectedVariantId() {
    var hidden = document.querySelector('form[action*="/cart/add"] [name="id"]');
    if (hidden && hidden.value) return hidden.value;
    var params = new URLSearchParams(window.location.search);
    return params.get("variant") || null;
  }

  function collectSelectedOptions() {
    var opts = {};

    var selects = document.querySelectorAll("variant-selects select");
    for (var i = 0; i < selects.length; i++) {
      var label = selects[i].closest(".product-form__input");
      var name = label
        ? (label.querySelector("label") || {}).textContent || selects[i].name
        : selects[i].name;
      opts[name.trim()] = selects[i].value;
    }

    var radios = document.querySelectorAll(
      'variant-radios input[type="radio"]:checked'
    );
    for (var j = 0; j < radios.length; j++) {
      var rlabel = radios[j].closest(".product-form__input");
      var rname = rlabel
        ? (rlabel.querySelector("legend") || {}).textContent || radios[j].name
        : radios[j].name;
      opts[rname.trim()] = radios[j].value;
    }

    if (Object.keys(opts).length === 0) {
      var legacy = document.querySelectorAll(".single-option-selector");
      for (var k = 0; k < legacy.length; k++) {
        opts["Option " + (k + 1)] = legacy[k].value;
      }
    }

    return opts;
  }

  // ---------------------------------------------------------------------------
  // engage — dwell time + scroll depth, fires on page exit
  // ---------------------------------------------------------------------------

  function initEngageTracking() {
    var startTime = Date.now();
    var maxScrollPct = 0;
    var pageType = resolvePageType();
    var hasFired = false;

    var scrollTimer = null;
    function updateScroll() {
      var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      var docHeight = Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight
      );
      var winHeight = window.innerHeight;
      var scrollable = docHeight - winHeight;
      if (scrollable > 0) {
        var pct = Math.round((scrollTop / scrollable) * 100);
        if (pct > maxScrollPct) maxScrollPct = pct;
      }
    }

    window.addEventListener(
      "scroll",
      function () {
        if (scrollTimer) return;
        scrollTimer = setTimeout(function () {
          scrollTimer = null;
          updateScroll();
        }, 200);
      },
      { passive: true }
    );

    function fireEngage() {
      if (hasFired) return;
      hasFired = true;
      var dwellMs = Date.now() - startTime;
      if (dwellMs < 500) return;
      updateScroll();
      track("engage", {
        productId: resolveProductId(null),
        context: {
          dwell_ms: dwellMs,
          max_scroll_pct: maxScrollPct,
          page_type: pageType,
        },
      });
      flush();
    }

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") fireEngage();
    });
    window.addEventListener("pagehide", fireEngage);
    window.addEventListener("popstate", fireEngage);
    document.addEventListener("turbo:before-visit", fireEngage);
  }

  // ---------------------------------------------------------------------------
  // SPA support — MutationObserver to re-scan for new product cards
  // ---------------------------------------------------------------------------

  function initMutationWatcher(impressionTracker) {
    if (typeof MutationObserver === "undefined" || !impressionTracker) return;

    var debounceTimer = null;
    var observer = new MutationObserver(function () {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        impressionTracker.refresh();
      }, 300);
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------

  var impressionTracker = initImpressionTracking();
  initClickTracking();
  initMediaTracking();
  initVariantTracking();
  initEngageTracking();
  initMutationWatcher(impressionTracker);

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);

  window.SkuLens = { flush: flush };
})();
