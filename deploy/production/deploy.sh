#!/usr/bin/env bash
set -Eeuo pipefail

release_dir="$(cd "${1:-.}" && pwd)"
env_file="${MARKETPLACE_ENV_FILE:-/etc/marketplace/marketplace.env}"
compose=(docker compose --env-file "$env_file" -f "$release_dir/deploy/production/docker-compose.yml")

echo "Running production migrations before starting application containers..."
"${compose[@]}" --profile migration run --rm migrate

current="$("${compose[@]}" --profile migration run --rm migrate alembic current 2>/dev/null | tail -n 1 | tr -d '\r')"
head="$("${compose[@]}" --profile migration run --rm migrate alembic heads 2>/dev/null | tail -n 1 | awk '{print $1}' | tr -d '\r')"
if [[ -z "$current" || -z "$head" || "$current" != "$head" ]]; then
  echo "Migration verification failed: current=$current head=$head" >&2
  exit 1
fi

echo "Migration verified at $current. Starting application containers..."
"${compose[@]}" up -d --build
"${compose[@]}" ps
