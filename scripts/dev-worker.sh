#!/bin/sh
set -eu

cd /workspace
uv sync --directory apps/server --extra dev

exec ./apps/server/.venv/bin/sku-lens-worker
