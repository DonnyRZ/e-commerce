"""make all orders explicit pre-orders with a stable estimate"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "l7m8n9o0p1q2"
down_revision: Union[str, None] = "k6l7m8n9o0p1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "fulfillment_mode",
            sa.String(length=20),
            nullable=False,
            server_default="pre_order",
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "preorder_estimate_days",
            sa.Integer(),
            nullable=False,
            server_default="21",
        ),
    )
    op.alter_column("orders", "fulfillment_mode", server_default=None)
    op.alter_column("orders", "preorder_estimate_days", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "preorder_estimate_days")
    op.drop_column("orders", "fulfillment_mode")
