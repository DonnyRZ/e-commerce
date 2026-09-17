# MUSLIMAH CANTIK

Single-owner commerce application for modest fashion and halal skincare.

The operating model is intentionally simple:

- customer-facing storefront for browsing, cart, checkout and order tracking;
- one internal Admin Console for catalog, inventory, orders, payments and CMS;
- no multi-seller onboarding, seller dashboard or seller API in the public application surface.

## Local development

### Docker Compose (recommended)

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). The API is available at [http://localhost:8000/api/ready](http://localhost:8000/api/ready).

### Manual

1. Copy `backend/.env.example` to `backend/.env` and set a local PostgreSQL URL.
2. Create a Python 3.12 environment and install `backend/requirements.txt`.
3. Run `alembic upgrade head` from `backend/`, then start `uvicorn server:app --reload`.
4. Run `npm ci` and `npm start` from `frontend/`.

For a repeatable local acceptance check, run `backend/scripts/smoke_local.py`
with `SMOKE_ADMIN_EMAIL` and `SMOKE_ADMIN_PASSWORD` set to the isolated test
operator credentials.

## Release documentation

- [Deployment runbook](docs/deployment.md)
- [Pre-deployment checklist](docs/pre-deployment-checklist.md)
- [PostgreSQL backup](ops/backup_postgres.sh)
- [PostgreSQL restore](ops/restore_postgres.sh)
- [Media backup](ops/backup_media.sh)
- [Media restore](ops/restore_media.sh)

Production readiness is fail-closed: the backend must have real payment, notification and persistent media configuration before `APP_ENV=production` can start serving traffic. For a zero-extra-cost launch, use `MEDIA_STORAGE=local` on a persistent volume and run the media backup script regularly; S3-compatible storage is optional.
