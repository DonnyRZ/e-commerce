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
- 2026-09-09: Milestone 1 — Foundation + Design System + Four-Language i18n. Status: PASS.
  - App shell: AnnouncementBar, Header (sticky, desktop nav, search/wishlist/cart/account entries), MobileNavigation (sheet drawer), LanguageSelector (dropdown), Footer, AppShell with max-w-[1440px] container.
  - i18n: custom React context (`src/i18n/index.js` I18nProvider/useI18n), dictionaries in `src/i18n/translations.js` for id/en/uz/ru, English fallback, localStorage persistence (`mc_locale`), `<html lang>` sync.
  - Design tokens: primary = emerald #145A46 (HSL 163 63% 22%), ring matched, radius 0.375rem, Manrope font (Cyrillic-capable) via Google Fonts import in index.css.
  - Common components: EmptyState, ErrorState, LoadingSkeleton, PriceDisplay (Intl currency per locale); shadcn Button/Input/Select/Breadcrumb/Sheet/DropdownMenu/Skeleton/Sonner reused.
  - API client: `src/lib/api.js` axios instance (baseURL from REACT_APP_BACKEND_URL, withCredentials).
  - Route shell placeholders: /, /search, /cart, /wishlist, /account, /checkout, /seller, /admin (+404).
  - Verified by testing agent (iteration_1.json): 100% backend + frontend, all 4 languages, persistence, 375/768/1440 no overflow, mobile drawer open/close, zero console errors. Announcement-bar translation concern disproven (RU/UZ verified via screenshot).
- 2026-09-09: Milestone 1.1 — Frontend Visual Foundation / UNIQLO UX Calibration. Status: PASS.
  - Rebuilt sparse M1 shell into retail-grade foundation: black promo bar, premium header (3 department nav buttons opening mega overlay, utility icons), SecondaryNav strip, SearchOverlay (search input + dept tabs + image category grid, Esc/X close, scroll lock).
  - Homepage: full-bleed visual hero (restrained overlay + 2 pill CTAs), Shop-by-Category image strip, New Arrivals + Best Sellers product grids, 3 department tiles.
  - ProductCard foundation: aspect-[3/4] image-dominant, swatches, wishlist heart, uppercase metadata, name, Rp narrowSymbol price, NEW/SALE badges, zero card chrome. ProductGrid 2/3/4 cols.
  - PLP visual foundation at /shop: breadcrumb, title, Results: {count} items (i18n interpolation), Sort/Filter buttons (visual only), category strip, 10-card grid.
  - Footer: grouped pipe-separated SHOP/HELP/ACCOUNT/ABOUT, promo line, copyright + socials + language selector.
  - Demo placeholder data with localized names: src/data/demo.js (3 departments, 17 categories, 10 demo products incl. required Gray Sweat Oversized Full-Zip Hoodie). Neutral Unsplash placeholders — IP-safe.
  - i18n extended: t(key, {params}) interpolation; ~30 new keys × 4 locales. Verified by testing agent (iteration_2.json): 100% pass, all viewports, all languages, zero console errors.
- 2026-09-09: Milestone 1.2 — Final Frontend Visual Gate. Status: PASS. FRONTEND FOUNDATION APPROVED for Prompt #3.
  - Muslimah image compliance: replaced non-modest/incoherent placeholders (shorts/streetwear models, skincare tubes in apparel categories). Departments now visually distinct: modest fashion portraits (Women Muslimah), neutral folded/hanging apparel (UNIQLO Products), clean beauty shots (Skincare).
  - SecondaryNav trimmed to New Arrivals/Best Sellers/Sale (redundant Shop removed).
  - New reusable EditorialSection ("Stories & Guides"): 4 localized cards (Modest Styling, Hijab Styling, Skincare Routine, New Season Edit) — image/label/title/desc/Learn More.
  - Homepage rhythm final: promo bar > header > secondary nav > hero > categories > new arrivals > dept tiles > best sellers > editorial > footer.
  - Verified by testing agent (iteration_3.json): 100% pass, 0 console errors, all images load, 4-locale regression incl. RU persistence, responsive 375/768/1440 clean.

## Backlog (prioritized, from Master Context V3)
- P0: Milestone 1 foundation (responsive shell, design tokens #145A46 emerald accent, 4-language i18n), taxonomy seed, catalog/PLP/PDP, search/filter/sort, auth+RBAC, cart, wishlist, checkout+mock payment, orders w/ idempotency + atomic inventory, seller isolation, admin core, security hardening.
- P1 (gated): reviews, back-in-stock, coupons, size assistant lite, basic SEO.
- P2 (deferred): AI features, multiple payment/shipping providers, live FX, loyalty, native apps, microservices.

## Next Tasks
1. Prompt #3 / Milestone 2 — Catalog (taxonomy seed, categories, products/variants backend, real PLP wiring) — only on explicit next prompt. Frontend foundation is FINAL-APPROVED.
2. Known tracked issue: dev CORS_ORIGINS="*" — fix during security hardening milestone.
3. Replace demo.js placeholder data with real catalog API; add /stories/:slug routes later; SecondaryNav active underline should reflect route state once PLP lands.
