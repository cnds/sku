# SKU Lens Roadmap

> This file is the single source of truth for SKU Lens product scope and roadmap.
> When priorities change, update this file by overwriting the current plan instead of appending a changelog.

## How To Maintain This Plan

- Mark a capability as `[x]` only when it is already usable in the current repo through the shipped UI, API, worker flow, demo flow, or extension.
- Keep a capability as `[ ]` if it is still partial, implied by the architecture, or only desirable for the future.
- Treat `[x]` as "exists in the repo today", not automatically "merchant-ready end to end", unless the line says so explicitly.
- Keep merchant-readiness risk visible even when the underlying feature is implemented. A feature is not proven merchant-ready until a real shop can install it, generate enough trustworthy data, understand the result, and act on it without developer help.
- Keep the product language centered on the Winners / Leakers daily decision board. Do not broaden the plan into a generic analytics dashboard, CRO suite, or AI operator unless that scope is explicitly chosen later.

## Product Positioning

SKU Lens is a daily decision board for Shopify products.

It tells merchants which products to promote, which products to fix, why each product was flagged, and what first action to take next.

The core product promise is:

1. Show today's highest-priority product decisions.
2. Identify hidden Winners that deserve more exposure.
3. Identify Leakers with strong evidence of shopper drop-off.
4. Explain the observed signal, supporting evidence, suspected friction, and first fix to try.

## Strategic Product Principles

- SKU Lens' moat is SKU-level action priority, not AI breadth or analytics depth.
- The experience should reduce merchant judgment cost. It should not ask merchants to explore more data before they understand what to do today.
- The board should present a small number of high-confidence product decisions, not a long list of possible optimizations.
- Competitive positioning should be judged by cognitive load: how much data a merchant must inspect, whether the product says which SKU matters today, whether the recommendation has behavior evidence, whether it gives one first action, and whether it avoids suggestion overload.
- The long-term value is not only giving recommendations. It is learning which recommendations merchants act on and, later, which recommendations appear to improve product progression.

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
- [x] PDP component tracking maps common storefront sections into stable labels such as `product_media`, `buy_box`, `review_tab`, `size_chart`, `product_description`, `shipping_returns`, `product_details`, and `recommendations`, while keeping section/class hints for debugging.
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
- [x] Current windows use shop-local calendar-day buckets; `24h` is not an exact rolling 24-hour lookback.

### 3. Daily Decision Board

- [x] SKU Lens has an embedded Shopify admin app as the primary merchant-facing surface.
- [x] The home page is centered on `Today's product priorities`.
- [x] The first screen uses up to 3 priority cards: 2 Leakers and 1 Hidden Winner when data supports that mix.
- [x] `Winners` are framed as `High intent, underexposed`.
- [x] `Leakers` are framed as `High attention, weak progression`.
- [x] Merchants can switch the board window across `24h`, `7d`, and `30d`.
- [x] Priority cards expose `Ready`, `Weak signal`, `Insufficient data`, and `Tracking issue`.
- [x] Priority cards expose trend context: `New`, `Worsening`, `Improving`, or `Stable`.
- [x] Each priority card shows why the product was flagged, the drop-off or opportunity step, supporting evidence, suspected friction, and first fix.
- [x] Low-data priority cards avoid confident PDP-friction claims and frame `Weak signal`, `Insufficient data`, and `Tracking issue` as watch, traffic, or event-coverage states.
- [x] The board shows merchant-visible integration health for tracker installation, storefront events, PDP views, component coverage, add-to-cart coverage, and order/webhook coverage.
- [x] The board separates no-install, no-raw-event, no-PDP-view, low-traffic, and partial-coverage readiness states before promising priority cards.
- [x] Merchants can drill from a priority card or secondary product list into a product analysis page.
- [x] Merchants can submit lightweight feedback on a priority card: `I will try this`, `Not useful`, `Already fixed`, or `Remind me later`.
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
- [x] Diagnosis responses expose generated freshness and can be manually re-run with `force=true` for the same snapshot.
- [x] A fallback diagnosis path exists when OpenAI-compatible AI output is unavailable.
- [x] Diagnosis output is normalized into `Observed`, `Evidence`, `Suspected friction`, and `First fix to try`.
- [x] Web-triggered diagnosis snapshots include the behavior fields supported by the backend snapshot model.

### 5. Demo And Delivery Readiness

- [x] The repo can seed a repeatable demo shop at `sku-dev-uaop8pff.myshopify.com`.
- [x] Demo seed data includes product behavior, priority-board inputs, product analysis inputs, and ready-made diagnosis cards.
- [x] The demo tells three fixed stories: a size-confidence Leaker, a media/trust Leaker, and a Hidden Winner.
- [x] Demo component data includes stable PDP labels for description, shipping/returns, and recommendations.
- [x] The web app defaults missing or invalid analytics windows to `24h`.
- [x] Request tracing propagates `X-SKU-Lens-Request-Id` across server, web, and storefront flows.
- [x] Browser-side debug logging is intentionally silent by default and can be enabled manually with `localStorage['sku-lens:debug'] = '1'`.
- [x] Browser install, post-install onboarding, and App Embed activation guidance exist in the repo through the backend OAuth start/callback flow and web `/onboarding` route.
- [x] Gated internal card review can inspect raw event counts, aggregate evidence, derived signal, AI summary, and final merchant-facing copy.
- [x] Merchant-test demo, listing, landing, competitor narrative, and theme validation support materials live in `docs/merchant-test/`.

## Product Gaps To Close Next

- [x] Replace the raw JSON/POST-only OAuth callback handling with a merchant-friendly browser install, post-install, and onboarding flow inside the embedded app.
- [x] Build first-run, no-data, insufficient-data, and tracking-issue states that explain what SKU Lens needs before it can produce priority cards.
- [x] Validate tracker event coverage and component labeling across common Shopify themes before treating the board as merchant-ready.
- [x] Add an internal card quality review mode for inspecting raw evidence, derived signal, AI summary, and final merchant-facing card copy.
- [x] Collect lightweight merchant feedback on each recommendation, starting with `I will try this`, `Not useful`, `Already fixed`, and `Remind me later` instead of a full task workflow.
- [x] Create a concise demo, landing, App Store, and competitor narrative around lower merchant cognitive load: `2 Leakers + 1 Hidden Winner`, with one reason and one first action per card.
- [ ] Store diagnosis history and add recommendation status after lightweight feedback proves that merchants understand and act on recommendations.
- [ ] Add cautious impact estimates only after funnel coverage and order attribution are strong enough, starting with directional upside/downside instead of precise revenue claims.
- [ ] Move from day-bucket windows to exact rolling behavioral windows if merchants need stricter `24h` semantics.

## Merchant-Test Readiness

- Repository-verified means the code, tests, and docs exist in this repo. It does not mean a live merchant pilot or Shopify App Store review has completed.
- [x] A merchant can install SKU Lens without developer help through the browser OAuth start/callback flow when Shopify app URLs are configured.
- [x] A merchant can confirm tracker status, storefront events, PDP views, component coverage, add-to-cart coverage, and order/webhook coverage inside the embedded app.
- [x] A merchant can see first raw data within the same day when traffic exists, without promising that a confident priority card will appear immediately.
- [x] Empty, low-data, and tracking-issue states explain why priority cards are missing and what the merchant should check next.
- [x] The tracker and component labeling are tested against common Shopify themes such as Dawn, Refresh, Sense, Impulse, Prestige, and Debutify.
- [x] Internal review can trace why a SKU became a Winner or Leaker from raw evidence to derived signal to final card copy.
- [x] Merchants can give lightweight action feedback before SKU Lens adds heavier recommendation-status workflows.
- [x] Demo, landing, and App Store surfaces can explain the product as "3 product decisions today" without needing a feature checklist or metric dashboard.

## Recommendation And Outcome Loop

- Phase 1: collect lightweight action feedback only: `I will try this`, `Not useful`, `Already fixed`, and `Remind me later`.
- Phase 2: add recommendation history and manual status once feedback shows merchants understand the cards: `New`, `Planned`, `Testing`, and `Implemented`.
- Phase 3: add automatic outcome verification only after history, action signals, traffic quality, and event coverage are strong enough to avoid false attribution.
- Early outcome language should stay cautious, such as "products marked as implemented showed improved progression after the fix". Do not claim exact revenue or conversion lift until attribution is reliable.

## Roadmap

### Near-Term

- [x] Improve component labeling and PDP section detection in the storefront tracker.
- [x] Add integration health and event coverage status to the board experience.
- [x] Add trend labels for priority cards, such as `New`, `Worsening`, or `Improving`.
- [x] Add diagnosis freshness and explicit re-run controls on product detail.
- [x] Tighten low-data card copy so `Weak signal`, `Insufficient data`, and `Tracking issue` states stay actionable without overclaiming.

### Merchant-Test Readiness

- [x] Build merchant-friendly install, post-install, and onboarding for the embedded app.
- [x] Improve first-run, no-data, insufficient-data, and tracking-issue states so new merchants know what data is missing.
- [x] Run a theme compatibility and event coverage validation pass for the storefront tracker.
- [x] Add internal card quality review for priority-card selection, evidence, AI summary, and final copy.
- [x] Add lightweight recommendation feedback before adding full recommendation lifecycle status.
- [x] Package the demo, landing, App Store, and competitor narrative around low cognitive load: `2 Leakers + 1 Hidden Winner`.

### Mid-Term

- [ ] Store diagnosis history after merchants can reliably view and act on recommendations.
- [ ] Expand lightweight feedback into manual recommendation status only if it does not pull the product into full task management.
- [ ] Add cautious directional impact estimates once the event model is reliable enough.
- [ ] Add exact rolling-window analytics if the day-bucket approximation becomes misleading in production use.

### Long-Term

- [ ] Add improvement detection once history, merchant action signals, and traffic quality are strong enough to show when a prior recommendation appears to have worked.
- [ ] Benchmark products against category peers and product cohorts, not only against one in-store benchmark.
- [ ] Expand Winners / Leakers logic beyond single PDPs into collection placement and merchandising opportunities.
- [ ] Add batch diagnosis for many products while keeping the board as the primary prioritization surface.
- [ ] Add agency or multi-store views only after the single-store Winners / Leakers loop is strong.

## Recommended Priority Order

1. Run a real merchant pilot to validate the repository-verified install, onboarding, tracker, feedback, and review surfaces with live traffic.
2. Store diagnosis history and add lightweight action status only after merchants can reliably act on recommendations.
3. Add cautious impact estimates only after coverage, attribution, and history are strong enough.
4. Add exact rolling behavioral windows if the day-bucket `24h` approximation becomes misleading in production.
5. Add improvement detection once history, merchant action signals, and traffic quality are strong enough.
