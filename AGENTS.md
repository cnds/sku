# Repository Guidelines

## Project Structure & Module Organization

- Repository root: `docker-compose.yml`, root `package.json`, `pnpm-workspace.yaml`, `.env.example`, and helper scripts in `scripts/` drive the monorepo workflows.
- `apps/server`: FastAPI backend. Python source lives directly in `apps/server/src` and is imported from that root (`from services.analysis import ...`). Tests live in `apps/server/tests`.
- `apps/web`: Shopify admin app built with Remix, Vite, and Polaris. App code is in `apps/web/app`; web tests live in `apps/web/tests`. The shell publishes the `shopify-api-key` meta tag and loads diagnosis data through Remix loaders/resource routes.
- `apps/extension`: Theme App Extension assets. Storefront tracking code is in `assets/sku-lens-tracker.js`; Liquid block config is in `blocks/sku-lens-tracker.liquid`. The tracker batches `impression`, `click`, `media`, `variant`, and `engage` events for `/ingest/events`.

Backend runtime boundaries:

- Redis is process-scoped. Initialize it at app/worker startup and use `job_queue.enqueue_json(...)` instead of passing `redis_url` down call chains.
- FastAPI database access is request-scoped through `db.get_db_session()`. The HTTP middleware owns session creation, automatic commit on successful responses, and rollback on errors.
- HTTP routes that enqueue follow-up work should use `request.state.after_commit_callbacks` and pass that callback collection down instead of passing FastAPI `Request` objects into services.
- Worker jobs should establish `db_session_context(session_factory)` at the job boundary and let lower layers consume `get_db_session()`.
- Redis jobs are claimed into `:processing` queues and acknowledged or requeued explicitly; keep the `claim_json(...)` / `acknowledge_claimed_json(...)` / `restore_claimed_json(...)` flow instead of switching back to one-pop consumers.
- Prefer raising domain errors from services and mapping them in `main.py` exception handlers instead of rebuilding ad hoc HTTP error branches inside controllers.
- Do not reintroduce session/session-factory constructor plumbing into handlers, services, or repositories unless a call path genuinely runs outside the request/job context.

Avoid committing generated output such as `build/`, `dist/`, `coverage/`, `node_modules/`, `__pycache__/`, local SQLite/db files, or local virtualenv state.

## Build, Test, and Development Commands

- `docker compose --env-file .env.example config`: render and validate the full dev stack before booting it.
- `docker compose up --build`: start the full containerized development stack (`mysql`, `redis`, `server`, `worker`, `web`).
- `docker compose ps --all`: inspect containerized service status.
- `docker compose up -d mysql redis`: start only MySQL and Redis for bare-metal development.
- `docker compose logs -f web server worker`: follow containerized app logs.
- `docker compose restart worker`: restart the worker after Python changes in containerized development.
- `docker compose down`: stop the containerized stack.
- `uv sync --directory apps/server --extra dev`: install Python 3.14 backend dependencies for bare-metal workflows.
- `uv run --directory apps/server sku-lens-server`: run the backend outside Docker.
- `uv run --directory apps/server sku-lens-worker`: run the worker outside Docker.
- `pnpm install`: install frontend dependencies for bare-metal workflows.
- `pnpm dev`: run the admin app outside Docker.
- `npm --prefix apps/web run test`: run web Vitest tests.
- `npm run typecheck`: run the web typecheck.
- `npm run build`: build the web app.
- `npm run perf:storefront -- --home <url> --product <url> --collection <url>`: run the storefront Lighthouse check.
- `uv run --directory apps/server --extra dev pytest tests -q -W default`: run backend tests with warnings enabled.
- `uv run --directory apps/server --extra dev ruff check src tests`: run backend Ruff.

## Coding Style & Naming Conventions

Use 4-space indentation in Python and standard TypeScript formatting in web code. Python files and functions use `snake_case`; React components use `PascalCase`; Remix route files follow Remix naming. The backend targets Python 3.14. Ruff enforces `ANN`, `I`, `N`, and `S` with a 120-character line limit. Do not reintroduce a nested Python package under `apps/server/src`.

When changing web code, assume the app runs with the enabled Remix v3 future flags in `apps/web/vite.config.ts` (`v3_fetcherPersist`, `v3_lazyRouteDiscovery`, `v3_relativeSplatPath`, `v3_singleFetch`, `v3_throwAbortReason`). Do not remove them just to silence warnings.

## Testing Guidelines

Backend tests use `pytest` in `apps/server/tests` as `test_*.py`. Web tests use `vitest` in `apps/web/tests`. Add or update regression tests with each behavior change. Keep test and build output warning-clean instead of filtering warnings away. For web work, pass both `npm --prefix apps/web run test` and `npm run typecheck`.

## Commit & Pull Request Guidelines

This branch has no established git history yet, so use short imperative commit subjects with a scope, for example `server: flatten src imports` or `web: update dashboard branding`. PRs should include:

- a brief summary of user-visible changes
- affected apps (`server`, `web`, `extension`)
- exact verification commands run
- screenshots for UI changes

## Security & Configuration Tips

Keep secrets in `.env` files only. `SHOPIFY_API_KEY` must be available so the admin shell can publish the App Bridge meta tag. `SHOPIFY_API_SECRET` backs Shopify OAuth callback and webhook HMAC verification; do not bypass those signature checks. `INGEST_SHARED_SECRET` is required for the backend and worker to start, and `INGEST_TOKEN_TTL_SECONDS` bounds accepted ingest timestamps. In local `.env`, keep host-facing URLs and connection strings on `localhost`; Docker Compose overrides container-internal service addresses. Do not store PII. Internal slugs such as `sku-lens`, queue names, and tracking headers are protocol identifiers; change them with cross-app updates.
