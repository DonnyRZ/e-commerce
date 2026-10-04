#!/usr/bin/env bash
set -Eeuo pipefail

release_dir="$(cd "${1:-.}" && pwd)"
env_file="${MARKETPLACE_ENV_FILE:-/etc/marketplace/marketplace.env}"
compose=(docker compose --env-file "$env_file" -f "$release_dir/deploy/production/docker-compose.yml")

echo "Preparing the persistent admin notification key..."
"${compose[@]}" --profile migration run --rm --build migrate python scripts/ensure_admin_push_keys.py

echo "Running production migrations before starting application containers..."
"${compose[@]}" --profile migration run --rm --build migrate

current="$("${compose[@]}" --profile migration run --rm migrate alembic current 2>/dev/null | tail -n 1 | awk '{print $1}' | tr -d '\r')"
head="$("${compose[@]}" --profile migration run --rm migrate alembic heads 2>/dev/null | tail -n 1 | awk '{print $1}' | tr -d '\r')"
if [[ -z "$current" || -z "$head" || "$current" != "$head" ]]; then
  echo "Migration verification failed: current=$current head=$head" >&2
  exit 1
fi

# The public host Nginx and the storefront gateway both receive browser
# uploads. Install the versioned host config before traffic is switched so
# their CMS media limits stay aligned across releases.
nginx_source="$release_dir/deploy/production/nginx/shanicantik.com.https.conf"
if [[ -f "$nginx_source" && -d /etc/nginx/sites-available ]]; then
  install -m 0644 "$nginx_source" /etc/nginx/sites-available/shanicantik.com
  nginx -t
  systemctl reload nginx
fi

echo "Migration verified at $current. Starting application containers..."
"${compose[@]}" up -d --build
"${compose[@]}" ps
