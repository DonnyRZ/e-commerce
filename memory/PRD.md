# MUSLIMAH CANTIK — PRD / Project Memory

## Original Problem Statement
Execute Controlled Execution Prompt V3 #1 — Repository Audit + Architecture Foundation only, per
01_EXECUTION_BOOTSTRAP.md and 02_MASTER_CONTEXT_V3.md (project constitution). No marketplace features.
Final product: full-stack multilingual (id/en/uz/ru) marketplace "MUSLIMAH CANTIK" (React + FastAPI +
MongoDB + Tailwind, modular monolith), IDR base currency, 3 departments (UNIQLO-style apparel, Women
Muslimah, Tropical Halal Skincare), roles customer/seller/admin, server-authoritative commerce.

## User Personas
- Customer (guest + registered, 4 languages, mobile-first)
- Seller (owns/manages own products, variants, stock, orders)
- Admin (catalog, orders, sellers, settings)

## Architecture (established 2026-09-09 — Milestone 0)
- Frontend: React 19 + react-router-dom 7 + Tailwind + shadcn/ui (`/app/frontend`), craco build.
  `src/i18n/index.js` — locale constants (id/en/uz/ru, fallback en).
- Backend: FastAPI modular monolith (`/app/backend`):
  - `config.py` — env-driven settings (APP_ENV, MONGO_URL, DB_NAME, CORS, BASE_CURRENCY=IDR, locales, providers=mock)
  - `database.py` — motor client + db handle
  - `models/base.py` — PyObjectId + BaseDocument (to_mongo/from_mongo, alias _id)
  - `models/documents.py` — User(role, preferred_locale), Category(department, translations), Product(seller_id, product_type, translations, base_price int IDR), ProductVariant(sku, option_values, inventory, price_override), Cart(+guest_token), Wishlist, Order(items snapshots w/ seller_id, idempotency_key, status codes), MarketplaceSettings
  - `server.py` — preserved status routes + `GET /api/v1/health`
- Infra: `/app/.gitignore` now ignores `.env`/`*.env` (verified via git check-ignore); `.env.example` in backend + frontend.
- No GitHub remote / gh CLI available in this environment — checkpoint not possible.

## Implemented History
- 2026-09-09: Milestone 0 — Repository Audit + Architecture Foundation. Status: PASS.

## Backlog (prioritized, from Master Context V3)
- P0: Milestone 1 foundation (responsive shell, design tokens #145A46 emerald accent, 4-language i18n), taxonomy seed, catalog/PLP/PDP, search/filter/sort, auth+RBAC, cart, wishlist, checkout+mock payment, orders w/ idempotency + atomic inventory, seller isolation, admin core, security hardening.
- P1 (gated): reviews, back-in-stock, coupons, size assistant lite, basic SEO.
- P2 (deferred): AI features, multiple payment/shipping providers, live FX, loyalty, native apps, microservices.

## Next Tasks
1. Milestone 1 — Foundation (shell, design system, i18n) — only on explicit next prompt.
