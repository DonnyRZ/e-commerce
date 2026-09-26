"""Telegram cart inquiry presentation and delivery helpers.

This module deliberately uses only ordinary Bot API sends. It never opts into
paid broadcasts, Stars, or Telegram Premium features.
"""

from __future__ import annotations

import html
import time
from urllib.parse import urljoin, urlparse

import httpx

from config import FRONTEND_URL


COPY = {
    "id": {
        "title": "Permintaan konfirmasi keranjang",
        "item": "Produk",
        "products": "produk",
        "variant": "Varian",
        "sku": "SKU",
        "quantity": "Jumlah",
        "price": "Harga satuan",
        "line_total": "Total item",
        "subtotal": "Subtotal sementara",
        "request_note": "Ini adalah permintaan konfirmasi pre-order, bukan pesanan final. Estimasi proses 2–3 minggu; admin akan mengonfirmasi harga akhir dan ongkir di chat ini.",
        "expired": "Referensi keranjang ini sudah kedaluwarsa. Silakan kembali ke toko dan kirim permintaan baru.",
        "prefill": "Halo, saya ingin mengonfirmasi keranjang. Referensi: {reference}",
        "status": "Mode pemesanan",
        "unavailable": "Pre-order · estimasi 2–3 minggu",
    },
    "en": {
        "title": "Cart confirmation request",
        "item": "Product",
        "products": "products",
        "variant": "Variant",
        "sku": "SKU",
        "quantity": "Quantity",
        "price": "Unit price",
        "line_total": "Line total",
        "subtotal": "Current subtotal",
        "request_note": "This is a pre-order inquiry, not a final order. Estimated processing time is 2–3 weeks; our admin will confirm the final price and shipping in this chat.",
        "expired": "This cart reference has expired. Please return to the store and send a new request.",
        "prefill": "Hello, I would like to confirm my cart. Reference: {reference}",
        "status": "Ordering mode",
        "unavailable": "Pre-order · estimated 2–3 weeks",
    },
    "uz": {
        "title": "Savatni tasdiqlash so‘rovi",
        "item": "Mahsulot",
        "products": "mahsulot",
        "variant": "Variant",
        "sku": "SKU",
        "quantity": "Miqdor",
        "price": "Birlik narxi",
        "line_total": "Mahsulot jami",
        "subtotal": "Joriy oraliq jami",
        "request_note": "Bu yakuniy buyurtma emas, pre-order so‘rovi. Jarayon taxminan 2–3 hafta davom etadi; adminimiz yakuniy narx va yetkazib berishni tasdiqlaydi.",
        "expired": "Savat havolasining muddati tugagan. Do‘konga qaytib, yangi so‘rov yuboring.",
        "prefill": "Salom, savatimni tasdiqlamoqchiman. Havola: {reference}",
        "status": "Buyurtma rejimi",
        "unavailable": "Pre-order · taxminiy 2–3 hafta",
    },
    "ru": {
        "title": "Запрос на подтверждение корзины",
        "item": "Товар",
        "products": "товаров",
        "variant": "Вариант",
        "sku": "Артикул",
        "quantity": "Количество",
        "price": "Цена за единицу",
        "line_total": "Сумма по товару",
        "subtotal": "Текущая сумма",
        "request_note": "Это запрос на предзаказ, а не окончательный заказ. Ориентировочный срок — 2–3 недели; администратор подтвердит итоговую цену и доставку в этом чате.",
        "expired": "Срок действия ссылки на корзину истёк. Вернитесь в магазин и отправьте новый запрос.",
        "prefill": "Здравствуйте, хочу подтвердить корзину. Ссылка: {reference}",
        "status": "Режим заказа",
        "unavailable": "Предзаказ · ориентировочно 2–3 недели",
    },
}


def localized(locale: str, key: str) -> str:
    return COPY.get(locale, COPY["en"]).get(key, COPY["en"][key])


def prefilled_message(locale: str, reference: str) -> str:
    return localized(locale, "prefill").format(reference=reference)


def _price(value: object) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _public_image_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = urljoin(f"{FRONTEND_URL}/", value.strip())
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def make_snapshot(cart: dict, locale: str) -> dict:
    """Copy only server-calculated item data needed to render the inquiry."""
    items = []
    for source in cart.get("items", []):
        translations = source.get("translations") or {}
        translation = translations.get(locale) or translations.get("en") or translations.get("id") or {}
        options = source.get("option_values") or {}
        variant = " / ".join(
            f"{key}: {value}" if key else str(value)
            for key, value in options.items()
            if value not in (None, "")
        )
        items.append(
            {
                "name": str(translation.get("title") or source.get("slug") or localized(locale, "item"))[:255],
                "_cart_item_id": str(source.get("id") or "")[:32],
                "_cart_product_id": str(source.get("product_id") or "")[:32],
                "_cart_variant_id": str(source.get("variant_id") or "")[:32],
                "variant": variant[:255],
                "sku": str(source.get("sku") or "")[:80],
                "quantity": int(source.get("quantity") or 0),
                "unit_price": int(source.get("unit_price") or 0),
                "line_total": int(source.get("line_total") or 0),
                "availability": str(source.get("availability") or "unavailable")[:32],
                "image_url": _public_image_url(source.get("image_url")),
            }
        )
    return {
        "locale": locale if locale in COPY else "en",
        "items": items,
        "subtotal": int(cart.get("subtotal") or 0),
        "currency": str(cart.get("currency") or "UZS")[:3],
        "item_count": int(cart.get("item_count") or 0),
    }


def _item_caption(item: dict, locale: str) -> str:
    labels = COPY.get(locale, COPY["en"])
    rows = [item["name"]]
    if item.get("variant"):
        rows.append(f"{labels['variant']}: {item['variant']}")
    if item.get("sku"):
        rows.append(f"{labels['sku']}: {item['sku']}")
    rows.extend(
        (
            f"{labels['quantity']}: {item['quantity']}",
            f"{labels['price']}: {_price(item['unit_price'])} UZS",
            f"{labels['line_total']}: {_price(item['line_total'])} UZS",
        )
    )
    rows.append(f"{labels['status']}: {labels['unavailable']}")
    return "\n".join(rows)


def rich_message(snapshot: dict, reference: str) -> dict:
    """Build a native Telegram Rich Message with one slideshow card per item."""
    locale = snapshot["locale"]
    labels = COPY.get(locale, COPY["en"])
    slides = []
    for item in snapshot["items"]:
        caption = html.escape(_item_caption(item, locale))
        image = item.get("image_url")
        image_tag = f'<img src="{html.escape(image, quote=True)}"/>' if image else ""
        slides.append(f"<figure>{image_tag}<figcaption>{caption}</figcaption></figure>")
    slide_block = f"<tg-slideshow>{''.join(slides)}</tg-slideshow>" if slides else ""
    heading = html.escape(labels["title"])
    total = html.escape(f"{_price(snapshot['subtotal'])} {snapshot['currency']}")
    note = html.escape(labels["request_note"])
    ref = html.escape(reference)
    content = (
        f"<h2>{heading}</h2>"
        f"<p>{ref} · {len(snapshot['items'])} {html.escape(labels['products'])}</p>"
        f"{slide_block}"
        f"<hr/><p><b>{html.escape(labels['subtotal'])}: {total}</b></p>"
        f"<p>{note}</p>"
    )
    return {"html": content}


def summary_text(snapshot: dict, reference: str) -> str:
    locale = snapshot["locale"]
    labels = COPY.get(locale, COPY["en"])
    items = "\n\n".join(_item_caption(item, locale) for item in snapshot["items"])
    prefix = f"{labels['title']} · {reference}\n\n"
    subtotal = f"\n\n{labels['subtotal']}: {_price(snapshot['subtotal'])} {snapshot['currency']}"
    return f"{prefix}{items}{subtotal}\n\n{labels['request_note']}"


def summary_chunks(snapshot: dict, reference: str, limit: int = 3800) -> list[str]:
    """Split long cart summaries at item boundaries under Telegram's text cap."""
    locale = snapshot["locale"]
    labels = COPY.get(locale, COPY["en"])
    chunks: list[str] = []
    current = f"{labels['title']} · {reference}"
    sections = [_item_caption(item, locale) for item in snapshot["items"]]
    sections.extend(
        (
            f"{labels['subtotal']}: {_price(snapshot['subtotal'])} {snapshot['currency']}",
            labels["request_note"],
        )
    )
    for section in sections:
        candidate = f"{current}\n\n{section}"
        if len(candidate) > limit and current != f"{labels['title']} · {reference}":
            chunks.append(current)
            current = section
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class TelegramDeliveryError(Exception):
    """A definite Bot API rejection; message contents/tokens are never exposed."""

    def __init__(self, message: str, *, safe_code: str = "telegram_api_rejected_request"):
        super().__init__(message)
        self.safe_code = safe_code


async def bot_request(
    token: str, method: str, payload: dict, *, timeout_seconds: float = 20.0
) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds)
        ) as client:
            response = await client.post(url, json=payload)
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # The request may have reached Telegram; callers must not blindly retry
        # this particular send because its outcome is ambiguous.
        raise TimeoutError("telegram_delivery_outcome_unknown") from exc
    if response.is_error or not isinstance(data, dict) or not data.get("ok"):
        description = str(data.get("description") or "").casefold() if isinstance(data, dict) else ""
        safe_code = (
            "message_not_modified"
            if "message is not modified" in description
            else "telegram_api_rejected_request"
        )
        raise TelegramDeliveryError("telegram_api_rejected_request", safe_code=safe_code)
    return data.get("result") or {}


async def telegram_webhook_is_ready(token: str, webhook_url: str) -> bool:
    """Check webhook destination/subscriptions without exposing Bot API errors."""
    try:
        info = await bot_request(
            token, "getWebhookInfo", {}, timeout_seconds=5.0
        )
    except (TelegramDeliveryError, TimeoutError):
        return False
    if not isinstance(info, dict):
        return False
    allowed = set(info.get("allowed_updates") or [])
    last_error = info.get("last_error_date")
    recent_error = (
        isinstance(last_error, (int, float))
        and time.time() - last_error < 5 * 60
    )
    return bool(
        info.get("url") == webhook_url
        and {"business_connection", "business_message", "callback_query"}.issubset(allowed)
        and int(info.get("pending_update_count") or 0) < 100
        and not recent_error
    )


async def send_inquiry(token: str, connection_id: str, chat_id: int, snapshot: dict, reference: str) -> str:
    base = {"business_connection_id": connection_id, "chat_id": chat_id}
    try:
        await bot_request(token, "sendRichMessage", {**base, "rich_message": rich_message(snapshot, reference)})
        return "rich"
    except TelegramDeliveryError:
        # Rich messages are not guaranteed to be available for every business
        # account/client. A normal media album is the free compatibility path.
        media = [
            {"type": "photo", "media": item["image_url"], "caption": _item_caption(item, snapshot["locale"])[:900]}
            for item in snapshot["items"]
            if item.get("image_url")
        ]
        try:
            if media:
                for offset in range(0, len(media), 10):
                    chunk = media[offset : offset + 10]
                    if len(chunk) == 1:
                        await bot_request(
                            token,
                            "sendPhoto",
                            {**base, "photo": chunk[0]["media"], "caption": chunk[0]["caption"]},
                        )
                    else:
                        await bot_request(
                            token,
                            "sendMediaGroup",
                            {**base, "media": chunk},
                        )
            for chunk in summary_chunks(snapshot, reference):
                await bot_request(token, "sendMessage", {**base, "text": chunk})
            return "album"
        except TelegramDeliveryError:
            # If an image URL cannot be fetched, still deliver all cart details.
            for chunk in summary_chunks(snapshot, reference):
                await bot_request(token, "sendMessage", {**base, "text": chunk})
            return "text"
