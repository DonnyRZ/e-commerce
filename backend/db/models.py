import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def uid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    first_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    last_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    role: Mapped[str] = mapped_column(String(20), default="customer")
    preferred_locale: Mapped[str] = mapped_column(String(5), default="id")
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    seller_profile: Mapped[Optional["SellerProfile"]] = relationship(
        back_populates="user", uselist=False
    )


class SellerProfile(TimestampMixin, Base):
    __tablename__ = "seller_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    store_name: Mapped[str] = mapped_column(String(255), default="")
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="seller_profile")


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(20), default="category")
    department: Mapped[str] = mapped_column(String(50), default="", index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    media_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cms_media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped[Optional["Category"]] = relationship(remote_side="Category.id")
    translations: Mapped[list["CategoryTranslation"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class CategoryTranslation(Base):
    __tablename__ = "category_translations"
    __table_args__ = (UniqueConstraint("category_id", "locale"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(5))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    category: Mapped[Category] = relationship(back_populates="translations")


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    seller_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    product_type: Mapped[str] = mapped_column(String(20), default="general")
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    brand: Mapped[str] = mapped_column(String(120), default="")
    base_price: Mapped[int] = mapped_column(Integer, default=0)
    compare_at_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    media: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # Monotonic catalog revision used to reject stale CMS/editor writes.
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    # Demo catalog items are visible for storefront/showcase QA but must never
    # be treated as commercially available products.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    bestseller: Mapped[bool] = mapped_column(Boolean, default=False)
    new_arrival: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    translations: Mapped[list["ProductTranslation"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductTranslation(Base):
    __tablename__ = "product_translations"
    __table_args__ = (UniqueConstraint("product_id", "locale"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(5))
    name: Mapped[str] = mapped_column(String(255))
    short_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    product: Mapped[Product] = relationship(back_populates="translations")


class ProductVariant(TimestampMixin, Base):
    __tablename__ = "product_variants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    option_values: Mapped[dict] = mapped_column(JSONB, default=dict)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    price_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sale_price_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cms_media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="variants")


class Cart(TimestampMixin, Base):
    __tablename__ = "carts"
    __table_args__ = (
        Index(
            "uq_carts_user_id_not_null",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_carts_guest_token_not_null",
            "guest_token",
            unique=True,
            postgresql_where=text("guest_token IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    guest_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    cart_id: Mapped[str] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    cart: Mapped[Cart] = relationship(back_populates="items")


class TelegramBusinessConnection(Base):
    """Latest Telegram Business connection state for a linked store account."""

    __tablename__ = "telegram_business_connections"

    connection_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    business_user_id: Mapped[str] = mapped_column(String(32), default="")
    username: Mapped[str] = mapped_column(String(32), default="", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    can_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    can_read_messages: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TelegramCartInquiry(Base):
    """Server-priced Telegram request awaiting admin conversion into an order."""

    __tablename__ = "telegram_cart_inquiries"
    __table_args__ = (
        CheckConstraint(
            "source IN ('web', 'telegram_inbox')",
            name="ck_telegram_cart_inquiries_source",
        ),
        UniqueConstraint("cart_id", "idempotency_key", name="uq_telegram_inquiry_cart_idempotency"),
        UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_telegram_inquiry_conversation_idempotency",
        ),
        Index("ix_telegram_cart_inquiries_expires_status", "expires_at", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    cart_id: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="web", server_default="web")
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("telegram_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    locale: Mapped[str] = mapped_column(String(5), default="en")
    snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    order_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    telegram_connection_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramUpdateReceipt(Base):
    """Webhook update IDs ensure Telegram retries do not duplicate replies."""

    __tablename__ = "telegram_update_receipts"
    __table_args__ = (Index("ix_telegram_update_receipts_received_at", "received_at"),)

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelegramConversation(Base):
    """A Telegram Business private chat captured for the CMS inbox."""

    __tablename__ = "telegram_conversations"
    __table_args__ = (
        UniqueConstraint("connection_id", "chat_id", name="uq_telegram_conversations_connection_chat"),
        Index("ix_telegram_conversations_status_activity", "status", "last_message_at"),
        CheckConstraint(
            "locale_source IN ('web', 'direct_default', 'admin', 'legacy')",
            name="ck_telegram_conversations_locale_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("telegram_business_connections.connection_id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    customer_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    customer_username: Mapped[str] = mapped_column(String(64), default="")
    customer_name: Mapped[str] = mapped_column(String(160), default="")
    telegram_language_code: Mapped[str] = mapped_column(String(16), default="")
    locale: Mapped[str] = mapped_column(String(5), default="id")
    locale_source: Mapped[str] = mapped_column(
        String(20), default="legacy", server_default="legacy"
    )
    status: Mapped[str] = mapped_column(String(24), default="needs_admin", index=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_customer_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_admin_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TelegramInboxMessage(Base):
    """CMS transcript entry; Telegram file IDs remain server-side only."""

    __tablename__ = "telegram_inbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "chat_id", "telegram_message_id",
            name="uq_telegram_inbox_messages_telegram_message",
        ),
        Index("ix_telegram_inbox_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("telegram_conversations.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[str] = mapped_column(String(255), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger)
    update_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    sender_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    direction: Mapped[str] = mapped_column(String(12))
    source: Mapped[str] = mapped_column(String(12), default="telegram")
    message_type: Mapped[str] = mapped_column(String(12), default="text")
    text: Mapped[str] = mapped_column(Text, default="")
    rich_content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    media_group_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    photo_file_unique_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    photo_file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TelegramProductCandidate(Base):
    """Admin-selected catalog item awaiting explicit customer confirmation."""

    __tablename__ = "telegram_product_candidates"
    __table_args__ = (
        UniqueConstraint("callback_token", name="uq_telegram_product_candidates_callback_token"),
        Index("ix_telegram_product_candidates_conversation_status", "conversation_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("telegram_conversations.id", ondelete="CASCADE"), index=True
    )
    source_message_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("telegram_inbox_messages.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[str] = mapped_column(String(32), index=True)
    sku: Mapped[str] = mapped_column(String(80), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    option_values: Mapped[dict] = mapped_column(JSONB, default=dict)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    confirmation_source: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    callback_token: Mapped[str] = mapped_column(String(24))
    confirmation_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Wishlist(TimestampMixin, Base):
    __tablename__ = "wishlists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    items: Mapped[list["WishlistItem"]] = relationship(
        back_populates="wishlist", cascade="all, delete-orphan"
    )


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    wishlist_id: Mapped[str] = mapped_column(
        ForeignKey("wishlists.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))

    wishlist: Mapped[Wishlist] = relationship(back_populates="items")


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    guest_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipping_address: Mapped[dict] = mapped_column(JSONB, default=dict)
    shipping_method: Mapped[str] = mapped_column(String(80), default="")
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    shipping_amount: Mapped[int] = mapped_column(Integer, default=0)
    tax: Mapped[int] = mapped_column(Integer, default=0)
    grand_total: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    payment_state: Mapped[str] = mapped_column(String(20), default="unpaid")
    status: Mapped[str] = mapped_column(String(30), default="pending_payment", index=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    # opaque token required (with order_number) for guest order lookup
    guest_access_token: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    # cart that produced this order — exactly-once cart clearing on payment
    cart_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    order_source: Mapped[str] = mapped_column(String(30), default="checkout")
    fulfillment_mode: Mapped[str] = mapped_column(String(20), default="pre_order")
    preorder_estimate_days: Mapped[int] = mapped_column(Integer, default=21)
    telegram_conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("telegram_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # snapshot only — intentionally no FK to mutable catalog rows
    variant_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    seller_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sku: Mapped[str] = mapped_column(String(80), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    option_values: Mapped[dict] = mapped_column(JSONB, default=dict)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    unit_price: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    line_total: Mapped[int] = mapped_column(Integer, default=0)

    order: Mapped[Order] = relationship(back_populates="items")


class MarketplaceSettings(TimestampMixin, Base):
    __tablename__ = "marketplace_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="unconfigured")
    environment: Mapped[str] = mapped_column(String(12), default="local")
    event_type: Mapped[str] = mapped_column(String(40))
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    provider_error_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[str] = mapped_column(String(20), default="ok")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class PaymentDestination(TimestampMixin, Base):
    """A manually managed bank account/card that customers may transfer to."""

    __tablename__ = "payment_destinations"
    __table_args__ = (
        CheckConstraint("slot >= 0 AND slot < 4", name="ck_payment_destinations_slot"),
        CheckConstraint(
            "destination_type IN ('bank_account', 'card')",
            name="ck_payment_destinations_type",
        ),
        UniqueConstraint("slot", name="uq_payment_destinations_slot"),
        UniqueConstraint("callback_key", name="uq_payment_destinations_callback_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    slot: Mapped[int] = mapped_column(SmallInteger)
    callback_key: Mapped[str] = mapped_column(String(12))
    bank_name: Mapped[str] = mapped_column(String(100))
    destination_type: Mapped[str] = mapped_column(String(20))
    account_number: Mapped[str] = mapped_column(String(34))
    holder_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index(
            "uq_payments_one_active_order",
            "order_id",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('failed', 'cancelled', 'expired', 'refunded', 'reversed')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    destination_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("payment_destinations.id", ondelete="SET NULL"), nullable=True
    )
    destination_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    telegram_selection_token: Mapped[Optional[str]] = mapped_column(
        String(24), unique=True, nullable=True
    )
    telegram_payment_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    telegram_payment_status: Mapped[str] = mapped_column(
        String(24), default="not_sent", index=True
    )
    telegram_payment_error: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="unconfigured")
    environment: Mapped[str] = mapped_column(String(12), default="local")
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    merchant_trans_id: Mapped[str] = mapped_column(String(80), unique=True)
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    provider_document_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    merchant_prepare_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    merchant_confirm_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provider_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    failure_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # admin payment-review bookkeeping (Admin Core, M9)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


PaymentEvent.payment = relationship("Payment", back_populates="events")


class ManualPaymentEvidence(TimestampMixin, Base):
    """Private, admin-only transfer proof; intentionally separate from CMS media."""

    __tablename__ = "manual_payment_evidence"
    __table_args__ = (
        Index("ix_manual_payment_evidence_payment_created", "payment_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(180), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    mime_type: Mapped[str] = mapped_column(String(80), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    uploaded_by: Mapped[str] = mapped_column(String(32), index=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class TelegramPaymentNotificationOutbox(TimestampMixin, Base):
    """Durable delivery attempts for manual-payment Telegram prompts."""

    __tablename__ = "telegram_payment_notification_outbox"
    __table_args__ = (
        Index(
            "ix_telegram_payment_outbox_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_telegram_payment_outbox_payment_created",
            "payment_id",
            "created_at",
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'blocked', 'unavailable')",
            name="ck_telegram_payment_outbox_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(24), default="pending")
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)


class TelegramOrderNotificationOutbox(TimestampMixin, Base):
    """Durable, deduplicated Telegram notices for order state transitions."""

    __tablename__ = "telegram_order_notification_outbox"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "event_key", name="uq_telegram_order_notification_event"
        ),
        Index(
            "ix_telegram_order_notification_status_created",
            "status",
            "created_at",
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'unavailable')",
            name="ck_telegram_order_notification_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(180))
    event_type: Mapped[str] = mapped_column(
        String(32), default="legacy", server_default="legacy"
    )
    event_payload: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    message_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class OrderFulfillmentStage(TimestampMixin, Base):
    """Auditable two-leg fulfillment timeline for the single store operator."""

    __tablename__ = "order_fulfillment_stages"
    __table_args__ = (
        UniqueConstraint("order_id", "stage", name="uq_order_fulfillment_stage"),
        UniqueConstraint(
            "shipping_document_key", name="uq_order_fulfillment_shipping_document_key"
        ),
        Index("ix_order_fulfillment_order_stage", "order_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    # supplier_shipping | received_by_admin | customer_shipping | delivered
    stage: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    carrier: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    shipping_document_key: Mapped[Optional[str]] = mapped_column(
        String(180), nullable=True
    )
    shipping_document_filename: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    shipping_document_mime_type: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
    shipping_document_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    shipping_document_checksum: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acted_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_variant_id: Mapped[str] = mapped_column(
        ForeignKey("product_variants.id"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    # active | committed | released | expired
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    committed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # auditable link: set when this row is a committed replacement for an
    # expired/released reservation (the original row stays untouched)
    reacquired_from: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("inventory_reservations.id"), nullable=True
    )


class SellerOrderFulfillment(TimestampMixin, Base):
    __tablename__ = "seller_order_fulfillments"
    __table_args__ = (UniqueConstraint("order_id", "seller_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    # pending | processing | shipped | delivered | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    shipping_carrier: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CmsMediaAsset(TimestampMixin, Base):
    __tablename__ = "cms_media_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    storage_provider: Mapped[str] = mapped_column(String(20), default="local")
    storage_key: Mapped[str] = mapped_column(String(160), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    mime_type: Mapped[str] = mapped_column(String(80), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class CmsMediaTranslation(Base):
    __tablename__ = "cms_media_translations"
    __table_args__ = (UniqueConstraint("media_id", "locale"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    media_id: Mapped[str] = mapped_column(
        ForeignKey("cms_media_assets.id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(5))
    alt_text: Mapped[str] = mapped_column(String(255), default="")
    caption: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class CmsContentEntry(TimestampMixin, Base):
    __tablename__ = "cms_content_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    # hero | announcement | banner | story | page | faq_item | nav_item |
    # footer_group | footer_item | homepage_section | department_visual
    content_type: Mapped[str] = mapped_column(String(40), index=True)
    internal_name: Mapped[str] = mapped_column(String(255), default="")
    slug: Mapped[str] = mapped_column(String(160), default="", index=True)
    # draft | published | archived
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    placement: Mapped[str] = mapped_column(String(80), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    media_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cms_media_assets.id", ondelete="SET NULL"), nullable=True
    )
    cta_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    secondary_cta_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    draft_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class CmsContentTranslation(TimestampMixin, Base):
    __tablename__ = "cms_content_translations"
    __table_args__ = (UniqueConstraint("entry_id", "locale"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("cms_content_entries.id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(5))
    title: Mapped[str] = mapped_column(String(500), default="")
    eyebrow: Mapped[str] = mapped_column(String(255), default="")
    subtitle: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    cta_label: Mapped[str] = mapped_column(String(120), default="")
    secondary_cta_label: Mapped[str] = mapped_column(String(120), default="")
    alt_text: Mapped[str] = mapped_column(String(255), default="")


class CmsRevision(Base):
    __tablename__ = "cms_revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    content_type: Mapped[str] = mapped_column(String(40), index=True)
    content_id: Mapped[str] = mapped_column(String(32), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    # created | saved_draft | published | unpublished | archived | restored
    action: Mapped[str] = mapped_column(String(20))
    snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class CmsAuditLog(Base):
    __tablename__ = "cms_audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="")
    target_id: Mapped[str] = mapped_column(String(40), default="")
    safe_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class StatusCheck(Base):
    __tablename__ = "status_checks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    client_name: Mapped[str] = mapped_column(String(120))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class UserAddress(TimestampMixin, Base):
    __tablename__ = "user_addresses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(80), default="")
    recipient_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    address_line_1: Mapped[str] = mapped_column(String(255), default="")
    address_line_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(120), default="")
    state_province: Mapped[str] = mapped_column(String(120), default="")
    postal_code: Mapped[str] = mapped_column(String(20), default="")
    country_code: Mapped[str] = mapped_column(String(2), default="ID")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    identifier: Mapped[str] = mapped_column(String(300), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
