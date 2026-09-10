import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="variants")


class Cart(TimestampMixin, Base):
    __tablename__ = "carts"

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
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    # opaque token required (with order_number) for guest order lookup
    guest_access_token: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    # cart that produced this order — exactly-once cart clearing on payment
    cart_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

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
    provider: Mapped[str] = mapped_column(String(20), default="click")
    environment: Mapped[str] = mapped_column(String(12), default="mock")
    event_type: Mapped[str] = mapped_column(String(40))
    click_trans_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provider_error_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[str] = mapped_column(String(20), default="ok")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="click")
    environment: Mapped[str] = mapped_column(String(12), default="mock")
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    merchant_trans_id: Mapped[str] = mapped_column(String(80), unique=True)
    click_trans_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    click_paydoc_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
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
