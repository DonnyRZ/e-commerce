# Deployment runbook

The application is a single-owner store: customers use the storefront, while the operator manages the catalog, orders, payments and CMS from `/admin`. There is no seller marketplace portal in the deployable route surface.

## Required production configuration

Set these values in the backend secret manager, never in Git:

- `APP_ENV=production`
- `DATABASE_URL` for PostgreSQL
- a unique `JWT_SECRET` with at least 32 characters
- explicit HTTPS `FRONTEND_URL`, `CORS_ORIGINS` and `TRUSTED_HOSTS`
- `SESSION_COOKIE_SECURE=true`; use `SESSION_COOKIE_SAMESITE=none` only when the frontend/API are truly cross-site
- `RATE_LIMIT_BACKEND=redis` and a private `REDIS_URL` shared by all API workers
- launch profile: use `CHECKOUT_ENABLED=false` until a payment method is selected and implemented
- `NOTIFICATION_PROVIDER=smtp` with working SMTP credentials
- persistent media storage: either `MEDIA_STORAGE=local` with an absolute `MEDIA_ROOT` mounted on a persistent volume, or optional S3-compatible storage with bucket, region, credentials and public/CDN base URL

The process validates this configuration during startup. `/api/ready` must return
HTTP 200 before traffic is routed to the service. While checkout is disabled, the
payment check is intentionally reported as `disabled`; checkout and order
creation are hard-blocked so the storefront and Admin Console can run without
creating orders or reserving stock.

## Release sequence

1. Build the backend and frontend images from the tagged commit.
2. Take a PostgreSQL backup using `ops/backup_postgres.sh` and verify that the artifact is readable.
3. Back up persistent media with `ops/backup_media.sh`. With local storage, copy the resulting archive off the server manually or to an existing free storage location; with S3, use bucket versioning/replication or the provider's object backup policy.
4. Run `alembic upgrade head` through the backend image. The single-owner migration must complete without duplicate-cart or duplicate-active-payment conflicts.
5. Bootstrap exactly one operator account with `seed_accounts.py`; set `STORE_OWNER_EMAIL` to that same email before running the catalog/CMS seeds.
6. Confirm `/api/ready`, login, Admin Console access, CMS publish/preview, media upload and email delivery in the staging environment. While checkout is disabled, also confirm the checkout-disabled screen and that no order/payment endpoint can create state.
7. Run the browser smoke flow: catalog → product → search → wishlist → cart → Admin/CMS. Run checkout only after a payment method is selected and implemented.
8. Route production traffic only after the applicable smoke flow and backup/restore drill pass.

## Operations

- Monitor structured request logs, `/api/health`, `/api/ready`, and any future payment integration error rates.
- Monitor Redis availability and rate-limit errors; readiness must fail if the shared limiter is unavailable.
- Schedule orphan-media cleanup in dry-run mode first: `python -m jobs.cleanup_orphan_media --dry-run`.
- Keep a tested restore command available: set `BACKUP_FILE` and `CONFIRM_RESTORE=YES` only after verifying the target database.
- Keep a tested media restore command available: set `MEDIA_BACKUP_FILE`, `MEDIA_ROOT` and `CONFIRM_RESTORE=YES` only after verifying the target directory.
- Never enable mock payment or notification flows, an ephemeral local media path or wildcard CORS in production. Local media is acceptable only when its volume is persistent and included in the backup/restore drill.

### Zero-extra-cost media profile

For a small single-operator store, use the server's existing persistent disk:

```dotenv
MEDIA_STORAGE=local
MEDIA_ROOT=/app/uploads
```

The Docker Compose profile already mounts `/app/uploads` to the `media_data` volume. This avoids a separate storage bill, but it is not disaster-proof by itself: run `ops/backup_media.sh` and keep a copy outside the server before releases and on a regular schedule.

## Local verification

With PostgreSQL, Redis and the API running, execute the repeatable smoke test:

```bash
SMOKE_ADMIN_EMAIL=operator@example.com \
SMOKE_ADMIN_PASSWORD='set-locally' \
python scripts/smoke_local.py
```
