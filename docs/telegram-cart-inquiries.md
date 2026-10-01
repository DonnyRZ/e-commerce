# Telegram cart inquiries

The cart's **Confirm** button creates a short-lived, server-priced inquiry and
opens `@CantikByIndonesia` with only its opaque reference prefilled. The
customer must still tap **Send** in Telegram. `@MuslimahCantikBot` then replies
through the connected Telegram Business account; store staff can continue the
conversation manually from the same account.

This flow is an inquiry, not an order. It does not create a CMS order, collect
payment, clear the cart, reserve stock, or decrement inventory. Price, stock,
and shipping remain subject to admin confirmation. Pending item snapshots are
cleared on delivery or after seven days.

## Telegram reply language

When a valid inquiry reference is received in a Business chat, that inquiry's
web locale becomes the active locale for the conversation. This uses the
locale saved with the inquiry, including English when it was the storefront's
active default. Starting a direct product-candidate flow from the Inbox selects
Uzbek unless an admin has explicitly selected a conversation locale. A valid
new web inquiry sets the locale to the inquiry's web locale, including after
an admin selection.

Future automated replies, payment prompts and order-status notifications use
the active conversation locale. Queued status notifications are translated
when they are sent, so a locale change also applies to an order already in
progress. Messages already delivered remain in the transcript. Admin-written
chat replies and payment-rejection reasons keep their original text. Product
names use available catalog translations and the existing English fallback.

## Configure safely

1. Rotate the bot token that was exposed in the setup screenshot. Put the new
   token only in the server's secret environment file; do not put it in Git,
   browser code, screenshots, chat logs, or this document.
2. Create a webhook secret (for example, `openssl rand -hex 32`) and configure
   `TELEGRAM_WEBHOOK_SECRET` beside `TELEGRAM_BOT_TOKEN`. Keep
   `TELEGRAM_INQUIRIES_ENABLED=false` during setup.
3. Enable Telegram Business / Secretary Mode for `@MuslimahCantikBot`, connect
   it to the store account `@CantikByIndonesia`, and grant the ability to read
   incoming chat messages and reply. No Premium-only permissions are requested
   by this application.
4. Apply the Alembic migration using the repository's normal deployment
   procedure before registering the webhook or opening the status endpoint.
5. Confirm `FRONTEND_URL` is the public HTTPS storefront URL, then register the
   webhook from the backend container (or the backend virtual environment):

   ```powershell
   python scripts/register_telegram_webhook.py
   python scripts/register_telegram_webhook.py --check
   ```

   The webhook subscribes only to `business_connection` and `business_message`
   updates. Existing deployment routing already forwards `/api/` to the API.
6. With the feature flag still false, confirm the webhook check succeeds and
   `GET /api/v1/telegram/status` reports `available: false` with
   `reason: feature_disabled`. After Telegram sends the connection update,
   `configuration_ready` and `business_connection_ready` should be true.
7. Enable `TELEGRAM_INQUIRIES_ENABLED=true` only in staging first. Confirm the
   status endpoint reports `available: true`, then test guest and signed-in
   carts in all four languages and inspect the result in Telegram. Disable the
   flag if anything fails; no new inquiries will be delivered, the cart remains
   intact, and checkout stays disabled.
8. After staging succeeds, enable the flag in production and repeat one small
   real inquiry. Keep paid broadcasts disabled.

## Message delivery and privacy

The API first attempts Telegram's Rich Message slideshow. If the connected
business account cannot send rich messages or Telegram rejects an image, the
API falls back to a regular photo album and concise text summary, then to text
only if photo delivery fails. These are standard Bot API sends; the code never
sets `allow_paid_broadcast`, uses Telegram Stars, or invokes a payment method.
Telegram determines whether Rich Messages are available to the connected
account/client, so verify the actual presentation during staging.

Only a cryptographically random reference is placed in the Telegram deep link;
the cart details are kept server-side until that reference is sent. Webhook
requests must include Telegram's secret header, duplicate update IDs are
deduplicated, and raw webhook payloads, chat IDs, and bot tokens are not logged.
Unrecognized chat messages are not handled automatically. Regular staff replies
remain manual.
