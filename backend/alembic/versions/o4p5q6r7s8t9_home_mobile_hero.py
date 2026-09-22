"""add the dedicated mobile homepage hero asset"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "o4p5q6r7s8t9"
down_revision: Union[str, None] = "n3o4p5q6r7s8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE cms_content_entries
            SET payload = CAST(jsonb_build_object(
                'product_id', payload->>'product_id',
                'hero_asset_url', COALESCE(payload->>'hero_asset_url', '/brand/generated/home-hero-smooth-cotton-collection.png'),
                'hero_mobile_asset_url', '/brand/generated/home-hero-smooth-cotton-mobile.png'
            ) AS json)
            WHERE content_type = 'hero' AND slug = 'home-hero'
            """
        )
    )


def downgrade() -> None:
    # Keep the desktop campaign intact if this migration is rolled back.
    pass
