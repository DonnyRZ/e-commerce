# MILESTONE 7.1 — LATE COMPLETE SAFETY REPORT

## Status
PASS (2026-09-10)

## Original Defect
`commit_reservations()` accepted reservations in status `active` **or** `expired`. A delayed CLICK Complete arriving after the reservation TTL had expired would blindly decrement stock and mark the expired reservation committed — even if another checkout had since reserved that unit. Payment correctness could break inventory correctness (oversell risk).

## New Reservation Commit Rule
`reconcile_paid_effects()` (checkout/service.py) commits **only** reservations with `status == "active"` directly. `expired`/`released` rows are NEVER reactivated or committed — they remain historically untouched. A late Complete on a non-active reservation goes through an explicit atomic reconciliation path. New states are centralized: `ORDER_STATUS_PAYMENT_REVIEW` / `ORDER_PAYMENT_STATE_REVIEW` (checkout/service.py) and `"reconciliation_required"` added to the centralized `PAYMENT_STATUSES` tuple (payments/service.py). Migrations: `f1a2b3c4d5e6` (auditable `reacquired_from` self-FK on inventory_reservations), `a1b2c3d4e5f7` (payments.status widened 20→30 for the new state; root-caused a StringDataRightTruncationError found during testing).

## Late Complete With Stock Available
One transaction: payment row locked (`_locked_payment`), order row locked (`FOR UPDATE`), reservation rows locked, variant rows locked in deterministic id order. Feasibility is checked first (nothing mutates before it passes): per variant, `available = stock − Σ(active reservations) − already-planned reacquisitions`. If all quantities available → apply: stock decremented exactly once; for each expired/released row a NEW replacement reservation is inserted (`status=committed`, `committed_at=now`, `reacquired_from=<original id>`) — the original row stays `expired`/`released` as an auditable trail. Then payment → paid, order → paid, source cart cleared (existing exactly-once guard).

## Late Complete Without Stock
If any quantity cannot be reacquired: NOTHING is applied (no stock decrement, no reservation change, no cart clearing). Payment → `reconciliation_required`, order → `payment_review` + `payment_state=review`, event logged (`COMPLETE`/`reconciliation`, reason=inventory_unavailable), and the Complete response uses the existing CLICK code **-7 (UPDATE_FAILURE)**. A later retried Complete (allowed from `reconciliation_required` alongside `prepared`) re-attempts reconciliation — if stock has freed, it pays exactly once.

## PostgreSQL Transaction Safety
Single transaction per Complete: `SELECT … FOR UPDATE` on payment, order, reservation rows, and variant rows (sorted by id → deterministic lock order, no deadlock vs checkout's identical ordering). Two-phase reconcile: check-then-apply; any insufficiency returns before mutation. Exactly-once preserved: committed rows are excluded from both worklists, so retries cannot double-decrement or create duplicate replacements.

## Race Test
`test_race_expire_b_reserves_delayed_a_complete` (stock=1): A reserves → payment prepared (TIMEOUT) → B blocked 409 while A active → A's reservation expires (backdated + real lazy sweep) → B reserves the freed unit (201) → delayed Complete for A → **-7, reconciliation_required / payment_review / review, stock stays 1, A's cart preserved, no replacement row**. Repeat → identical (idempotent). B pays → stock 0. A retries → still reconciliation, stock never negative. Independently re-verified by testing_agent via curl+psql (36/36 assertions).

## Reacquisition Test
`test_late_complete_reacquires_safely` (stock=2): A reserves → expires → delayed Complete → paid; stock exactly 1; rows = original `expired` (untouched) + replacement `committed` with `reacquired_from=<original id>`; cart cleared once; repeated Complete → zero further effects. Released-row variant: FAILED payment → released; new transaction SUCCESS → reacquires via replacement, released row untouched, stock decremented exactly once across both attempts.

## Idempotency
Repeated delayed Completes: no duplicate stock decrement, no duplicate replacement reservation, no duplicate cart clearing, no duplicate order transition. Order-creation idempotency (M7) untouched and regression-passing.

## CLICK Protocol
No invented codes: unfulfillable late Complete → existing **-7 UPDATE_FAILURE** ("Merchant inventory reconciliation required"); invalid signature → -1; wrong amount → -2; already paid → -4; transaction not found → -6. Mock mode only — zero external CLICK network.

## Reservation Expiry Scheduler Readiness
Lazy in-request sweep retained for development. VPS-callable entry point added: `python3 -m jobs.expire_reservations` (tested, exits 0) — wire into cron/systemd timer on the VPS, e.g. `* * * * * cd /app/backend && venv/bin/python -m jobs.expire_reservations`. No Emergent scheduler dependency; nothing deployed.

## Regression
- pytest **134/134 PASS** (M7 25 + M7.1 6 + catalog/auth/payments M5.1/cart-wishlist M6 suites).
- testing_agent iteration_12.json: 36/36 independent M7.1 assertions PASS, storefront regressions clean, `retest_needed: false`.
- UI happy path re-verified post-patch: guest checkout → mock SUCCESS → confirmation `Paid`, UZS 179,000, cart badge cleared.
- Frontend `yarn build` PASS. Alembic: current-DB upgrade + clean-DB replay both at `a1b2c3d4e5f7` head.
- i18n: `orders.pay.review`, `orders.state.payment_review`, `mockPay.reviewTitle/reviewBody` × id/en/uz/ru; mock page shows a "Payment under review" panel for reconciliation outcomes.

## Known Issues
- Test-harness note (not a product bug): order-creation rate limit (30/15min/IP, in-memory) can throttle heavy curl suites from one IP; restart backend to reset, or wait the window. Production-appropriate; unchanged.
- Environment note: the pod restarted mid-session and PostgreSQL was re-provisioned + reseeded (user/db recreated, migrations replayed, seeds re-run). All green afterwards; VPS deployments keep persistent volumes so this does not affect production.
- Pre-existing, unchanged: guest 401 `/auth/me` console probes; preview-ingress SameSite rewrite (verify on VPS Nginx).

# STOP
Seller Marketplace was NOT started.
