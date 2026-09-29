"""Add reversible order archiving."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t9u0v1w2x3y"
down_revision: Union[str, None] = "s8t9u0v1w2x3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.create_index("ix_orders_archived_at", "orders", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_archived_at", table_name="orders")
    op.drop_column("orders", "archived_at")
