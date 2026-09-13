"""Mark showcase catalog items explicitly as demo content.

The storefront is intentionally live before the product master and CLICK are
ready. Existing catalog rows are showcase data and must remain visible, but
they must not be mistaken for sellable inventory or enter checkout.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Per the approved storefront scope, every product currently in the
    # database is showcase/demo content. Future products default to false and
    # can be published as real catalog items through Admin.
    op.execute(sa.text("UPDATE products SET is_demo = TRUE"))
    op.alter_column("products", "is_demo", server_default=None)
    op.create_index("ix_products_is_demo", "products", ["is_demo"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_is_demo", table_name="products")
    op.drop_column("products", "is_demo")
