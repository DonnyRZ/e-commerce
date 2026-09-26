# Telegram inquiry recovery — 26 September 2026

No schema migration is required. Implementation does not modify live orders or configuration.

## Customer flow

- Preserve the idempotency key in session storage, scoped to cart ID, locale and item/quantity/price snapshot. HTTP retries reuse the key.
- Always release confirmation state after navigation; show selectable message text, Copy and Reopen Telegram actions.
- The cart-owner-scoped GET `/api/v1/telegram/inquiries/{reference}` reports delivery without exposing chat IDs. Poll unresolved requests and refresh on focus.
- A delivered request can be explicitly replaced by a new request. Item changes invalidate the handoff.
- Queue cart mutations and block confirmation while they are pending. Snapshot creation holds the Cart lock used by mutations.
- Keep the cart: opening Telegram does not mean pressing Send. Automatic selective cart reconciliation is not implemented; it must preserve additions made after the snapshot.

## Delivery recovery

The existing snapshot JSON stores `_delivery.started` and `_delivery.update_id`. `sending` becomes `unknown` on timeout or after a five-minute stale lease. Do not automatically resend an original update with an uncertain outcome. A new customer message may retry after checking the chat; the web UI warns about duplicate replies.

Fresh processing receipts return 503, allowing Telegram to retry if the worker crashes. Stale receipts can be reclaimed; completed receipts remain deduplicated. Legacy sending rows without metadata are treated as stale. Bound references cannot move to another chat. Missing connections are fetched with getBusinessConnection before eligibility checks.

Fallback single-photo chunks now use sendPhoto.photo. CMS cannot create an order before the inquiry binds to the customer chat. Historical orders with missing bindings are not rewritten.

## Deployment follow-up

At deployment, run `backend/scripts/register_telegram_webhook.py` in the usual deployment environment, followed by its `--check` mode, to subscribe to edited_business_message. The script preserves pending updates. Never print the bot token. Normal new messages do not depend on the additional subscription. No production webhook was changed during implementation.

## Verification

Run isolated backend tests without the existing database-mutating pytest fixtures:

```powershell
backend/.venv/Scripts/python.exe -m unittest discover -s backend/unit_tests -v
```

The tests cover timeout recovery, stale receipts, duplicate updates, chat ownership, cart-scoped status, quota-free idempotent retry, premature CMS orders, connection recovery and 1/2/10/11-photo fallback.

Frontend tests exercise the actual CartPage with mocked network/navigation, including cancelled navigation and lost API responses, plus handoff persistence and four-language copy. Run frontend lint, test:ci and both production builds.

Real-phone Telegram handoff and an end-to-end order through the deployed webhook require a post-deploy smoke test. Mocked tests do not verify native Telegram behavior.
