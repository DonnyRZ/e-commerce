"""Flatten catalog taxonomy to department -> category.

The earlier release allowed an optional group level. The store now uses a
single product-facing category level. The existing Shoe/Skechers node is
preserved by converting it to a category, while former grouping nodes are
removed after their children are re-parented directly to the department.
Product and media IDs are not changed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    groups = connection.execute(
        sa.text(
            "SELECT id, parent_id, department, slug FROM categories "
            "WHERE kind = 'group' ORDER BY id"
        )
    ).mappings().all()

    for group in groups:
        if group["parent_id"] is None:
            raise RuntimeError(
                f"Cannot flatten orphaned catalog group {group['slug']}: missing department parent"
            )

        product_count = connection.execute(
            sa.text("SELECT COUNT(*) FROM products WHERE category_id = :group_id"),
            {"group_id": group["id"]},
        ).scalar_one()

        # Move former group children to the department before deciding what
        # to do with the group row. This preserves all product categories.
        connection.execute(
            sa.text(
                "UPDATE categories SET parent_id = :parent_id "
                "WHERE parent_id = :group_id"
            ),
            {"parent_id": group["parent_id"], "group_id": group["id"]},
        )

        # Skechers is an actual product category in the current Shoe catalog.
        # Preserve any existing direct product assignment as well. Other
        # grouping labels (for example the former Batik/Parfum segment rows)
        # are not product categories and can be removed after their children
        # have been flattened.
        preserve_as_category = (
            (group["department"] == "shoe" and group["slug"] == "skechers")
            or bool(product_count)
        )
        if preserve_as_category:
            connection.execute(
                sa.text("UPDATE categories SET kind = 'category' WHERE id = :group_id"),
                {"group_id": group["id"]},
            )
        else:
            connection.execute(
                sa.text("DELETE FROM categories WHERE id = :group_id"),
                {"group_id": group["id"]},
            )


def downgrade() -> None:
    # Converting the rows back would require guessing which categories were
    # former groups and would risk moving products. Release rollback does not
    # require destructive taxonomy reversal.
    pass
