# SKU Lens

Daily Decision Board for Shopify Products

SKU Lens helps merchants decide which products to promote, which products to fix,
why each product was flagged, and what first action to try next. The first screen
centers on `Today's product priorities`: two Leakers with shopper drop-off evidence
and one Hidden Winner with high intent but limited exposure. Priority selection is
score-driven, while the merchant-facing suspected friction and first fix are
generated from the same AI diagnosis chain used on the product detail page when
OpenAI-compatible credentials are configured.

## Apps

Self-hosted services, built and deployed by us.

- `apps/server`: FastAPI + SQLModel APIs, browser Shopify install/OAuth callback, onboarding status, ingest pipeline, integration health, recommendation feedback, internal card review, diagnosis, and Celery worker runtime.
- `apps/web`: Embedded Shopify admin app built with Remix + Vite + Polaris. The shell publishes Shopify App Bridge metadata, defaults missing or invalid `window` params to `24h`, loads onboarding and integration health, shows readiness-aware board states, and loads product diagnosis asynchronously after first paint with freshness, manual re-run controls, and lightweight recommendation feedback.

## Extensions

Shopify platform extensions, built by Shopify CLI and deployed to Shopify infrastructure via `shopify app deploy`.

- `extensions/theme`: Theme App Extension assets for storefront DOM-experience tracking. The shipped tracker batches `product_impression`, `product_click`, `component_impression`, `component_click`, `media_interaction`, `variant_intent`, and `engage` events, maps common PDP sections to stable component labels, then posts them to `/ingest/events` with per-visitor and per-session identifiers.
- `extensions/web-pixel`: Shopify Web Pixel extension for standard Shopify customer events. It subscribes to product, cart, checkout, collection, search, and page events, then posts normalized batches to `/ingest/pixel-events`.

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
- Persist raw timestamps in UTC, but keep each shop's IANA timezone on `shop_installations`. SDK DOM and Shopify Pixel ingestion, daily rollups, and analytics windows should resolve `stat_date` against the shop-local calendar day rather than the server's UTC date.
- Shopify OAuth installation is also responsible for refreshing the persisted shop timezone. Normalize Shopify's `iana_timezone`, store it on `shop_installations`, and recompute rollup cursors when the timezone changes.
- `init_db()` reconciles additive `shop_installations` and `recommendation_feedback` columns and widens legacy `product_diagnoses.report_markdown` storage so older MySQL/SQLite dev volumes can pick up timezone, rollup metadata, feedback board context, and longer diagnosis text on startup. If your local schema drifts beyond those compatibility fixes, reset it explicitly with `docker compose down -v`.
- Celery Beat schedules the due-shop scanner every 60 seconds. The scanner decides whether a shop has crossed into a new day from `next_rollup_at_utc`, then backfills each missing local day through yesterday instead of assuming the process started near `00:00`.
- Domain errors such as diagnosis lookup failures, ingest auth failures, invalid Shopify shop domains, invalid OAuth state, and invalid Shopify OAuth callbacks are translated to HTTP responses centrally in `main.py`.
- Browser install starts at `GET /shopify/oauth/start?shop=<shop>.myshopify.com`, validates state in `GET /shopify/oauth/callback`, and redirects to `/onboarding` in the embedded web app. The older `POST /shopify/oauth/callback` remains a compatibility/test entrypoint.
- Onboarding status lives at `GET /api/onboarding/status?shop_id=<shop>&window=24h` and returns the public token, Theme SDK ingest endpoint, App Embed deep link, integration health, last raw event, and setup checklist. Shopify OAuth also creates or updates the app pixel settings with the Pixel ingest endpoint, public token, and shop domain.
- Order facts come from the Shopify `orders/create` webhook at `POST /shopify/webhooks/orders/create`. Web Pixel `checkout_completed` remains a journey event, while daily `orders` are rolled up from order webhook events.
- Recommendation feedback is append-only through `POST /api/recommendation-feedback` with `will_try`, `not_useful`, `already_fixed`, or `remind_later`. Priority-board submissions should include `board_date`, `window_start_date`, `window_end_date`, `card_rank`, and a small `context` snapshot so later analysis can group feedback by the exact daily board card that was shown.
- Internal card review is gated by `SKU_LENS_INTERNAL_REVIEW=1` and exposed at `GET /api/internal/card-review`; keep it off for normal merchant-facing environments.
- Application logs use standard Python `logging` configured through `logging.basicConfig(...)`. Keep server-side logs on ordinary `logger.info(...)`, `logger.warning(...)`, and `logger.exception(...)` calls instead of custom wrappers or ad hoc `print(...)`.
- Uvicorn access logs are intentionally disabled in the Python dev entrypoints. Treat the application log lines keyed by `request_id` and `job_id` as the canonical request trace.
- FastAPI, worker jobs, Remix server fetches, and the storefront tracker all propagate `X-SKU-Lens-Request-Id` when available. Celery dispatch uses `job_id` as `task_id` so server enqueue logs and worker processing logs can be correlated.
- The Remix loaders and resource routes default analytics and diagnosis requests to `24h` when `window` is missing or invalid; preserve the supported `24h`, `7d`, and `30d` values end-to-end.
- Current analytics windows use shop-local calendar-day buckets; `24h` is not an exact rolling 24-hour lookback.
- Priority cards are selected from score-ranked product statistics: up to two Leakers and one Hidden Winner. When a real `AI_API_KEY` is configured, the selected cards reuse the AI diagnosis prompt to produce the card-level `suspected_friction` and `first_fix`; if AI is unavailable, rule-based copy remains the fallback.
- Browser-side logs stay silent by default. To inspect `apps/web` browser polling or `extensions/theme` tracker behavior locally, set `localStorage['sku-lens:debug'] = '1'` before reproducing the flow.

## Runtime Compose

The root `docker-compose.yml` is the shared runtime stack for production and local production-like testing. It builds immutable images from the root `Dockerfile`: the `server`, `worker`, and `worker-beat` services share the Python image, while `web` uses the Node/Remix image.

1. Copy `.env.example` to `.env`.
2. For local production-like testing, keep `SKU_LENS_ENV=local`, `SHOPIFY_APP_URL=http://localhost:3000`, and `SHOPIFY_WEBHOOK_BASE_URL=http://localhost:8000`.
3. For production, set `SKU_LENS_ENV=production`, use strong URL-safe MySQL passwords, set real Shopify credentials, and use public HTTPS values for `SHOPIFY_APP_URL` and `SHOPIFY_WEBHOOK_BASE_URL`.
4. Validate the stack with `docker compose --env-file .env config`.
5. Build and start it with `docker compose up --build -d`.

Runtime state is bind-mounted by default:

- MySQL data: `${SKU_LENS_DATA_DIR:-./var/data}/mysql`
- Redis data: `${SKU_LENS_DATA_DIR:-./var/data}/redis`
- Celery Beat schedule: `${SKU_LENS_DATA_DIR:-./var/data}/celerybeat`

Those paths are ignored by git. Rebuilding images does not remove them, and `docker compose down -v` does not delete bind-mounted files under `var/`; remove those directories explicitly only when you want a full data reset.

Services started by Compose:

- `mysql`: MySQL 8.4, private to the Compose network
- `redis`: Redis 7.4 with append-only persistence, private to the Compose network
- `server`: FastAPI app on `${SERVER_BIND_HOST:-127.0.0.1}:${SERVER_PORT:-8000}`
- `worker`: Celery worker for rollup and diagnosis tasks
- `worker-beat`: single Celery Beat scheduler for due-shop rollup scans
- `web`: Remix production server on `${WEB_BIND_HOST:-127.0.0.1}:${WEB_PORT:-3000}`

Useful commands:

- `docker compose --env-file .env.example config`: validate the template values
- `docker compose --env-file .env config`: validate the active environment
- `docker compose up --build -d`: build and start everything in the background
- `docker compose ps --all`: inspect service status and health
- `docker compose logs -f web server worker worker-beat`: follow app logs
- `docker compose restart worker worker-beat`: restart Celery processes after Python task or schedule changes
- `docker compose down`: stop the stack
- `docker compose down -v`: stop the stack and remove Docker-managed volumes; bind-mounted data under `${SKU_LENS_DATA_DIR:-./var/data}` remains in place

When running behind an existing reverse proxy or platform router, keep the Compose port bindings on `127.0.0.1` and route:

- `/api/*`, `/ingest/*`, and `/shopify/*` to `http://127.0.0.1:${SERVER_PORT:-8000}`
- all other paths to `http://127.0.0.1:${WEB_PORT:-3000}`

The proxy must preserve the original request path. Do not strip `/api`, `/ingest`, or `/shopify`.

Health endpoints:

- Backend: `GET /api/healthz`
- Web: `GET /healthz`

For a minimal MySQL backup, run this from the host after setting the same `.env` values used by Compose:

```bash
docker compose exec mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > sku_lens_backup.sql
```

Application services write logs to stdout and stderr only. Docker keeps short local history with the `json-file` driver and log rotation from `docker-compose.yml`; production log retention and alerts should be handled by a host-level agent such as Vector, Fluent Bit, Promtail, or Filebeat collecting Docker container logs and forwarding them to your logging backend.

## Bare-Metal Development

1. Start MySQL and Redis outside the runtime Compose stack, or add a temporary local-only Compose override that publishes `3306` and `6379`.
2. Install Python deps with `uv sync --directory apps/server --extra dev`.
3. Install frontend deps with `pnpm install`.
4. Copy `.env.example` to `.env` and fill in Shopify credentials plus OpenAI-compatible AI credentials when needed.
5. Run the API with `uv run --directory apps/server sku-lens-server`.
6. Run the Celery worker with `uv run --directory apps/server celery --app celery_app:celery_app worker --loglevel INFO --queues sku-lens:rollups,sku-lens:diagnoses`.
7. Run the single Celery Beat scheduler with `uv run --directory apps/server celery --app celery_app:celery_app beat --loglevel INFO`.
8. Seed repeatable demo data with `uv run --directory apps/server sku-lens-seed-demo`.
9. Run the admin app with `pnpm dev`.

`SHOPIFY_API_KEY` must be set so the embedded admin shell can publish the App Bridge meta tag and build the App Embed activation link. `SHOPIFY_API_SECRET` is used for Shopify OAuth callback and webhook HMAC verification. `SHOPIFY_SCOPES` must include `read_orders` for order webhooks plus `write_pixels` and `read_customer_events` so OAuth can activate the app pixel. `SHOPIFY_WEBHOOK_BASE_URL` is the public backend base used for OAuth callback, webhook, and ingest URLs, while `SHOPIFY_APP_URL` is the embedded web app base used after install. `INGEST_SHARED_SECRET` plus `INGEST_TOKEN_TTL_SECONDS` control storefront ingest authentication. `AI_API_KEY`, `AI_MODEL`, and `AI_BASE_URL` configure the OpenAI-compatible Chat Completions provider for priority-card advice and product diagnosis reports; without a real `AI_API_KEY`, SKU Lens keeps the same score-based card selection and uses local fallback copy for merchant-facing advice. `DATABASE_URL`, `REDIS_URL`, and optional `CELERY_BROKER_URL` are used by bare-metal processes; the runtime Compose stack overrides them with container-internal service addresses. `SKU_LENS_LOG_LEVEL` defaults to `INFO` and controls both API and worker application logs. Set `SKU_LENS_INTERNAL_REVIEW=1` only when the gated card-review endpoint should be available.

The demo seed command targets the most recent OAuth-installed Shopify shop by default, so data appears in the embedded admin app for that development store. If no OAuth-installed shop exists, it uses the latest installation record; if no installation exists, it falls back to `sku-dev-uaop8pff.myshopify.com`. Pass `--shop-domain <store>.myshopify.com` to seed a specific store. The command replaces only the repo's `demo-*` products for that shop, preserves existing OAuth tokens unless you explicitly override them, includes stable PDP component labels such as `product_description`, `shipping_returns`, and `recommendations`, and pre-generates diagnosis cards so `http://localhost:3000/?shop=<store>.myshopify.com&window=24h` renders real board and product data immediately.

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

The repository is expected to stay warning-clean under those commands. Backend tests should not emit Python warnings, and the web app is already opted into the current Remix v3 future flags used by this repo. For stack checks, use `http://localhost:8000/api/healthz` as the backend health endpoint and `http://localhost:3000/healthz` as the web health endpoint.

## Storefront Performance Check

Run a weighted Lighthouse check across the three page types Shopify uses for storefront impact:

```bash
npm run perf:storefront -- \
  --home https://store.example.com \
  --product https://store.example.com/products/example \
  --collection https://store.example.com/collections/example
```
