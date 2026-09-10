# MILESTONE 6 — CART + WISHLIST REPORT

**Status: PASS** (2026-09-10)

## Scope delivered
- **Guest cart**: server-issued opaque 32-byte token in HttpOnly `guest_cart_token` cookie (30d); forged/client-supplied tokens are ignored and replaced. Cart is intent, not reservation — stock validated on mutations, never decremented.
- **Authenticated cart**: bound to `user.id`; no guest token issued while logged in; CSRF double-submit enforced on all mutations (403 without header); full per-user isolation (cross-user item access → 404).
- **Guest→auth merge** (`POST /api/v1/cart/merge`, triggered automatically on login/register): quantities summed per variant, clamped to live stock with `adjustments` reported (dead/OOS variants dropped), guest cart row + cookie deleted, repeat merge is a no-op. User-facing `cart.mergeAdjusted` toast when clamping occurs.
- **Server-authoritative pricing**: unit price = sale_override → price_override → base_price; integer UZS only; client never submits prices.
- **Wishlist (auth-only)**: 401 for guests (API + `/wishlist` route redirect + PDP heart → toast + `/login`), idempotent add, per-user isolation, localized payload with stock state.
- **UI**: CartPage (qty stepper with stock cap, availability badges, subtotal, checkout CTA), WishlistPage (ProductCard grid), header badge counts, PDP wiring, ~15 new i18n keys × 4 locales (id/en/uz/ru).
- **DB**: Alembic `d4e5f6a7b8c9` at head; uniques `uq_cart_items_cart_variant`, `uq_wishlists_user_id`, `uq_wishlist_items_wishlist_product`; cart row-lock on merge/add race paths.

## Verification
- **Backend pytest**: 103/103 PASS (incl. new `tests/test_shop_m6.py` — 20 tests: token security/HttpOnly, OOS/invalid-variant/unknown-product rejection, same-variant merge + stock cap, qty update bounds, override pricing, guest+auth isolation, CSRF 403, merge clamp/no-conflict/idempotent/auth-required, wishlist auth/idempotency/isolation).
- **E2E (testing_agent, iteration_10.json)**: 12/12 PASS — PDP add-to-cart, cart page contents (UZS 499,000), stepper cap at stock 2, guest persistence across reload, remove/empty state, Black/XXL OOS disabled, guest wishlist gating, login-merge, auth wishlist toggle, RU/UZ/ID/EN localized (no raw keys), 375px mobile clean, zero JS console errors.

## Fixes during testing
- `PriceDisplay.jsx` now forwards `data-testid` (was hardcoded, dropping e.g. `cart-subtotal`).
- Test-harness: M6 suite reduced to 2 fresh registrations (in-memory register rate-limit 10/15min/IP was being exhausted); seeded customer reused with state cleanup.

## Known non-issues
- Guest 401 network probes (`/auth/me`) appear in browser console — expected session-restore pattern; wishlist query already gated by `enabled: Boolean(user)`.
- Preview ingress rewrites SameSite (tracked for VPS Nginx verification).
- GitHub checkpoint NOT saved (no remote in this environment).

## Next
Milestone 7 — Checkout + Orders + CLICK mock payment (PaymentService hooks ready: `create_payment(order)`, `_on_payment_paid`).
