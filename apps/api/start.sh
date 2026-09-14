#!/bin/sh
set -e

# Railway injects $PORT for services with public networking.
# Fall back to 8000 for local Docker runs.
APP_PORT="${PORT:-8000}"

# Presence-only check; never log values (secrets).
check_var() {
  name="$1"
  eval "val=\${$name:-}"
  if [ -n "$val" ]; then
    echo "[start] $name: set"
  else
    echo "[start] $name: MISSING"
  fi
}

echo "[start] binding uvicorn to 0.0.0.0:${APP_PORT} (PORT env=${PORT:+set})"
check_var COMPANIES_HOUSE_API_KEY
check_var ANTHROPIC_API_KEY
check_var CORS_ORIGINS

echo "[start] launching uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT}"
