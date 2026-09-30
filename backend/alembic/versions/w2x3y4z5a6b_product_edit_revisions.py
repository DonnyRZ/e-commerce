"""Add monotonic revisions for concurrent product editing."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w2x3y4z5a6b"
down_revision: Union[str, None] = "v1w2x3y4z5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("products", "revision")
