"""m10: link catalog taxonomy and variants to CMS media assets.

The legacy image_url fields remain for read compatibility. New imports and
admin workflows use media_id as the source of truth and keep image_url as a
resolved local URL for existing clients.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("media_id", sa.String(length=32), nullable=True))
    op.create_index("ix_categories_media_id", "categories", ["media_id"])
    op.create_foreign_key(
        "fk_categories_media_id", "categories", "cms_media_assets", ["media_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("product_variants", sa.Column("media_id", sa.String(length=32), nullable=True))
    op.create_index("ix_product_variants_media_id", "product_variants", ["media_id"])
    op.create_foreign_key(
        "fk_product_variants_media_id", "product_variants", "cms_media_assets", ["media_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_variants_media_id", "product_variants", type_="foreignkey")
    op.drop_index("ix_product_variants_media_id", table_name="product_variants")
    op.drop_column("product_variants", "media_id")
    op.drop_constraint("fk_categories_media_id", "categories", type_="foreignkey")
    op.drop_index("ix_categories_media_id", table_name="categories")
    op.drop_column("categories", "media_id")
