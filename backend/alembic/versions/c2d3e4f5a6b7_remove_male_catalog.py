"""Remove male-scoped catalog nodes from the single-store catalog.

The store scope is Muslimah-only. The old Batik Pria and Parfum Pria
taxonomy nodes were never assigned products, but they were already present in
the production catalog and therefore need an explicit, idempotent cleanup.
Historical orders are not touched: order items keep catalog snapshots and do
not reference categories.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REMOVED_SLUGS = (
    "batik-pria",
    "batik-koko-kemko",
    "kemeja-batik-lengan-panjang",
    "kemeja-batik-lengan-pendek",
    "jas-blazer-batik-luara",
    "sarung-batik",
    "parfum-pria",
    "oud-woody",
    "kasturi-rempah",
    "fresh-citrus-aquatic",
    "attar-perfume-oil-premium",
)
GROUP_SLUGS = {"batik-pria", "parfum-pria"}


def _params(prefix: str, values: Sequence[str]) -> tuple[str, dict[str, str]]:
    names = [f":{prefix}{index}" for index in range(len(values))]
    return ", ".join(names), {f"{prefix}{index}": value for index, value in enumerate(values)}


def upgrade() -> None:
    connection = op.get_bind()
    placeholders, slug_params = _params("slug_", REMOVED_SLUGS)
    rows = connection.execute(
        sa.text(
            f"SELECT id, slug, kind, parent_id FROM categories "
            f"WHERE slug IN ({placeholders})"
        ),
        slug_params,
    ).mappings().all()
    if not rows:
        return

    ids = [row["id"] for row in rows]
    id_placeholders, id_params = _params("id_", ids)
    product_count = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM products WHERE category_id IN ({id_placeholders})"
        ),
        id_params,
    ).scalar_one()
    if product_count:
        raise RuntimeError(
            "Refusing to remove male catalog nodes because products are still assigned. "
            "Move or archive those products first."
        )

    group_ids = [row["id"] for row in rows if row["slug"] in GROUP_SLUGS]
    if group_ids:
        group_placeholders, group_params = _params("group_", group_ids)
        child_rows = connection.execute(
            sa.text(
                f"SELECT id, slug FROM categories WHERE parent_id IN ({group_placeholders})"
            ),
            group_params,
        ).mappings().all()
        unexpected = [row["slug"] for row in child_rows if row["slug"] not in REMOVED_SLUGS]
        if unexpected:
            raise RuntimeError(
                "Refusing to remove male catalog groups with unlisted children: "
                + ", ".join(sorted(unexpected))
            )

    # Delete leaves first so the self-referencing parent foreign key remains
    # valid on PostgreSQL installations that enforce it immediately.
    for kind in ("category", "group"):
        kind_rows = [row["id"] for row in rows if row["kind"] == kind]
        if not kind_rows:
            continue
        kind_placeholders, kind_params = _params("kind_", kind_rows)
        connection.execute(
            sa.text(f"DELETE FROM categories WHERE id IN ({kind_placeholders})"),
            kind_params,
        )


def downgrade() -> None:
    # These are business taxonomy rows, not schema defaults. Recreating them
    # without approved translations/media would be unsafe; application release
    # rollback does not require restoring removed catalog data.
    pass
