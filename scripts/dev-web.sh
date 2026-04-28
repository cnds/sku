#!/bin/sh
set -eu

cd /workspace
pnpm install --frozen-lockfile

cd /workspace/apps/web
exec pnpm exec vite dev --host 0.0.0.0 --port 3000
