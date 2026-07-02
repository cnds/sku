FROM python:3.14-slim AS server

ENV PATH="/workspace/apps/server/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/workspace/apps/server/src" \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

RUN python -m pip install --no-cache-dir --upgrade pip uv

COPY apps/server /workspace/apps/server
RUN uv sync --directory apps/server --frozen --no-dev

WORKDIR /workspace/apps/server/src
EXPOSE 8000

CMD ["uvicorn", "main:create_app", "--factory", "--no-access-log", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]


FROM node:22-bookworm-slim AS web-build

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:${PATH}"

WORKDIR /workspace

RUN corepack enable && corepack prepare pnpm@10.10.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json /workspace/
COPY apps/web/package.json /workspace/apps/web/package.json
COPY extensions/theme/package.json /workspace/extensions/theme/package.json
COPY extensions/web-pixel/package.json /workspace/extensions/web-pixel/package.json
RUN pnpm install --frozen-lockfile

COPY apps/web /workspace/apps/web
RUN pnpm --dir apps/web run build


FROM node:22-bookworm-slim AS web

ENV NODE_ENV=production \
    PORT=3000

WORKDIR /workspace

COPY --from=web-build /workspace/package.json /workspace/pnpm-lock.yaml /workspace/pnpm-workspace.yaml /workspace/
COPY --from=web-build /workspace/node_modules /workspace/node_modules
COPY --from=web-build /workspace/apps/web /workspace/apps/web

WORKDIR /workspace/apps/web
EXPOSE 3000

CMD ["npm", "run", "start"]
