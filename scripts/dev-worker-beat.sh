#!/bin/sh
set -eu

cd /workspace
uv sync --directory apps/server --extra dev

exec ./apps/server/.venv/bin/celery \
  --app celery_app:celery_app \
  beat \
  --loglevel "${SKU_LENS_LOG_LEVEL:-INFO}"
