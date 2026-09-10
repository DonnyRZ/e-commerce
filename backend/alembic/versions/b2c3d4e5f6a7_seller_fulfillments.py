"""m8: seller order fulfillments

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "seller_profiles", sa.Column("description", sa.Text(), nullable=True)
    )
    op.add_column(
        "seller_profiles",
        sa.Column("contact_phone", sa.String(length=40), nullable=True),
    )
    op.create_table(
        "seller_order_fulfillments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("seller_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("tracking_number", sa.String(length=120), nullable=True),
        sa.Column("shipping_carrier", sa.String(length=80), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"],
            name="fk_seller_order_fulfillments_order_id_orders",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"], ["users.id"],
            name="fk_seller_order_fulfillments_seller_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_seller_order_fulfillments"),
        sa.UniqueConstraint("order_id", "seller_id", name="uq_seller_order_fulfillments_order_seller"),
    )
    op.create_index("ix_seller_order_fulfillments_order_id", "seller_order_fulfillments", ["order_id"])
    op.create_index("ix_seller_order_fulfillments_seller_id", "seller_order_fulfillments", ["seller_id"])
    op.create_index("ix_seller_order_fulfillments_status", "seller_order_fulfillments", ["status"])


def downgrade() -> None:
    op.drop_column("seller_profiles", "contact_phone")
    op.drop_column("seller_profiles", "description")
    op.drop_index("ix_seller_order_fulfillments_status", table_name="seller_order_fulfillments")
    op.drop_index("ix_seller_order_fulfillments_seller_id", table_name="seller_order_fulfillments")
    op.drop_index("ix_seller_order_fulfillments_order_id", table_name="seller_order_fulfillments")
    op.drop_table("seller_order_fulfillments")
