"""configure homepage merchandising to use catalog product references"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m2n3o4p5q6r7"
down_revision: Union[str, None] = "l7m8n9o0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    hero_product = bind.execute(
        sa.text(
            """
            SELECT id FROM products
            WHERE status = 'active'
            ORDER BY featured DESC, created_at DESC, id DESC
            LIMIT 1
            """
        )
    ).scalar()

    if hero_product:
        bind.execute(
            sa.text(
                """
                UPDATE cms_content_entries
                SET payload = CAST(jsonb_build_object('product_id', CAST(:product_id AS text)) AS json)
                WHERE content_type = 'hero'
                  AND slug = 'home-hero'
                  AND (
                    payload IS NULL
                    OR NOT (CAST(payload AS jsonb) ? 'product_id')
                  )
                """
            ),
            {"product_id": hero_product},
        )

    defaults = {
        "new_arrivals": {
            "id": "Pilihan untukmu",
            "en": "Picks for you",
            "uz": "Siz uchun tanlovlar",
            "ru": "Подборка для вас",
            "payload": '{"source": "catalog", "sort": "newest", "limit": 8}',
        },
        "best_sellers": {
            "id": "Koleksi pilihan",
            "en": "Curated collection",
            "uz": "Tanlangan kolleksiya",
            "ru": "Избранная коллекция",
            "payload": '{"source": "catalog", "sort": "featured", "limit": 8}',
        },
    }
    for slug, data in defaults.items():
        entry_id = bind.execute(
            sa.text(
                """
                UPDATE cms_content_entries
                SET payload = CASE
                    WHEN payload IS NULL OR CAST(payload AS jsonb) = '{}'::jsonb THEN CAST(:payload AS json)
                    ELSE payload
                END
                WHERE content_type = 'homepage_section' AND slug = :slug
                RETURNING id
                """
            ),
            {"slug": slug, "payload": data["payload"]},
        ).scalar()
        if not entry_id:
            continue
        for locale in ("id", "en", "uz", "ru"):
            bind.execute(
                sa.text(
                    """
                    UPDATE cms_content_translations
                    SET title = :title
                    WHERE entry_id = :entry_id AND locale = :locale
                      AND lower(title) IN ('new arrivals', 'koleksi terbaru', 'best sellers', 'terlaris')
                    """
                ),
                {"entry_id": entry_id, "locale": locale, "title": data[locale]},
            )

    bind.execute(
        sa.text(
            """
            UPDATE cms_content_entries
            SET is_visible = false
            WHERE content_type = 'homepage_section'
              AND slug = 'stories'
              AND lower(internal_name) = 'section: stories'
            """
        )
    )


def downgrade() -> None:
    # This is a content configuration migration. Do not restore operator-edited
    # titles, visibility, or product references on downgrade.
    pass
