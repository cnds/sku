# SKU Lens

AI Product Performance Ranking

Use AI to rank Shopify PDPs into Red Board and Black Board, compare `24h` / `7d` / `30d`
windows, and generate diagnosis cards from funnel plus component engagement signals.

## Apps

- `apps/server`: FastAPI + SQLModel APIs, ingest pipeline, Shopify validation, and worker runtime.
- `apps/web`: Embedded Shopify admin app built with Remix + Vite + Polaris. The shell publishes Shopify App Bridge metadata, defaults missing or invalid `window` params to `24h`, and loads product diagnosis asynchronously after first paint.
- `apps/extension`: Theme App Extension assets for storefront tracking. The shipped tracker batches `impression`, `click`, `media`, `variant`, and `engage` events, then posts them to `/ingest/events` with per-visitor and per-session identifiers.

## Backend Runtime Conventions

- Redis is initialized once at app and worker startup. Queue producers should call `enqueue_json(...)` directly and should not thread `redis_url` through handlers or services.
- Database access in the FastAPI app is request-scoped. The HTTP middleware creates the `AsyncSession`, stores it in a `ContextVar`, commits on successful responses, and rolls back on errors.
- HTTP handlers that need post-commit queue work should register it through `request.state.after_commit_callbacks` and pass that callback collection down explicitly instead of passing the whole FastAPI `Request` into lower layers.
- Server-side handlers, services, and repositories should fetch the active session with `get_db_session()` instead of accepting a session or session factory parameter.
- Worker jobs should open a `db_session_context(session_factory)` at the job boundary and commit or roll back there, so service code stays aligned with the request path.
- Queue pushes that depend on database writes should be scheduled after commit, not before, to avoid workers seeing uncommitted state.
- A single ingest batch may resolve to multiple shop-local `stat_date` values. Keep the deduplicated `stat_dates` set through persist, rollup, and enqueue so cross-midnight batches schedule every affected day.
- Redis jobs are claimed into `:processing` queues and acknowledged or requeued explicitly; worker startup restores in-flight jobs before polling the normal queues.
- Persist raw timestamps in UTC, but keep each shop's IANA timezone on `shop_installations`. SDK/webhook ingestion, daily rollups, and analytics windows should resolve `stat_date` against the shop-local calendar day rather than the server's UTC date.
- Shopify OAuth installation is also responsible for refreshing the persisted shop timezone. Normalize Shopify's `iana_timezone`, store it on `shop_installations`, and recompute rollup cursors when the timezone changes.
- `init_db()` reconciles additive `shop_installations` columns and widens legacy `product_diagnoses.report_markdown` storage so older MySQL/SQLite dev volumes can pick up timezone, rollup metadata, and longer diagnosis text on startup. If your local schema drifts beyond those compatibility fixes, reset it explicitly with `docker compose down -v`.
- The worker should decide whether a shop has crossed into a new day from `next_rollup_at_utc`, then backfill each missing local day through yesterday instead of assuming the process started near `00:00`.
- Domain errors such as diagnosis lookup failures, ingest auth failures, and invalid Shopify OAuth callbacks are translated to HTTP responses centrally in `main.py`.
- Application logs use standard Python `logging` configured through `logging.basicConfig(...)`. Keep server-side logs on ordinary `logger.info(...)`, `logger.warning(...)`, and `logger.exception(...)` calls instead of custom wrappers or ad hoc `print(...)`.
- Uvicorn access logs are intentionally disabled in the Python dev entrypoints. Treat the application log lines keyed by `request_id` and `job_id` as the canonical request trace.
- FastAPI, worker jobs, Remix server fetches, and the storefront tracker all propagate `X-SKU-Lens-Request-Id` when available. Queue payloads also carry `job_id` so server enqueue logs and worker processing logs can be correlated.
- The Remix loaders and resource routes default analytics and diagnosis requests to `24h` when `window` is missing or invalid; preserve the supported `24h`, `7d`, and `30d` values end-to-end.
- Browser-side logs stay silent by default. To inspect `apps/web` browser polling or `apps/extension` tracker behavior locally, set `localStorage['sku-lens:debug'] = '1'` before reproducing the flow.

## Containerized Development

1. Copy `.env.example` to `.env` and fill in Shopify and Gemini credentials.
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
- `worker`: background queue processor
- `web`: Remix + Vite dev server on `localhost:3000`

Useful commands:

- `docker compose --env-file .env.example config`: validate the Compose configuration
- `docker compose up --build -d`: start everything in the background
- `docker compose ps --all`: inspect service status and health
- `docker compose logs -f web server worker`: follow app logs
- `docker compose restart worker`: restart the worker after Python code changes
- `docker compose down`: stop the stack
- `docker compose down -v`: stop the stack and remove Docker volumes for a full reset

The `server` and `web` services use source mounts for live development. The worker shares the same mounted code, but because it is a long-running loop you should restart it after Python changes. Compose intentionally keeps separate `.venv` volumes for `server` and `worker`.

## Bare-Metal Development

1. Start infrastructure with `docker compose up -d mysql redis`.
2. Install Python deps with `uv sync --directory apps/server --extra dev`.
3. Install frontend deps with `pnpm install`.
4. Copy `.env.example` to `.env` and fill in Shopify and Gemini credentials.
5. Run the API with `uv run --directory apps/server sku-lens-server`.
6. Run the worker with `uv run --directory apps/server sku-lens-worker`.
7. Seed repeatable demo data with `uv run --directory apps/server sku-lens-seed-demo`.
8. Run the admin app with `pnpm dev`.

`SHOPIFY_API_KEY` must be set so the embedded admin shell can publish the App Bridge meta tag. `SHOPIFY_API_SECRET` is used for Shopify OAuth callback and webhook verification, and `INGEST_SHARED_SECRET` plus `INGEST_TOKEN_TTL_SECONDS` control storefront ingest authentication. `SKU_LENS_LOG_LEVEL` defaults to `INFO` and controls both API and worker application logs.

The demo seed command upserts `demo.myshopify.com`, replaces the repo's `demo-*` products for that shop, and pre-generates diagnosis cards so `http://localhost:3000/?shop=demo.myshopify.com&window=24h` renders real dashboard and product data immediately.

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
