"""Validation, masking, and localized Telegram UI for bank transfers."""

from __future__ import annotations

import re
from typing import Iterable


MAX_PAYMENT_DESTINATIONS = 4
DESTINATION_LOCALES = {"id", "en", "uz", "ru"}

PAYMENT_COPY = {
    "id": {
        "prompt_title": "Order {order_number} sudah dibuat.",
        "items": "Jumlah produk",
        "total": "Total pembayaran",
        "choose": "Pilih bank untuk transfer:",
        "details_title": "Detail pembayaran · Order {order_number}",
        "bank": "Bank",
        "type": "Jenis tujuan",
        "account": "Rekening bank",
        "card": "Kartu",
        "number": "Nomor tujuan",
        "holder": "Nama pemilik",
        "transfer": "Transfer tepat sebesar",
        "after_transfer": "Setelah transfer, kirim bukti pembayaran di chat ini.",
        "copy": "Salin nomor",
        "change": "Ganti bank",
        "tracking": "Lihat status order",
        "selected": "Bank dipilih.",
        "choose_again": "Silakan pilih bank tujuan transfer:",
        "invalid": "Pilihan bank tidak berlaku. Minta admin mengirim ulang detail pembayaran.",
        "unavailable": "Pilihan ini sudah tidak tersedia. Silakan pilih bank lain.",
        "locked": "Pembayaran order ini sudah diproses dan tidak dapat diubah.",
        "no_destinations": "Pilihan rekening sedang tidak tersedia. Silakan hubungi admin toko.",
    },
    "en": {
        "prompt_title": "Order {order_number} is confirmed.",
        "items": "Products",
        "total": "Total to pay",
        "choose": "Choose a bank for your transfer:",
        "details_title": "Payment details · Order {order_number}",
        "bank": "Bank",
        "type": "Destination type",
        "account": "Bank account",
        "card": "Card",
        "number": "Destination number",
        "holder": "Account holder",
        "transfer": "Transfer this exact amount",
        "after_transfer": "After transferring, send your payment proof in this chat.",
        "copy": "Copy number",
        "change": "Change bank",
        "tracking": "Track your order",
        "selected": "Bank selected.",
        "choose_again": "Choose a bank for your transfer:",
        "invalid": "This bank choice is no longer valid. Ask the store to resend payment details.",
        "unavailable": "This option is no longer available. Please choose another bank.",
        "locked": "Payment for this order is already being processed and cannot be changed.",
        "no_destinations": "Transfer options are temporarily unavailable. Please contact the store.",
    },
    "uz": {
        "prompt_title": "{order_number} buyurtmangiz tasdiqlandi.",
        "items": "Mahsulotlar soni",
        "total": "To‘lov summasi",
        "choose": "Pul o‘tkazish uchun bankni tanlang:",
        "details_title": "To‘lov ma’lumotlari · {order_number}",
        "bank": "Bank",
        "type": "Hisob turi",
        "account": "Bank hisob raqami",
        "card": "Karta",
        "number": "Hisob raqami",
        "holder": "Hisob egasi",
        "transfer": "Aynan shu summani o‘tkazing",
        "after_transfer": "O‘tkazmadan so‘ng to‘lov chekini shu chatga yuboring.",
        "copy": "Raqamni nusxalash",
        "change": "Bankni almashtirish",
        "tracking": "Buyurtmani kuzatish",
        "selected": "Bank tanlandi.",
        "choose_again": "Pul o‘tkazish uchun bankni tanlang:",
        "invalid": "Bank tanlovi yaroqsiz. To‘lov ma’lumotlarini qayta yuborishni do‘kondan so‘rang.",
        "unavailable": "Bu variant mavjud emas. Boshqa bankni tanlang.",
        "locked": "Buyurtma to‘lovi qayta ishlanmoqda va uni o‘zgartirib bo‘lmaydi.",
        "no_destinations": "Pul o‘tkazish variantlari vaqtincha mavjud emas. Do‘kon bilan bog‘laning.",
    },
    "ru": {
        "prompt_title": "Заказ {order_number} оформлен.",
        "items": "Количество товаров",
        "total": "Итого к оплате",
        "choose": "Выберите банк для перевода:",
        "details_title": "Данные для оплаты · заказ {order_number}",
        "bank": "Банк",
        "type": "Тип реквизита",
        "account": "Банковский счёт",
        "card": "Карта",
        "number": "Номер реквизита",
        "holder": "Владелец счёта",
        "transfer": "Переведите точную сумму",
        "after_transfer": "После перевода отправьте подтверждение оплаты в этот чат.",
        "copy": "Скопировать номер",
        "change": "Сменить банк",
        "tracking": "Статус заказа",
        "selected": "Банк выбран.",
        "choose_again": "Выберите банк для перевода:",
        "invalid": "Выбор банка больше недействителен. Попросите магазин повторно отправить данные для оплаты.",
        "unavailable": "Этот вариант больше недоступен. Выберите другой банк.",
        "locked": "Оплата заказа уже обрабатывается и не может быть изменена.",
        "no_destinations": "Варианты перевода временно недоступны. Свяжитесь с магазином.",
    },
}


def payment_locale(value: str | None) -> str:
    locale = (value or "id").lower().split("-")[0]
    return locale if locale in DESTINATION_LOCALES else "id"


def payment_text(locale: str | None, key: str) -> str:
    return PAYMENT_COPY[payment_locale(locale)][key]


def normalize_account_number(value: str, destination_type: str) -> str:
    number = re.sub(r"[\s-]", "", value or "")
    if not number.isdigit():
        raise ValueError("account_number_digits_only")
    if destination_type == "card" and not 12 <= len(number) <= 19:
        raise ValueError("invalid_card_number_length")
    if destination_type == "bank_account" and not 8 <= len(number) <= 34:
        raise ValueError("invalid_bank_account_length")
    return number


def mask_account_number(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return "—"
    return f"•••• {digits[-4:]}"


def destination_snapshot(destination) -> dict:
    return {
        "bank_name": destination.bank_name,
        "destination_type": destination.destination_type,
        "account_number": destination.account_number,
        "holder_name": destination.holder_name,
    }


def destination_admin_payload(destination, *, include_number: bool = False) -> dict:
    payload = {
        "id": destination.id,
        "slot": destination.slot,
        "bank_name": destination.bank_name,
        "destination_type": destination.destination_type,
        "masked_account_number": mask_account_number(destination.account_number),
        "holder_name": destination.holder_name,
        "is_active": destination.is_active,
        "created_at": destination.created_at,
        "updated_at": destination.updated_at,
    }
    if include_number:
        payload["account_number"] = destination.account_number
    return payload


def _amount(amount: int, currency: str) -> str:
    return f"{amount:,}".replace(",", " ") + f" {currency}"


def payment_prompt_text(order, item_count: int, locale: str, tracking_link: str) -> str:
    copy = PAYMENT_COPY[payment_locale(locale)]
    lines = [
        copy["prompt_title"].format(order_number=order.order_number),
        f"{copy['items']}: {item_count}",
        f"{copy['total']}: {_amount(order.grand_total, order.currency)}",
        "",
        copy["choose"],
    ]
    if tracking_link:
        lines.extend(["", f"{copy['tracking']}: {tracking_link}"])
    return "\n".join(lines)


def payment_choice_keyboard(destinations: Iterable, token: str, locale: str) -> dict:
    rows = []
    for destination in destinations:
        rows.append(
            [
                {
                    "text": f"{destination.bank_name[:45]} ···· {destination.account_number[-4:]}",
                    "callback_data": (
                        f"bank:{token}:{destination.callback_key}:{payment_locale(locale)}"
                    ),
                }
            ]
        )
    return {"inline_keyboard": rows}


def payment_detail_text(order, snapshot: dict, locale: str) -> str:
    copy = PAYMENT_COPY[payment_locale(locale)]
    kind = copy["card"] if snapshot["destination_type"] == "card" else copy["account"]
    return "\n".join(
        [
            copy["details_title"].format(order_number=order.order_number),
            "",
            f"{copy['bank']}: {snapshot['bank_name']}",
            f"{copy['type']}: {kind}",
            f"{copy['number']}: {snapshot['account_number']}",
            f"{copy['holder']}: {snapshot['holder_name']}",
            "",
            f"{copy['transfer']}: {_amount(order.grand_total, order.currency)}",
            copy["after_transfer"],
        ]
    )


def payment_detail_keyboard(snapshot: dict, token: str, locale: str) -> dict:
    copy = PAYMENT_COPY[payment_locale(locale)]
    return {
        "inline_keyboard": [
            [{"text": copy["copy"], "copy_text": {"text": snapshot["account_number"]}}],
            [
                {
                    "text": copy["change"],
                    "callback_data": f"back:{token}:{payment_locale(locale)}",
                }
            ],
        ]
    }


def answer_locale_error(locale: str, key: str) -> str:
    return PAYMENT_COPY[payment_locale(locale)][key]
