# VPS deployment runbook — MUSLIMAH CANTIK

Target: `/var/www/marketplace`, `https://shanicantik.com`.

This runbook deliberately keeps `junix.tech` and `/var/www/junix` separate. The
Marketplace Compose file runs only `backend`, `frontend`, and `redis`; PostgreSQL
is native on the host and is shared by database/role, never by a public port.

## Release layout

```text
/var/www/marketplace/
├── releases/<git-sha>/
├── current -> releases/<git-sha>/
└── shared/acme/

/var/lib/marketplace/media/
/etc/marketplace/marketplace.env  # chmod 600
```

Deploy only a validated commit/tag. Do not copy a dirty development tree into a
production release.

## Native PostgreSQL migration order

1. Confirm the existing `shared-postgres` container and `junix` database are healthy.
2. Create a custom dump of `junix` and a globals/roles dump, and copy the backup off-server.
3. Install native PostgreSQL 16 on an alternate port (5433) while the old container remains on 5432.
4. Restore `junix` to native PostgreSQL and verify its tables and application connection.
5. Create a separate `marketplace` database and `marketplace` login role. Never run Marketplace migrations against `junix`.
6. Allow PostgreSQL only from localhost and the Marketplace Docker subnet (`172.30.0.0/24`, after collision check). Do not open 5432 publicly.
7. Deploy and validate Marketplace against native PostgreSQL on its alternate port first if needed.
8. During a maintenance window, stop the old container, move native PostgreSQL to 5432, update the env file, and restart only the Marketplace backend.
9. Keep the old PostgreSQL container volume and verified backups until the rollback window has passed.

## Application deployment

From `/var/www/marketplace/current`:

```bash
docker compose -f deploy/production/docker-compose.yml config
docker compose -f deploy/production/docker-compose.yml up -d redis
docker compose -f deploy/production/docker-compose.yml --profile migration run --rm migrate
docker compose -f deploy/production/docker-compose.yml up -d backend frontend
docker compose -f deploy/production/docker-compose.yml ps
curl --fail http://127.0.0.1:8080/api/health
curl --fail http://127.0.0.1:8080/api/ready
```

The production backend command starts Uvicorn directly. Alembic is intentionally
run by the one-shot `migrate` service and not on every backend restart.

## Required production environment

Copy `deploy/production/marketplace.env.example` to
`/etc/marketplace/marketplace.env`, fill the Click test credentials, SMTP
credentials, database password, and operator bootstrap values required by the
application, then run:

```bash
chown root:root /etc/marketplace/marketplace.env
chmod 600 /etc/marketplace/marketplace.env
```

`CLICK_MODE=test` is required during certification. Change it to `production`
only after prepare, complete, refund, and reconciliation have passed.

## Nginx and HTTPS

1. Create `/var/www/marketplace/shared/acme`.
2. Install `deploy/production/nginx/shanicantik.com.http.conf` as a separate site.
3. Run `nginx -t && systemctl reload nginx`.
4. Verify `A shanicantik.com -> 187.124.138.79` and `www` resolution.
5. Obtain the certificate for both names with Certbot.
6. Replace the temporary site with `shanicantik.com.https.conf`.
7. Run `nginx -t && systemctl reload nginx` again.

The canonical host is `https://shanicantik.com`; `www` redirects to it.

## Bootstrap and smoke test

After `/api/ready` is healthy, seed exactly one operator account, then seed the
catalog and CMS using the repository's backend scripts. Confirm that no seller
account or seller route is public. Test `/`, `/shop`, `/login`, `/admin`, mobile
navigation, catalog, inventory, orders, CMS, local media persistence, guest and
authenticated checkout, and the Click test callbacks.

## Backup and rollback

Before and after migration, create PostgreSQL custom-format and globals backups.
Back up `/var/lib/marketplace/media` and copy backups outside the VPS. Application
rollback is a symlink switch to the previous release followed by a Compose rebuild
and health check. Database rollback uses a verified backup restore, not Alembic
downgrade.

Only ports 22, 80, and 443 should be publicly reachable. Redis, backend,
PostgreSQL, and the frontend's 8080 listener remain private.
