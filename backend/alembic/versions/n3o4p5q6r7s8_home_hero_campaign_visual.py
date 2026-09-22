"""point homepage hero at the audited catalog product and campaign visual"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "n3o4p5q6r7s8"
down_revision: Union[str, None] = "m2n3o4p5q6r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    product_id = bind.execute(
        sa.text(
            """
            SELECT id FROM products
            WHERE status = 'active' AND slug = 'smooth-cotton-crew-neck-sweater-4aa1f9'
            LIMIT 1
            """
        )
    ).scalar()
    if not product_id:
        return

    bind.execute(
        sa.text(
            """
            UPDATE cms_content_entries
            SET payload = CAST(jsonb_build_object(
                'product_id', CAST(:product_id AS text),
                'hero_asset_url', CAST(:hero_asset_url AS text)
            ) AS json)
            WHERE content_type = 'hero' AND slug = 'home-hero'
            """
        ),
        {
            "product_id": product_id,
                "hero_asset_url": "/brand/generated/home-hero-smooth-cotton-collection.png",
        },
    )


def downgrade() -> None:
    # Do not replace an operator-selected hero on downgrade.
    pass
