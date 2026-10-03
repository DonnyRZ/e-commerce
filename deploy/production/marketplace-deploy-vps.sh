#!/usr/bin/env bash
set -Eeuo pipefail

sha="${1:-}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: marketplace-deploy <40-character-commit-sha>" >&2
  exit 2
fi
if [[ "$#" -ne 1 || "$EUID" -ne 0 ]]; then
  echo "This command must be run as root with one commit SHA." >&2
  exit 2
fi

root="/var/www/marketplace"
incoming="$root/incoming"
releases="$root/releases"
release="$releases/$sha"
archive="$incoming/$sha.tar.gz"
checksum="$archive.sha256"
env_file="/etc/marketplace/marketplace.env"
compose_file="deploy/production/docker-compose.yml"
previous=""

[[ -f "$env_file" ]] || { echo "Missing production environment file: $env_file" >&2; exit 1; }
[[ -f "$archive" && -f "$checksum" ]] || { echo "Release archive or checksum is missing." >&2; exit 1; }
mkdir -p "$incoming" "$releases"
(
  cd "$incoming"
  sha256sum --check --status "$sha.tar.gz.sha256"
)

if [[ -L "$root/current" ]]; then
  previous="$(readlink -f "$root/current" || true)"
elif [[ -e "$root/current" ]]; then
  echo "$root/current exists but is not a symlink; refusing to replace it." >&2
  exit 1
fi

if [[ ! -d "$release" ]]; then
  staging="$releases/.$sha.staging"
  rm -rf -- "$staging"
  install -d -o root -g root -m 0755 "$staging"
  tar --extract --gzip --file "$archive" --directory "$staging" --no-same-owner
  [[ -f "$staging/$compose_file" && -f "$staging/deploy/production/deploy.sh" ]] || {
    echo "Archive does not contain the production deployment files." >&2
    exit 1
  }
  mv -- "$staging" "$release"
fi

if [[ ! -f "$release/$compose_file" || ! -f "$release/deploy/production/deploy.sh" ]]; then
  echo "Release directory is incomplete: $release" >&2
  exit 1
fi

rollback_previous_release() {
  if [[ -n "$previous" && -f "$previous/$compose_file" ]]; then
    local previous_nginx="$previous/deploy/production/nginx/shanicantik.com.https.conf"
    if [[ -f "$previous_nginx" ]]; then
      install -m 0644 "$previous_nginx" /etc/nginx/sites-available/shanicantik.com || true
      nginx -t && systemctl reload nginx || true
    fi
    docker compose --env-file "$env_file" -f "$previous/$compose_file" up -d --build || true
  fi
}

if ! bash "$release/deploy/production/deploy.sh" "$release"; then
  echo "Release command failed; restoring the previous application version when available." >&2
  rollback_previous_release
  exit 1
fi

healthy=0
for _ in $(seq 1 24); do
  if curl --fail --silent --show-error --max-time 5 \
      -H 'Host: shanicantik.com' -H 'X-Forwarded-Proto: https' \
      http://127.0.0.1:8080/api/health >/dev/null \
    && curl --fail --silent --show-error --max-time 5 \
      -H 'Host: shanicantik.com' -H 'X-Forwarded-Proto: https' \
      http://127.0.0.1:8080/api/ready >/dev/null; then
    healthy=1
    break
  fi
  sleep 5
done

if [[ "$healthy" -ne 1 ]]; then
  echo "Health check failed; restoring the previous application version when available." >&2
  rollback_previous_release
  exit 1
fi

next_link="$root/.current-$sha"
ln -sfn "$release" "$next_link"
mv -Tf "$next_link" "$root/current"
rm -f -- "$archive" "$checksum"
echo "Deployed $sha successfully; current now points to $release."
