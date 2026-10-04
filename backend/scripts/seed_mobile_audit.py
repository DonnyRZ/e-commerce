"""Synthetic CMS browser fixtures for the isolated Compose stack only."""

import asyncio
from datetime import timedelta
from sqlalchemy import select
from db.models import (
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    TelegramBusinessConnection,
    TelegramCartInquiry,
    TelegramConversation,
    TelegramInboxMessage,
    TelegramProductCandidate,
    User,
    utcnow,
)
from db.session import SessionLocal
from config import APP_ENV, TELEGRAM_STORE_USERNAME

if APP_ENV not in {"development", "test"}:
    raise RuntimeError(
        "Mobile audit fixtures may only be seeded in an isolated development/test database"
    )


async def seed():
    async with SessionLocal() as s:
        if await s.get(TelegramBusinessConnection, "mobile-audit-local"):
            print("Local mobile fixtures already present")
            return
        c = TelegramBusinessConnection(
            connection_id="mobile-audit-local",
            business_user_id="999999",
            username=TELEGRAM_STORE_USERNAME,
            is_enabled=True,
            can_reply=True,
            can_read_messages=True,
        )
        s.add(c)
        await s.flush()
        chat = TelegramConversation(
            id="a" * 32,
            connection_id=c.connection_id,
            chat_id=888888,
            customer_name="Customer audit mobile · Nama panjang",
            customer_username="customer_mobile_audit",
            locale="id",
            locale_source="admin",
            status="needs_admin",
            last_customer_message_at=utcnow(),
        )
        s.add(chat)
        await s.flush()
        for i in range(14):
            s.add(
                TelegramInboxMessage(
                    conversation_id=chat.id,
                    connection_id=c.connection_id,
                    chat_id=chat.chat_id,
                    telegram_message_id=9000 + i,
                    direction="inbound" if i % 2 == 0 else "outbound",
                    source="telegram",
                    message_type="text",
                    text=(
                        (
                            "Apakah produk tersedia ukuran M? "
                            + (
                                "https://example.com/" + "panjang" * 20
                                if i == 12
                                else "Saya ingin memesan untuk keluarga."
                            )
                        )
                        if i % 2 == 0
                        else "Tersedia, silakan pilih ukuran dan warna."
                    ),
                    created_at=utcnow() - timedelta(minutes=15 - i),
                )
            )
        product = await s.scalar(select(Product).where(Product.status == "active"))
        product.is_demo = False
        variant = await s.scalar(
            select(ProductVariant).where(
                ProductVariant.product_id == product.id,
                ProductVariant.is_active == True,
            )
        )
        customer = await s.scalar(select(User).where(User.role == "customer"))
        candidate = TelegramProductCandidate(
            id="b" * 32,
            conversation_id=chat.id,
            product_id=product.id,
            variant_id=variant.id,
            sku=variant.sku,
            product_name="Produk audit mobile",
            option_values=variant.option_values,
            quantity=1,
            status="confirmed",
            confirmation_source="admin",
            callback_token="local-audit-confirmed",
        )
        s.add(candidate)
        inquiry = TelegramCartInquiry(
            reference="SC-" + "C" * 32,
            source="telegram_inbox",
            conversation_id=chat.id,
            idempotency_key="local-mobile-audit",
            locale="id",
            status="sent",
            telegram_connection_id=c.connection_id,
            telegram_chat_id=chat.chat_id,
            delivered_at=utcnow(),
            snapshot={
                "items": [
                    {
                        "sku": variant.sku,
                        "name": "Produk audit mobile",
                        "quantity": 1,
                        "unit_price": product.base_price,
                        "line_total": product.base_price,
                        "option_values": variant.option_values,
                        "availability": "pre_order",
                        "_candidate_id": candidate.id,
                    }
                ],
                "subtotal": product.base_price,
                "currency": product.currency,
                "item_count": 1,
                "_candidate_ids": [candidate.id],
                "_customer": {
                    "name": chat.customer_name,
                    "username": chat.customer_username,
                },
            },
        )
        s.add(inquiry)
        for i, status in enumerate(
            [
                "pending_payment",
                "payment_review",
                "paid",
                "supplier_shipping",
                "received_by_admin",
                "customer_shipping",
                "delivered",
            ]
        ):
            order = Order(
                order_number=f"MOBILE-AUDIT-{i+1}",
                user_id=customer.id,
                order_source="telegram_inbox",
                telegram_conversation_id=chat.id,
                shipping_address={
                    "recipient_name": chat.customer_name,
                    "phone": "+998901234567",
                    "address_line_1": "Alamat audit lokal, tidak digunakan untuk pengiriman",
                    "city": "Tashkent",
                    "country_code": "UZ",
                },
                shipping_method="manual",
                subtotal=product.base_price,
                grand_total=product.base_price,
                currency=product.currency,
                status=status,
                payment_state="paid" if i > 1 else "unpaid",
            )
            s.add(order)
            await s.flush()
            s.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    variant_id=variant.id,
                    seller_id=product.seller_id,
                    sku=variant.sku,
                    product_name="Produk audit mobile",
                    quantity=1,
                    unit_price=product.base_price,
                    line_total=product.base_price,
                    option_values=variant.option_values,
                )
            )
            s.add(
                Payment(
                    order_id=order.id,
                    provider="manual_transfer",
                    environment="local",
                    currency=product.currency,
                    amount=product.base_price,
                    status="paid" if i > 1 else "pending",
                    merchant_trans_id=f"LOCAL-MOBILE-AUDIT-{i+1}",
                )
            )
        await s.commit()
        print("Created isolated local chat, pending inquiry and seven order stages")


asyncio.run(seed())
