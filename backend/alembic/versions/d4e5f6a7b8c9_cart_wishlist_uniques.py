"""cart wishlist unique constraints

Revision ID: d4e5f6a7b8c9
Revises: a207cd2314b3
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "a207cd2314b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_cart_items_cart_variant", "cart_items", ["cart_id", "variant_id"]
    )
    op.create_unique_constraint(
        "uq_wishlist_items_wishlist_product",
        "wishlist_items",
        ["wishlist_id", "product_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_wishlist_items_wishlist_product", "wishlist_items")
    op.drop_constraint("uq_cart_items_cart_variant", "cart_items")
