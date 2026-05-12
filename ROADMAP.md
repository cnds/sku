# SKU Lens Roadmap

> This file is the single source of truth for SKU Lens product scope and roadmap.
> When priorities change, update this file by overwriting the current plan instead of appending a changelog.

## How To Maintain This Plan

- Mark a capability as `[x]` only when it is already usable in the current repo through the shipped UI, API, worker flow, demo flow, or extension.
- Keep a capability as `[ ]` if it is still partial, implied by the architecture, or only desirable for the future.
- Treat `[x]` as "exists in the repo today", not automatically "merchant-ready end to end", unless the line says so explicitly.
- Keep the product language centered on the Winners / Leakers concept. Do not broaden the plan into a generic analytics dashboard, CRO suite, or AI operator unless that scope is explicitly chosen later.

## Product Positioning

SKU Lens is an AI-powered Winners / Leakers board for Shopify products.

It tells merchants which products are winning or leaking shoppers, where the shopper journey breaks, what on the PDP may have caused that drop-off, and what to fix or promote next.

The core product promise is:

1. Show the merchant which products deserve attention.
2. Explain why each product is a Winner or a Leaker.
3. Identify the likely drop-off step in the shopper journey.
4. Use AI to turn the evidence into a concrete PDP recommendation.

## Product Boundaries

- Winners / Leakers is the product center, not a secondary analytics view.
- The product should prioritize "why this product is on the board" over broad store overview metrics.
- AI should explain specific funnel and PDP behavior, not generate generic ecommerce advice.
- Workflow, agency reporting, multi-store portfolios, and full task management are future extensions. They should not pull the first product away from the board plus diagnosis loop.
- Revenue impact can be introduced later, but only after funnel coverage and order attribution are strong enough to avoid false precision.

## Current Product Scope

### 1. Store Integration And Data Intake

- [x] A signed Shopify installation callback endpoint can create or update a shop installation record.
- [x] Each installed shop stores its own public ingest token.
- [x] Each installed shop stores its IANA timezone and uses it as the basis for analytics windows and daily rollups.
- [x] A Theme App Extension block can inject the SKU Lens storefront tracker into a Shopify storefront.
- [x] The shipped tracker batches `impression`, `click`, `media`, `variant`, and `engage` events to `/ingest/events`.
- [x] The tracker keeps per-visitor and per-session identifiers so storefront behavior can be grouped over time.
- [x] Shopify order webhooks can be converted into product-level order ingestion events.
- [x] Ingest requests are protected by a shop-specific public token plus timestamp validation.

### 2. Product Behavior Pipeline

- [x] Raw event data is persisted before downstream rollups and analysis.
- [x] Daily product stats are rebuilt from raw events instead of being maintained only as counters.
- [x] Daily rollups respect each merchant's local calendar day instead of the server's UTC day.
- [x] A single ingest batch can update multiple local `stat_date` values when events cross local midnight boundaries.
- [x] Background jobs are used for rollup follow-up work and AI diagnosis generation.
- [x] Product rankings can be queried for `24h`, `7d`, and `30d` windows.
- [ ] Current windows are day-bucket based, not exact rolling-hour behavioral windows.

### 3. Winners And Leakers

- [x] SKU Lens has an embedded Shopify admin app as the primary merchant-facing surface.
- [x] The dashboard shows `Winners` for hidden-gem products.
- [x] The dashboard shows `Leakers` for products losing shoppers before they buy.
- [x] Merchants can switch board rankings across `24h`, `7d`, and `30d`.
- [x] Merchants can drill from a board entry into a product analysis page.
- [x] Ranking logic uses opportunity/gap scoring when the required funnel inputs are present.
- [ ] Board entries do not yet explain the specific reason a product was flagged.
- [ ] Board entries do not yet show the likely drop-off step or the first AI recommendation inline.

### 4. Product Drop-Off Diagnosis

- [x] Each product can be analyzed against a benchmark product from the same shop.
- [x] The product analysis API returns funnel snapshots across views, add-to-cart, orders, impressions, and clicks.
- [x] The product analysis API returns component-level engagement comparisons such as `review_tab` and `size_chart`.
- [x] The current product page renders a visual score panel instead of only raw tables or JSON.
- [x] AI diagnosis is generated asynchronously and returns `pending` or `ready` from the backend.
- [x] The frontend can show a failed diagnosis state when a diagnosis request fails.
- [x] Diagnosis responses are stored and returned as markdown plus summary metadata.
- [x] Diagnosis results are reused when the same product snapshot has already been analyzed.
- [x] A fallback diagnosis path exists when Gemini output is unavailable.
- [ ] The product page does not yet present a step-by-step shopper journey with the primary drop-off step highlighted.
- [ ] The diagnosis prompt and UI do not yet reliably connect a drop-off step to a merchant-controlled PDP cause.
- [ ] The web-triggered diagnosis payload does not yet include every behavior field that the backend snapshot model supports.

### 5. Demo And Delivery Readiness

- [x] The repo can seed a repeatable demo shop at `demo.myshopify.com`.
- [x] Demo seed data includes leaderboard rows, product analysis inputs, and ready-made diagnosis cards.
- [x] The web app defaults missing or invalid analytics windows to `24h`.
- [x] Request tracing propagates `X-SKU-Lens-Request-Id` across server, web, and storefront flows.
- [x] Browser-side debug logging is intentionally silent by default and can be enabled manually with `localStorage['sku-lens:debug'] = '1'`.
- [ ] The demo does not yet tell the full Winners / Leakers story with realistic PDP drop-off causes.

## Product Gaps To Close Next

- [ ] Complete storefront funnel tracking for PDP `view`, buy-box intent, PDP component clicks, `add_to_cart`, and related conversion actions so Winners / Leakers placement is based on full shopper behavior.
- [ ] Convert board rows into board cards that answer: why this product is here, where shoppers drop off, and what AI recommends next.
- [ ] Define a drop-off taxonomy that maps funnel steps to likely PDP causes, such as product image friction, missing social proof, unclear sizing, variant selection friction, hidden shipping/returns, or weak CTA placement.
- [ ] Normalize diagnosis markdown generation and parsing so every producer maps cleanly to `Problem`, `Drop-Off Evidence`, `Likely Cause`, and `Recommended Fixes`.
- [ ] Include all supported behavior fields in web-created diagnosis snapshots, including impressions, clicks, media interactions, variant changes, dwell, scroll, and component impressions.
- [ ] Replace the raw JSON/POST-only OAuth callback handling with a merchant-friendly browser install, post-install, and onboarding flow inside the embedded app.
- [ ] Add a merchant-visible integration health check that confirms tracker install, webhook connectivity, and recent data arrival.

## Roadmap

### Near-Term

- [ ] Reframe the dashboard as a richer Winners / Leakers home screen, not a generic analytics dashboard.
- [ ] Add inline AI explanations to each board item: flag reason, suspected drop-off step, confidence, and first recommendation.
- [ ] Add a product detail diagnosis layout centered on the shopper journey: exposure, click, PDP view, media/review/size/variant engagement, add-to-cart, and order.
- [ ] Highlight the primary drop-off step in the product detail page and show the evidence that supports it.
- [ ] Update demo seed content so the top Winners and Leakers demonstrate clear, realistic stories.
- [ ] Improve board and diagnosis terminology around `winning`, `leaking shoppers`, `drop-off`, `likely cause`, and `recommended fix`.

### Mid-Term

- [ ] Add better storefront component labeling so AI can reason about real theme sections instead of generic component ids.
- [ ] Add trend context for board entries so merchants can see whether a product is newly flagged, worsening, or improving.
- [ ] Add diagnosis freshness, last generated time, and explicit re-run controls.
- [ ] Add a lightweight recommendation status for each diagnosis: `New`, `Planned`, `Testing`, `Implemented`, and `Improved`.
- [ ] Store diagnosis history so merchants can see whether a PDP improved after page changes.
- [ ] Add cautious impact estimates once funnel coverage is strong enough, starting with directional upside/downside instead of precise revenue claims.

### Long-Term

- [ ] Add improvement detection so the product can show when a prior recommendation appears to have worked.
- [ ] Benchmark products against category peers and product cohorts, not only against one in-store benchmark.
- [ ] Expand Winners / Leakers logic beyond single PDPs into collection placement and merchandising opportunities.
- [ ] Add batch diagnosis for many products while keeping the board as the primary prioritization surface.
- [ ] Add agency or multi-store views only after the single-store Winners / Leakers loop is strong.

## Recommended Priority Order

1. Complete the missing funnel instrumentation so Winners / Leakers placement has stronger ground truth.
2. Redesign board entries around explanation: why flagged, where drop-off happens, and what to do next.
3. Redesign the product page around drop-off diagnosis rather than generic scoring.
4. Normalize AI diagnosis structure and snapshot data so recommendations stay evidence-backed.
5. Add history, status, and impact tracking only after the board plus diagnosis loop is reliable.
