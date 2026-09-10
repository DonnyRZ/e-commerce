# MILESTONE 7 — CHECKOUT + ORDERS + CLICK MOCK REPORT

## Status
PASS (2026-09-10)

## Checkout
- Guest checkout (P0) works end-to-end: secure guest cart (HttpOnly `guest_cart_token`) → contact email + full address form → shipping selection → server recalculation → order + reservation + CLICK payment created atomically. No registration forced.
- Authenticated checkout: saved-address picker (ownership verified server-side — user B selecting user A's `saved_address_id` gets 404), new-address option, order linked to `user_id`, email snapshotted from the account.
- Address snapshot is immutable: editing a saved address after ordering does NOT alter the historical order (tested).
- Server-side validation of all address fields (pydantic), guest email required, empty cart rejected, unknown shipping method rejected.
- Rate limit: 30 order creations / 15 min / IP (in-memory, mirrors register limiter); idempotency key is the primary defense.

## Shipping
- `shipping/` provider package: `ShippingProvider` ABC → `MockShippingProvider` (only implementation; real courier pluggable later via `SHIPPING_PROVIDER` env gate, unknown value fails closed).
- Server-defined integer UZS rates: Standard 30,000 (FREE when merchandise subtotal ≥ 550,000 — matches storefront promo), Express 65,000. Frontend never supplies shipping cost; `POST /api/v1/checkout/quote` recomputes everything.

## PostgreSQL Schema
- Alembic `e7f8a9b0c1d2` (head): new table `inventory_reservations` (id, order_id FK→orders ON DELETE CASCADE, product_variant_id FK, quantity, status active|committed|released|expired, expires_at, created_at, committed_at, released_at; indexes on order_id/variant/status); `orders` + `guest_access_token` (unique) + `cart_id`; `order_items` + `variant_id` (snapshot, intentionally no FK).
- Verified: current-DB upgrade + clean-DB replay (23 tables) + `alembic current` at head.

## Order Architecture
- `POST /api/v1/checkout/orders`: idempotent via client-supplied `idempotency_key` (unique column; replay returns the same order; concurrent same-key race resolved via IntegrityError → return winner). Double-submit locked in UI + backend authority.
- `order_number` = opaque `MC-XXXXXXXXXX` (uuid-derived, non-sequential).
- Totals: merchandise subtotal + shipping = grand_total; integer UZS only; no invented tax/discount.
- State machines — payment: pending → prepared → paid | failed | cancelled | expired (+refunded/reversed preserved). order: pending_payment → paid | cancelled (one-shot payment attempt; failure cancels order, cart retained for re-checkout).

## Order Snapshots
Immutable per order_item: `product_id`, `variant_id`, `seller_id` (mandatory for Seller milestone), `sku`, `product_name` (localized at checkout locale), `option_values` (JSONB), `image_url`, `unit_price`, `quantity`, `line_total`. Plus order-level: `guest_email` (customer email snapshot), `shipping_address` (JSONB), `shipping_method`, amounts, currency. Verified: live catalog price change (+7,000 UZS via SQL) does not mutate a placed order.

## Inventory Reservation
- Reserve at checkout: variant rows locked (`SELECT … FOR UPDATE`, deterministic id order), availability = stock − Σ(active reservations), oversell rejected 409; concurrent last-unit test: exactly one of two simultaneous checkouts wins.
- Cart still does NOT reserve stock (regression asserted).
- Commit: on successful Complete — inside `_on_payment_paid` guard — reservations locked, physical stock decremented exactly once, status → committed (duplicate Complete verified: no second decrement).
- Release: failed/cancelled/expired payments → active reservations → released, stock untouched, cart retained.
- Expiry: TTL via `INVENTORY_RESERVATION_TTL_MINUTES` (30, env-configurable); lazy sweep marks overdue active reservations expired (deterministically tested by backdating `expires_at`).

## CLICK Payment Integration
- Order → `PaymentService.create_payment(order)` (M5.1 foundation untouched): amount = authoritative `grand_total`, `merchant_trans_id` = server-generated order id (never client-controlled), payment↔order FK persisted, idempotency key `order-{id}`.
- Prepare/Complete protocol, MD5 raw-string signature, error mapping, payment_events audit — all preserved and regression-passed.

## Mock CLICK Success
Customer mock page buttons call `POST /api/v1/payments/mock/pay` (mock-gated, order-owner/guest-token authorized) → shared scenario runner → REAL `PaymentService.prepare` (signature+amount verified) → REAL `complete` → payment paid → order paid → inventory committed → source cart cleared. Tested: steps `[prepare:0, complete:0]`, stock 14→13 once, cart emptied, reservation committed.

## Payment Failure Scenarios
- FAILED: payment failed, order cancelled, reservation released, cart retained, stock unchanged.
- CANCELLED: payment cancelled (cancelled_at set), order cancelled, reservation released, cart retained.
- EXPIRED: payment expired, order cancelled, reservation released.
- TIMEOUT: prepare only — payment stays prepared (unknown/pending), order pending_payment, reservation held until TTL, cart retained. Never marked paid.
- WRONG AMOUNT: rejected (-2), no payment/order mutation, no stock commit, cart intact.
- INVALID SIGNATURE: rejected (-1), zero financial/inventory mutation.

## Duplicate Safety
- Order: same idempotency key → same order, exactly one row/reservation set.
- Prepare replay → success replay; Complete replay (same trans) → success echo; Complete with other trans after paid → -4 ALREADY_PAID. Stock decremented exactly once across DUPLICATE_COMPLETE. Events logged with proper semantics.

## Cart Clearing
On paid: only `order.cart_id`'s items deleted (exactly once, inside the paid-transition guard). Verified: unrelated guest cart retains items; failure paths retain the source cart; a post-checkout new cart is unaffected.

## Guest Order
Confirmation via `GET /api/v1/orders/track?order_number=&token=` — opaque 24-byte `guest_access_token`, constant-time compare, 404 on wrong/missing token (also 422 without param), never exposes auth-owned orders. E2E: tampered/stripped token → invalid page, no data leak.

## Customer Order History
`GET /api/v1/account/orders` (ref, date, payment state, order state, UZS total, item count) → `/orders`; detail `GET /api/v1/account/orders/{order_number}` → `/orders/:orderNumber` with full snapshots. No fabricated tracking/reviews.

## Order Detail Security
Cross-user test: user B gets 404 on user A's `order_number`; B's history excludes A's orders; guest track endpoint 404s auth-owned orders. PASS.

## Localization
~65 new keys × id/en/uz/ru — checkout, address fields (reused auth.*), shipping, summary, mock payment + MOCK warning, confirmation, history/detail, all payment/order states. E2E verified RU/UZ/ID rendering with no raw keys; money always integer UZS.

## Responsive
375px / 768px / 1440px: checkout, mock payment, confirmation, orders, order detail — zero horizontal overflow (E2E verified scrollWidth).

## Regression
pytest 128/128 (catalog 20, M3 filters 14, auth M5, payments M5.1 23, cart/wishlist M6 20, checkout M7 25). E2E regression pass: homepage/PLP/PDP/cart/wishlist/login. Frontend production build (`yarn build`) succeeds. Backend starts clean.

## PostgreSQL
Zero MongoDB — motor/pymongo absent; all persistence PostgreSQL via SQLAlchemy/Alembic.

## VPS Portability
No Emergent runtime dependency: mock providers are in-process, config via env only, cookies standard HttpOnly. CLICK callbacks will hit the VPS directly when real credentials arrive (CLICK_MODE=test/production gates preserved; mock endpoints 404 in those modes — unit-verified).

## Tests Run
- `backend/tests/test_checkout_m7.py` — 25 tests (list covers acceptance items 1-60 at API level incl. concurrency + TTL).
- Full suite: 128/128 PASS.
- Alembic current-DB upgrade + clean-DB replay.
- `yarn build` PASS.
- testing_agent E2E iteration_11.json: 12/12 PASS.
- Manual repro: cart badge on mock page verified present (agent note was a testid false positive).

## Known Issues
- Non-blocking: guest 401 probes (`/auth/me`) appear as console network errors (expected session-restore pattern).
- Non-blocking: locale switches to account preference at login (intentional M5 behavior; changes number separator only).
- Tracked from before: preview ingress rewrites SameSite cookies — re-verify on VPS Nginx.
- Accepted corner: a Complete arriving after TTL expiry while payment is still `prepared` will commit an expired reservation (payment-wins); stock can't be double-committed, but availability between expiry and late Complete is not re-checked. Mock-scope acceptable.

## Credit Usage
Not visible to the agent.

## Next Recommended Milestone
Milestone 8 — Seller Marketplace

# STOP
Seller, Admin, real CLICK integration, and deployment were NOT started.
