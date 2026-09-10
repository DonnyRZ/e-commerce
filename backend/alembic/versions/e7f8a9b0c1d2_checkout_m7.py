"""checkout m7: inventory reservations + order guest token/cart link + variant snapshot

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("guest_access_token", sa.String(length=80), nullable=True)
    )
    op.add_column("orders", sa.Column("cart_id", sa.String(length=32), nullable=True))
    op.create_unique_constraint(
        "uq_orders_guest_access_token", "orders", ["guest_access_token"]
    )
    op.add_column(
        "order_items", sa.Column("variant_id", sa.String(length=32), nullable=True)
    )
    op.create_table(
        "inventory_reservations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("product_variant_id", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_inventory_reservations_order_id_orders",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_variant_id"],
            ["product_variants.id"],
            name="fk_inventory_reservations_product_variant_id_product_variants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_reservations"),
    )
    op.create_index(
        "ix_inventory_reservations_order_id", "inventory_reservations", ["order_id"]
    )
    op.create_index(
        "ix_inventory_reservations_product_variant_id",
        "inventory_reservations",
        ["product_variant_id"],
    )
    op.create_index(
        "ix_inventory_reservations_status", "inventory_reservations", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_reservations_status", table_name="inventory_reservations")
    op.drop_index(
        "ix_inventory_reservations_product_variant_id",
        table_name="inventory_reservations",
    )
    op.drop_index("ix_inventory_reservations_order_id", table_name="inventory_reservations")
    op.drop_table("inventory_reservations")
    op.drop_column("order_items", "variant_id")
    op.drop_constraint("uq_orders_guest_access_token", "orders")
    op.drop_column("orders", "cart_id")
    op.drop_column("orders", "guest_access_token")
