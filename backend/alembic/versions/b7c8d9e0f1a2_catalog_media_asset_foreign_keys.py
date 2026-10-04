"""Ensure catalog media references after the CMS media table exists.

The legacy media-link revision can run before the CMS-core branch on a fresh
database, so it defers these foreign keys when the target table is not present.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "cms_media_assets" not in tables:
        raise RuntimeError("CMS core must create cms_media_assets before catalog media links")

    foreign_keys = {
        "categories": {item["name"] for item in inspector.get_foreign_keys("categories")},
        "product_variants": {item["name"] for item in inspector.get_foreign_keys("product_variants")},
    }
    if "fk_categories_media_id" not in foreign_keys["categories"]:
        op.create_foreign_key(
            "fk_categories_media_id",
            "categories",
            "cms_media_assets",
            ["media_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "fk_product_variants_media_id" not in foreign_keys["product_variants"]:
        op.create_foreign_key(
            "fk_product_variants_media_id",
            "product_variants",
            "cms_media_assets",
            ["media_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Preserve foreign-key integrity during a code rollback. The earlier media
    # link revision owns dropping these constraints if that revision is also
    # rolled back.
    pass
