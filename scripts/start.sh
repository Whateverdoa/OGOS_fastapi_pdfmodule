#!/usr/bin/env bash
set -euo pipefail

# Determine sensible defaults
PORT="${PORT:-8000}"
WEB_CONCURRENCY_DEFAULT=1
if command -v nproc >/dev/null 2>&1; then
  # Cap workers at 2 for CPU-heavy PDF work unless overridden
  CPUS=$(nproc)
  if [ "$CPUS" -ge 2 ]; then
    WEB_CONCURRENCY_DEFAULT=2
  fi
fi
WEB_CONCURRENCY="${WEB_CONCURRENCY:-$WEB_CONCURRENCY_DEFAULT}"

exec gunicorn \
  --workers "${WEB_CONCURRENCY}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}" \
  --config /app/gunicorn_conf.py \
  main:app

