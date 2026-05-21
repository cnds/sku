# SKU Lens

Daily Decision Board for Shopify Products

SKU Lens helps merchants decide which products to promote, which products to fix,
why each product was flagged, and what first action to try next. The first screen
centers on `Today's product priorities`: two Leakers with shopper drop-off evidence
and one Hidden Winner with high intent but limited exposure.

## Apps

- `apps/server`: FastAPI + SQLModel APIs, browser Shopify install/OAuth callback, onboarding status, ingest pipeline, integration health, recommendation feedback, internal card review, diagnosis, and Celery worker runtime.
- `apps/web`: Embedded Shopify admin app built with Remix + Vite + Polaris. The shell publishes Shopify App Bridge metadata, defaults missing or invalid `window` params to `24h`, loads onboarding and integration health, shows readiness-aware board states, and loads product diagnosis asynchronously after first paint with freshness, manual re-run controls, and lightweight recommendation feedback.
- `apps/extension`: Theme App Extension assets for storefront tracking. The shipped tracker batches `impression`, `click`, `view`, `component_click`, `add_to_cart`, `media`, `variant`, and `engage` events, maps common PDP sections to stable component labels, then posts them to `/ingest/events` with per-visitor and per-session identifiers.

## Backend Runtime Conventions

- Celery uses Redis as its broker through `REDIS_URL`, or `CELERY_BROKER_URL` when an explicit broker override is needed. Queue producers should go through `services.job_dispatch` instead of direct Redis-list operations.
- Database access in the FastAPI app is request-scoped. The HTTP middleware creates the `AsyncSession`, stores it in a `ContextVar`, commits on successful responses, and rolls back on errors.
- HTTP handlers that need post-commit queue work should register it through `request.state.after_commit_callbacks` and pass that callback collection down explicitly instead of passing the whole FastAPI `Request` into lower layers.
- Server-side handlers, services, and repositories should fetch the active session with `get_db_session()` instead of accepting a session or session factory parameter.
- Worker jobs should open `tasks.runtime.task_session_context()` at the job boundary and commit or roll back there, so service code stays aligned with the request path and lower layers can keep using `get_db_session()`.
- Celery task definitions, task runtime state, async job handlers, and due-shop scheduling live in `apps/server/src/tasks`; keep `celery_app.py` focused on Celery app configuration, routes, queues, and beat schedule.
- Queue pushes that depend on database writes should be scheduled after commit, not before, to avoid workers seeing uncommitted state.
- A single ingest batch may resolve to multiple shop-local `stat_date` values. Keep the deduplicated `stat_dates` set through persist, rollup, and enqueue so cross-midnight batches schedule every affected day.
- Celery tasks use JSON payloads, `acks_late`, `reject_on_worker_lost`, and `worker_prefetch_multiplier=1`. Diagnosis generation and rollups retry with finite exponential backoff; exhausted diagnosis jobs are marked `failed` with a short error summary.
- Legacy Redis-list payloads under `sku-lens:rollups` or `sku-lens:diagnoses` are not consumed by the Celery worker; clear local Redis if stale development jobs matter after upgrading.
- Persist raw timestamps in UTC, but keep each shop's IANA timezone on `shop_installations`. SDK/webhook ingestion, daily rollups, and analytics windows should resolve `stat_date` against the shop-local calendar day rather than the server's UTC date.
- Shopify OAuth installation is also responsible for refreshing the persisted shop timezone. Normalize Shopify's `iana_timezone`, store it on `shop_installations`, and recompute rollup cursors when the timezone changes.
- `init_db()` reconciles additive `shop_installations` columns and widens legacy `product_diagnoses.report_markdown` storage so older MySQL/SQLite dev volumes can pick up timezone, rollup metadata, and longer diagnosis text on startup. If your local schema drifts beyond those compatibility fixes, reset it explicitly with `docker compose down -v`.
- Celery Beat schedules the due-shop scanner every 60 seconds. The scanner decides whether a shop has crossed into a new day from `next_rollup_at_utc`, then backfills each missing local day through yesterday instead of assuming the process started near `00:00`.
- Domain errors such as diagnosis lookup failures, ingest auth failures, invalid Shopify shop domains, invalid OAuth state, and invalid Shopify OAuth callbacks are translated to HTTP responses centrally in `main.py`.
- Browser install starts at `GET /shopify/oauth/start?shop=<shop>.myshopify.com`, validates state in `GET /shopify/oauth/callback`, and redirects to `/onboarding` in the embedded web app. The older `POST /shopify/oauth/callback` remains a compatibility/test entrypoint.
- Onboarding status lives at `GET /api/onboarding/status?shop_id=<shop>&window=24h` and returns the public token, ingest endpoint, App Embed deep link, integration health, last raw event, and setup checklist.
- Recommendation feedback is append-only through `POST /api/recommendation-feedback` with `will_try`, `not_useful`, `already_fixed`, or `remind_later`.
- Internal card review is gated by `SKU_LENS_INTERNAL_REVIEW=1` and exposed at `GET /api/internal/card-review`; keep it off for normal merchant-facing environments.
- Application logs use standard Python `logging` configured through `logging.basicConfig(...)`. Keep server-side logs on ordinary `logger.info(...)`, `logger.warning(...)`, and `logger.exception(...)` calls instead of custom wrappers or ad hoc `print(...)`.
- Uvicorn access logs are intentionally disabled in the Python dev entrypoints. Treat the application log lines keyed by `request_id` and `job_id` as the canonical request trace.
- FastAPI, worker jobs, Remix server fetches, and the storefront tracker all propagate `X-SKU-Lens-Request-Id` when available. Celery dispatch uses `job_id` as `task_id` so server enqueue logs and worker processing logs can be correlated.
- The Remix loaders and resource routes default analytics and diagnosis requests to `24h` when `window` is missing or invalid; preserve the supported `24h`, `7d`, and `30d` values end-to-end.
- Current analytics windows use shop-local calendar-day buckets; `24h` is not an exact rolling 24-hour lookback.
- Browser-side logs stay silent by default. To inspect `apps/web` browser polling or `apps/extension` tracker behavior locally, set `localStorage['sku-lens:debug'] = '1'` before reproducing the flow.

## Containerized Development

1. Copy `.env.example` to `.env` and fill in Shopify credentials plus OpenAI-compatible AI credentials when needed.
2. Sanity-check the stack definition with `docker compose --env-file .env.example config`.
3. Build and start the full development stack with `docker compose up --build`.
4. On the first boot, allow the `web` container time to finish `pnpm install` inside its Docker volumes before checking `localhost:3000`.
5. Open `http://localhost:3000` for the embedded admin app.
6. Use `http://localhost:8000` for direct API and webhook testing.

Keep the `.env` host values on `localhost`. Docker Compose overrides `DATABASE_URL`, `REDIS_URL`, and `SERVER_API_URL` inside the containers so the same `.env` can still be used for bare-metal workflows.

Services started by Compose:

- `mysql`: MySQL 8.4 on `localhost:3306`
- `redis`: Redis 7.4 on `localhost:6379`
- `server`: FastAPI app with reload on `localhost:8000`
- `worker`: Celery worker for rollup and diagnosis tasks
- `worker-beat`: single Celery Beat scheduler for due-shop rollup scans
- `web`: Remix + Vite dev server on `localhost:3000`

Useful commands:

- `docker compose --env-file .env.example config`: validate the Compose configuration
- `docker compose up --build -d`: start everything in the background
- `docker compose ps --all`: inspect service status and health
- `docker compose logs -f web server worker worker-beat`: follow app logs
- `docker compose restart worker worker-beat`: restart Celery processes after Python task or schedule changes
- `docker compose down`: stop the stack
- `docker compose down -v`: stop the stack and remove Docker volumes for a full reset

The `server` and `web` services use source mounts for live development. The Celery worker and Beat scheduler share the same mounted code, but restart them after Python task or schedule changes. Compose intentionally keeps separate `.venv` volumes for `server`, `worker`, and `worker-beat`.

## Bare-Metal Development

1. Start infrastructure with `docker compose up -d mysql redis`.
2. Install Python deps with `uv sync --directory apps/server --extra dev`.
3. Install frontend deps with `pnpm install`.
4. Copy `.env.example` to `.env` and fill in Shopify credentials plus OpenAI-compatible AI credentials when needed.
5. Run the API with `uv run --directory apps/server sku-lens-server`.
6. Run the Celery worker with `uv run --directory apps/server celery --app celery_app:celery_app worker --loglevel INFO --queues sku-lens:rollups,sku-lens:diagnoses`.
7. Run the single Celery Beat scheduler with `uv run --directory apps/server celery --app celery_app:celery_app beat --loglevel INFO`.
8. Seed repeatable demo data with `uv run --directory apps/server sku-lens-seed-demo`.
9. Run the admin app with `pnpm dev`.

`SHOPIFY_API_KEY` must be set so the embedded admin shell can publish the App Bridge meta tag and build the App Embed activation link. `SHOPIFY_API_SECRET` is used for Shopify OAuth callback and webhook verification. `SHOPIFY_WEBHOOK_BASE_URL` is the public backend base used for OAuth callback, webhook, and ingest URLs, while `SHOPIFY_APP_URL` is the embedded web app base used after install. `INGEST_SHARED_SECRET` plus `INGEST_TOKEN_TTL_SECONDS` control storefront ingest authentication. `AI_API_KEY`, `AI_MODEL`, and `AI_BASE_URL` configure the OpenAI-compatible Chat Completions provider for generated diagnosis reports; without a real `AI_API_KEY`, diagnosis generation uses the local fallback report. `REDIS_URL` is also the default Celery broker URL; set `CELERY_BROKER_URL` only if you need Celery to use a different Redis broker. `SKU_LENS_LOG_LEVEL` defaults to `INFO` and controls both API and worker application logs. Set `SKU_LENS_INTERNAL_REVIEW=1` only when the gated card-review endpoint should be available.

The demo seed command upserts `demo.myshopify.com`, replaces the repo's `demo-*` products for that shop, includes stable PDP component labels such as `product_description`, `shipping_returns`, and `recommendations`, and pre-generates diagnosis cards so `http://localhost:3000/?shop=demo.myshopify.com&window=24h` renders real board and product data immediately.

Merchant-test copy, demo flow, App Store draft, competitor narrative, and theme validation notes live in `docs/merchant-test/`. Those files document repository-verified readiness; they do not mean a live merchant pilot or Shopify App Store review has already completed.

## Verification

- `docker compose --env-file .env.example config`
- `docker compose up --build -d`
- `docker compose ps --all`
- `uv run --directory apps/server --extra dev pytest tests -q -W default`
- `uv run --directory apps/server --extra dev ruff check src tests`
- `npm --prefix apps/web run test`
- `npm run typecheck`
- `npm run build`

The repository is expected to stay warning-clean under those commands. Backend tests should not emit Python warnings, and the web app is already opted into the current Remix v3 future flags used by this repo. For stack checks, wait for the `web` logs to print the Vite ready message before probing `http://localhost:3000`, and use `http://localhost:8000/openapi.json` as the backend health endpoint.

## Storefront Performance Check

Run a weighted Lighthouse check across the three page types Shopify uses for storefront impact:

```bash
npm run perf:storefront -- \
  --home https://store.example.com \
  --product https://store.example.com/products/example \
  --collection https://store.example.com/collections/example
```
