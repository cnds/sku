# SKU Lens Roadmap

> This file is the single source of truth for SKU Lens product scope and roadmap.
> When priorities change, update this file by overwriting the current plan instead of appending a changelog.

## How To Maintain This Plan

- Mark a capability as `[x]` only when it is already usable in the current repo through the shipped UI, API, worker flow, demo flow, or extension.
- Keep a capability as `[ ]` if it is still partial, implied by the architecture, or only desirable for the future.
- Treat `[x]` as "exists in the repo today", not automatically "merchant-ready end to end", unless the line says so explicitly.
- Keep the product language centered on the Winners / Leakers concept. Do not broaden the plan into a generic analytics dashboard, CRO suite, or AI operator unless that scope is explicitly chosen later.

## Product Positioning

SKU Lens is a daily decision board for Shopify products.

It tells merchants which products to promote, which products to fix, why each product was flagged, and what first action to take next.

The core product promise is:

1. Show the merchant today's highest-priority product decisions.
2. Identify hidden Winners that deserve more exposure.
3. Identify Leakers with strong evidence of shopper drop-off.
4. Explain the observed signal, supporting evidence, suspected friction, and first fix to try.

## Product Boundaries

- The home page is not an analytics dashboard. It is a daily decision board.
- Winners / Leakers is the product center, not a secondary analytics view or report filter.
- A Winner means "high intent, underexposed", not "best seller".
- A Leaker means "high attention, weak progression", not "worst seller".
- The product should prioritize "which products need action today and why" over broad store overview metrics.
- AI should explain specific funnel and PDP behavior with evidence, not generate generic ecommerce advice.
- AI wording must avoid false certainty. Use suspected friction, likely cause, and first fix language unless the evidence is conclusive.
- Workflow, agency reporting, multi-store portfolios, and full task management are future extensions. They should not pull the first product away from the board plus diagnosis loop.
- Revenue impact can be introduced later, but only after funnel coverage and order attribution are strong enough to avoid false precision.

## MVP Product Constraints

- The first home experience should default to 3 priority cards: 2 Leakers and 1 Hidden Winner.
- Secondary lists such as "View more products" can exist, but they should not become the primary experience.
- Each priority card must have one main conclusion, one drop-off or opportunity, one suspected friction, and one first fix.
- Do not show long metric tables, broad filter sets, or exploratory chart panels on the first screen.
- Do not turn card recommendations into a generic AI audit checklist. Keep the card focused on the next decision.
- Every diagnosis should follow the same evidence chain: `Observed`, `Evidence`, `Suspected friction`, and `First fix to try`.
- Product cards need explicit signal states: `Ready`, `Weak signal`, `Insufficient data`, and `Tracking issue`.
- Low-data products should not receive confident AI recommendations. They should show why the signal is weak or what event is missing.
- The demo should tell three fixed stories first: a size-confidence Leaker, a media/trust Leaker, and a Hidden Winner.

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
- [ ] The home page is not yet a 3-card daily decision board.
- [ ] Winner cards do not yet explicitly frame hidden gems as high intent and underexposed.
- [ ] Leaker cards do not yet explicitly frame leaks as high attention and weak progression.
- [ ] Board entries do not yet explain the specific reason a product was flagged.
- [ ] Board entries do not yet show the likely drop-off step, suspected friction, or first fix inline.
- [ ] Board entries do not yet expose `Ready`, `Weak signal`, `Insufficient data`, or `Tracking issue` states.

### 4. Product Drop-Off Diagnosis

- [x] Each product can be analyzed against a benchmark product from the same shop.
- [x] The product analysis API returns funnel snapshots across views, add-to-cart, orders, impressions, and clicks.
- [x] The product analysis API returns component-level engagement comparisons such as `review_tab` and `size_chart`.
- [x] The current product page renders a visual score panel instead of only raw tables or JSON.
- [x] AI diagnosis is generated asynchronously and returns `pending` or `ready` from the backend.
- [x] The frontend can show a failed diagnosis state when a diagnosis request fails.
- [x] Diagnosis responses are stored and returned as markdown plus summary metadata.
- [x] Diagnosis results are reused when the same product snapshot has already been analyzed.
- [x] A fallback diagnosis path exists when OpenAI-compatible AI output is unavailable.
- [ ] The product page does not yet present a step-by-step shopper journey with the primary drop-off step highlighted.
- [ ] The diagnosis prompt and UI do not yet reliably connect a drop-off step to one primary suspected PDP friction.
- [ ] Diagnosis output is not yet normalized into `Observed`, `Evidence`, `Suspected friction`, and `First fix to try`.
- [ ] Diagnosis cards do not yet enforce one primary conclusion and one first fix.
- [ ] The web-triggered diagnosis payload does not yet include every behavior field that the backend snapshot model supports.

### 5. Demo And Delivery Readiness

- [x] The repo can seed a repeatable demo shop at `demo.myshopify.com`.
- [x] Demo seed data includes leaderboard rows, product analysis inputs, and ready-made diagnosis cards.
- [x] The web app defaults missing or invalid analytics windows to `24h`.
- [x] Request tracing propagates `X-SKU-Lens-Request-Id` across server, web, and storefront flows.
- [x] Browser-side debug logging is intentionally silent by default and can be enabled manually with `localStorage['sku-lens:debug'] = '1'`.
- [ ] The demo does not yet tell the 3-card daily decision story with two Leakers and one Hidden Winner.
- [ ] The demo does not yet show size confidence, media trust, and underexposed-winner narratives as fixed examples.

## Product Gaps To Close Next

- [ ] Complete storefront funnel tracking for PDP `view`, buy-box intent, PDP component clicks, `add_to_cart`, and related conversion actions so Winners / Leakers placement is based on full shopper behavior.
- [ ] Convert board rows into daily decision cards that answer: why this product is here, where shoppers drop off or where the opportunity is, what evidence supports the call, and what first fix or promotion action to try.
- [ ] Define a drop-off taxonomy that maps funnel steps to suspected PDP frictions, such as product image friction, missing social proof, unclear sizing, variant selection friction, hidden shipping/returns, or weak CTA placement.
- [ ] Normalize diagnosis generation and parsing so every producer maps cleanly to `Observed`, `Evidence`, `Suspected friction`, and `First fix to try`.
- [ ] Add signal-state logic for `Ready`, `Weak signal`, `Insufficient data`, and `Tracking issue`.
- [ ] Include all supported behavior fields in web-created diagnosis snapshots, including impressions, clicks, media interactions, variant changes, dwell, scroll, and component impressions.
- [ ] Replace the raw JSON/POST-only OAuth callback handling with a merchant-friendly browser install, post-install, and onboarding flow inside the embedded app.
- [ ] Add a merchant-visible integration health check that confirms tracker install, webhook connectivity, and recent data arrival.

## Roadmap

### Near-Term

- [ ] Reframe the home page as `Today's product priorities`, not a generic dashboard.
- [ ] Default the first screen to 3 priority cards: 2 Leakers and 1 Hidden Winner.
- [ ] Define Winner as `High intent, underexposed` in the UI.
- [ ] Define Leaker as `High attention, weak progression` in the UI.
- [ ] Add inline explanations to each priority card: why flagged, drop-off or opportunity, evidence, suspected friction, and first fix.
- [ ] Add signal states to priority cards so low-data products show `Weak signal`, `Insufficient data`, or `Tracking issue` instead of confident recommendations.
- [ ] Add a product detail diagnosis layout centered on the shopper journey: exposure, click, PDP view, media/review/size/variant engagement, add-to-cart, and order.
- [ ] Highlight the primary drop-off step in the product detail page and show the evidence that supports it.
- [ ] Update demo seed content so the first three cards tell clear stories: size-confidence leak, media/trust leak, and hidden winner.
- [ ] Improve board and diagnosis terminology around `winning`, `leaking shoppers`, `drop-off`, `likely cause`, and `recommended fix`.

### Mid-Term

- [ ] Add better storefront component labeling so AI can reason about real theme sections instead of generic component ids.
- [ ] Add a compact "View more products" path after the 3-card daily decision board without turning the home page into a dashboard.
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
2. Redesign the home page into a 3-card daily decision board.
3. Add signal states so weak or missing data does not produce overconfident AI recommendations.
4. Normalize AI diagnosis structure and snapshot data so every recommendation stays evidence-backed.
5. Redesign the product page around one primary drop-off, one suspected friction, and one first fix.
6. Add history, status, and impact tracking only after the daily decision board is reliable.
