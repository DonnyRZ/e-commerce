"""Register/check the Telegram Business webhook without printing credentials.

Run from the backend directory after setting TELEGRAM_BOT_TOKEN,
TELEGRAM_WEBHOOK_SECRET, and FRONTEND_URL in the server environment.
"""

import argparse
import sys
import time

import httpx

from config import (
    FRONTEND_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_USERNAME,
    TELEGRAM_WEBHOOK_SECRET,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="show safe webhook readiness details"
    )
    args = parser.parse_args()
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_WEBHOOK_SECRET:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET in the server environment.")
        return 2

    webhook_url = f"{FRONTEND_URL.rstrip('/')}/api/v1/telegram/webhook"
    if not webhook_url.startswith("https://"):
        print("Telegram webhooks require FRONTEND_URL to use HTTPS.")
        return 2

    try:
        with httpx.Client(timeout=20.0) as client:
            identity_response = client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
            )
            identity = identity_response.json()
            bot = identity.get("result") or {} if isinstance(identity, dict) else {}
            if (
                identity_response.is_error
                or not isinstance(identity, dict)
                or not identity.get("ok")
                or str(bot.get("username") or "").lstrip("@").casefold()
                != TELEGRAM_BOT_USERNAME.strip().lstrip("@").casefold()
            ):
                print("The configured token does not match TELEGRAM_BOT_USERNAME.")
                return 1
            if args.check:
                response = client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
                )
            else:
                response = client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
                    json={
                        "url": webhook_url,
                        "secret_token": TELEGRAM_WEBHOOK_SECRET,
                        "allowed_updates": [
                            "business_connection",
                            "business_message",
                            "edited_business_message",
                            "callback_query",
                        ],
                        "drop_pending_updates": False,
                    },
                )
            result = response.json()
    except (httpx.HTTPError, ValueError):
        print("Could not contact the Telegram Bot API. No credentials were displayed.")
        return 1

    if response.is_error or not isinstance(result, dict) or not result.get("ok"):
        print("Telegram rejected the webhook request. Check bot configuration and try again.")
        return 1

    if args.check:
        info = result.get("result") or {}
        configured = info.get("url") == webhook_url
        updates = set(info.get("allowed_updates") or [])
        updates_ready = {
            "business_connection",
            "business_message",
            "edited_business_message",
            "callback_query",
        }.issubset(updates)
        last_error = info.get("last_error_date")
        recent_error = (
            isinstance(last_error, (int, float))
            and time.time() - last_error < 5 * 60
        )
        backlog = int(info.get("pending_update_count") or 0)
        print(
            "Webhook URL: "
            + ("matches" if configured else "does not match")
            + f"; business updates: {'enabled' if updates_ready else 'not enabled'}"
            + f"; pending updates: {backlog}"
            + f"; recent delivery error: {'yes' if recent_error else 'no'}"
        )
        return 0 if configured and updates_ready and not recent_error and backlog < 100 else 1

    print(
        "Webhook registered for business_connection, business_message, edited_business_message, and callback_query updates. "
        f"Verify the bot connection for @{TELEGRAM_BOT_USERNAME.strip().lstrip('@')}; keep "
        "TELEGRAM_INQUIRIES_ENABLED=false until the staging test succeeds."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
