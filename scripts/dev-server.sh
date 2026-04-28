#!/bin/sh
set -eu

cd /workspace
uv sync --directory apps/server --extra dev

exec ./apps/server/.venv/bin/uvicorn \
  --app-dir ./apps/server/src \
  main:create_app \
  --factory \
  --reload \
  --reload-dir ./apps/server/src \
  --host 0.0.0.0 \
  --port 8000

