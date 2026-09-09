from typing import Any, Dict, List, Literal, Optional

from pydantic import EmailStr, Field

from models.base import BaseDocument, PyObjectId

UserRole = Literal["customer", "seller", "admin"]
ProductType = Literal["apparel", "skincare", "general"]
OrderStatus = Literal[
    "pending_payment",
    "paid",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
]
PaymentStatus = Literal["unpaid", "pending", "success", "failure", "refunded"]
ProductStatus = Literal["draft", "active", "archived"]

LocalizedContent = Dict[str, Dict[str, str]]


class User(BaseDocument):
    email: EmailStr
    full_name: str = ""
    role: UserRole = "customer"
    preferred_locale: str = "id"
    password_hash: Optional[str] = None
    is_active: bool = True


class Category(BaseDocument):
    kind: Literal["department", "category"] = "category"
    department: str = ""
    slug: str
    translations: LocalizedContent = Field(default_factory=dict)
    parent_id: Optional[PyObjectId] = None
    image_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class MediaAsset(BaseDocument):
    url: str = ""
    alt: str = ""
    sort_order: int = 0


class Product(BaseDocument):
    seller_id: PyObjectId
    category_id: PyObjectId
    product_type: ProductType = "general"
    slug: str = ""
    translations: LocalizedContent = Field(default_factory=dict)
    brand: str = ""
    base_price: int = 0
    compare_at_price: Optional[int] = None
    currency: str = "IDR"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    media: List[Dict[str, Any]] = Field(default_factory=list)
    status: ProductStatus = "draft"
    featured: bool = False
    bestseller: bool = False
    new_arrival: bool = False


class ProductVariant(BaseDocument):
    product_id: PyObjectId
    sku: str
    option_values: Dict[str, str] = Field(default_factory=dict)
    stock_quantity: int = 0
    price_override: Optional[int] = None
    sale_price_override: Optional[int] = None
    image_url: Optional[str] = None
    is_active: bool = True


class CartItem(BaseDocument):
    product_id: PyObjectId
    variant_id: PyObjectId
    quantity: int = Field(default=1, ge=1)


class Cart(BaseDocument):
    user_id: Optional[PyObjectId] = None
    guest_token: Optional[str] = None
    items: List[CartItem] = Field(default_factory=list)


class Wishlist(BaseDocument):
    user_id: PyObjectId
    product_ids: List[PyObjectId] = Field(default_factory=list)


class OrderItemSnapshot(BaseDocument):
    product_id: PyObjectId
    seller_id: PyObjectId
    sku: str
    product_name: str
    option_values: Dict[str, str] = Field(default_factory=dict)
    image_url: Optional[str] = None
    unit_price: int
    quantity: int = Field(ge=1)
    line_total: int


class AddressSnapshot(BaseDocument):
    recipient_name: str = ""
    phone: str = ""
    line1: str = ""
    line2: str = ""
    city: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = ""


class Order(BaseDocument):
    order_number: str
    user_id: Optional[PyObjectId] = None
    guest_email: Optional[EmailStr] = None
    items: List[OrderItemSnapshot] = Field(default_factory=list)
    shipping_address: AddressSnapshot = Field(default_factory=AddressSnapshot)
    shipping_method: str = ""
    subtotal: int = 0
    discount: int = 0
    shipping_amount: int = 0
    tax: int = 0
    grand_total: int = 0
    currency: str = "IDR"
    payment_state: PaymentStatus = "unpaid"
    status: OrderStatus = "pending_payment"
    idempotency_key: Optional[str] = None


class MarketplaceSettings(BaseDocument):
    key: str = "global"
    data: Dict[str, Any] = Field(default_factory=dict)
