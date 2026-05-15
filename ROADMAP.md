# SKU Lens Roadmap

> This file is the single source of truth for SKU Lens product scope and roadmap.
> When priorities change, update this file by overwriting the current plan instead of appending a changelog.

## How To Maintain This Plan

- Mark a capability as `[x]` only when it is already usable in the current repo through the shipped UI, API, worker flow, demo flow, or extension.
- Keep a capability as `[ ]` if it is still partial, implied by the architecture, or only desirable for the future.
- Treat `[x]` as "exists in the repo today", not automatically "merchant-ready end to end", unless the line says so explicitly.
- Keep the product language centered on the Winners / Leakers daily decision board. Do not broaden the plan into a generic analytics dashboard, CRO suite, or AI operator unless that scope is explicitly chosen later.

## Product Positioning

SKU Lens is a daily decision board for Shopify products.

It tells merchants which products to promote, which products to fix, why each product was flagged, and what first action to take next.

The core product promise is:

1. Show today's highest-priority product decisions.
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
- The secondary product list can keep using `/api/leaderboard` internally, but user-facing UI should not center on exposed scores or rankings.
- Workflow, agency reporting, multi-store portfolios, and full task management are future extensions. They should not pull the first product away from the board plus diagnosis loop.
- Revenue impact can be introduced later, but only after funnel coverage and order attribution are strong enough to avoid false precision.

## MVP Product Constraints

- The first home experience defaults to up to 3 priority cards: 2 Leakers and 1 Hidden Winner.
- Secondary lists such as "View more products" can exist, but they should not become the primary experience.
- Each priority card must have one main conclusion, one drop-off or opportunity, one suspected friction, and one first fix.
- Do not show long metric tables, broad filter sets, exploratory chart panels, or exposed score-first tables on the first screen.
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
- [x] The shipped tracker batches `impression`, `click`, `view`, `component_click`, `add_to_cart`, `media`, `variant`, and `engage` events to `/ingest/events`.
- [x] The tracker keeps per-visitor and per-session identifiers so storefront behavior can be grouped over time.
- [x] Shopify order webhooks can be converted into product-level order ingestion events.
- [x] Ingest requests are protected by a shop-specific public token plus timestamp validation.

### 2. Product Behavior Pipeline

- [x] Raw event data is persisted before downstream rollups and analysis.
- [x] Daily product stats are rebuilt from raw events instead of being maintained only as counters.
- [x] Daily rollups respect each merchant's local calendar day instead of the server's UTC day.
- [x] A single ingest batch can update multiple local `stat_date` values when events cross local midnight boundaries.
- [x] Background jobs are used for rollup follow-up work and AI diagnosis generation.
- [x] Product behavior can be queried for `24h`, `7d`, and `30d` windows.
- [x] `/api/priorities` is the board API for the daily decision cards.
- [x] `/api/leaderboard` remains available as a secondary/internal product-list API.
- [ ] Current windows are day-bucket based, not exact rolling-hour behavioral windows.

### 3. Daily Decision Board

- [x] SKU Lens has an embedded Shopify admin app as the primary merchant-facing surface.
- [x] The home page is centered on `Today's product priorities`.
- [x] The first screen uses up to 3 priority cards: 2 Leakers and 1 Hidden Winner when data supports that mix.
- [x] `Winners` are framed as `High intent, underexposed`.
- [x] `Leakers` are framed as `High attention, weak progression`.
- [x] Merchants can switch the board window across `24h`, `7d`, and `30d`.
- [x] Priority cards expose `Ready`, `Weak signal`, `Insufficient data`, and `Tracking issue`.
- [x] Each priority card shows why the product was flagged, the drop-off or opportunity step, supporting evidence, suspected friction, and first fix.
- [x] Merchants can drill from a priority card or secondary product list into a product analysis page.
- [x] `View more products` is present as a compact secondary discovery path after the priority cards.
- [x] Secondary product lists keep score internal and show recent activity instead of score-first table columns.

### 4. Product Drop-Off Diagnosis

- [x] Each product can be analyzed against a benchmark product from the same shop.
- [x] The product analysis API returns funnel snapshots across exposure, click, PDP view, engagement, add-to-cart, and order behavior.
- [x] The product analysis API returns component-level engagement comparisons such as `review_tab`, `size_chart`, and theme-derived component ids.
- [x] The product page presents a step-by-step shopper journey with exposure, click, PDP view, engagement, add-to-cart, and order.
- [x] The product page highlights the primary drop-off step and shows evidence, suspected friction, and a first fix.
- [x] AI diagnosis is generated asynchronously and returns `pending`, `ready`, or `failed` states.
- [x] Diagnosis responses are stored and returned as markdown plus summary metadata.
- [x] Diagnosis results are reused when the same product snapshot has already been analyzed.
- [x] A fallback diagnosis path exists when OpenAI-compatible AI output is unavailable.
- [x] Diagnosis output is normalized into `Observed`, `Evidence`, `Suspected friction`, and `First fix to try`.
- [x] Web-triggered diagnosis snapshots include the behavior fields supported by the backend snapshot model.

### 5. Demo And Delivery Readiness

- [x] The repo can seed a repeatable demo shop at `demo.myshopify.com`.
- [x] Demo seed data includes product behavior, priority-board inputs, product analysis inputs, and ready-made diagnosis cards.
- [x] The demo tells three fixed stories: a size-confidence Leaker, a media/trust Leaker, and a Hidden Winner.
- [x] The web app defaults missing or invalid analytics windows to `24h`.
- [x] Request tracing propagates `X-SKU-Lens-Request-Id` across server, web, and storefront flows.
- [x] Browser-side debug logging is intentionally silent by default and can be enabled manually with `localStorage['sku-lens:debug'] = '1'`.

## Product Gaps To Close Next

- [ ] Improve storefront component labeling so AI can reason about real theme sections instead of generic or theme-specific component ids.
- [ ] Replace the raw JSON/POST-only OAuth callback handling with a merchant-friendly browser install, post-install, and onboarding flow inside the embedded app.
- [ ] Add a merchant-visible integration health check that confirms tracker install, webhook connectivity, recent data arrival, and event coverage by funnel step.
- [ ] Add trend context for board entries so merchants can see whether a product is newly flagged, worsening, or improving.
- [ ] Add diagnosis freshness, history, and lightweight recommendation status so merchants can track what changed after a fix.
- [ ] Add cautious impact estimates only after funnel coverage and order attribution are strong enough, starting with directional upside/downside instead of precise revenue claims.
- [ ] Move from day-bucket windows to exact rolling behavioral windows if merchants need stricter `24h` semantics.

## Roadmap

### Near-Term

- [ ] Improve component labeling and PDP section detection in the storefront tracker.
- [ ] Add integration health and event coverage status to the board experience.
- [ ] Add trend labels for priority cards, such as `New`, `Worsening`, or `Improving`.
- [ ] Add diagnosis freshness and explicit re-run controls on product detail.
- [ ] Tighten low-data card copy so `Weak signal`, `Insufficient data`, and `Tracking issue` states stay actionable without overclaiming.

### Mid-Term

- [ ] Build a merchant-friendly install, post-install, and onboarding flow for the embedded app.
- [ ] Store diagnosis history so merchants can see whether a PDP improved after page changes.
- [ ] Add a lightweight recommendation status for each diagnosis: `New`, `Planned`, `Testing`, `Implemented`, and `Improved`.
- [ ] Add cautious directional impact estimates once the event model is reliable enough.
- [ ] Add exact rolling-window analytics if the day-bucket approximation becomes misleading in production use.

### Long-Term

- [ ] Add improvement detection so the product can show when a prior recommendation appears to have worked.
- [ ] Benchmark products against category peers and product cohorts, not only against one in-store benchmark.
- [ ] Expand Winners / Leakers logic beyond single PDPs into collection placement and merchandising opportunities.
- [ ] Add batch diagnosis for many products while keeping the board as the primary prioritization surface.
- [ ] Add agency or multi-store views only after the single-store Winners / Leakers loop is strong.

## Recommended Priority Order

1. Improve tracker component labeling and integration health so the board's evidence is easier to trust.
2. Add trend, freshness, and status signals around the existing priority-card loop.
3. Build merchant-friendly install and onboarding so the current product can be used outside local/demo flows.
4. Add history and improvement detection after merchants can reliably act on recommendations.
5. Add cautious impact estimates only after coverage, attribution, and history are strong enough.
