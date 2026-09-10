"""m7.1: reservation reacquisition audit link

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_reservations",
        sa.Column("reacquired_from", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_reservations_reacquired_from",
        "inventory_reservations",
        "inventory_reservations",
        ["reacquired_from"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inventory_reservations_reacquired_from",
        "inventory_reservations",
        type_="foreignkey",
    )
    op.drop_column("inventory_reservations", "reacquired_from")
