"""configure the launch homepage with four manually curated product sections"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p5q6r7s8t9u0"
down_revision: Union[str, None] = "o4p5q6r7s8t9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LOCALES = {
    "en": {
        "best_sellers": "Best Sellers",
        "new_arrivals": "New Arrivals",
        "skincare": "Skincare Essentials",
        "daily_style": "Everyday Style",
    },
    "id": {
        "best_sellers": "Terlaris",
        "new_arrivals": "Koleksi Terbaru",
        "skincare": "Rawat Kulitmu",
        "daily_style": "Gaya Sehari-hari",
    },
    "uz": {
        "best_sellers": "Eng ko‘p sotilganlar",
        "new_arrivals": "Yangi kelganlar",
        "skincare": "Teri parvarishi",
        "daily_style": "Kundalik uslub",
    },
    "ru": {
        "best_sellers": "Бестселлеры",
        "new_arrivals": "Новинки",
        "skincare": "Уход за кожей",
        "daily_style": "Повседневный стиль",
    },
}

PRODUCT_SLUGS = {
    "best_sellers": (
        "smooth-cotton-crew-neck-sweater-4aa1f9",
        "mini-cable-crew-neck-cardigan-7f6c29",
        "skechers-d-lux-walker-3-0-5290c0",
        "safi-age-defy-sensitive-biome-calming-gel-45gr-a0ed8c",
    ),
    "new_arrivals": (
        "safi-acne-expert-acne-treatment-gel-bf9f7e",
        "safi-acne-expert-sebum-control-fluid-c0e878",
        "safi-acne-expert-clarifying-2-in-1-cleanser-4051de",
        "safi-age-defy-sensitive-biome-calming-gel-45gr-a0ed8c",
    ),
    "skincare": (
        "safi-age-defy-sensitive-biome-balancing-cleanser-100ml-b90220",
        "safi-acne-expert-sebum-control-fluid-c0e878",
        "safi-age-defy-sensitive-biome-soothing-serum-30ml-9ff972",
        "safi-age-defy-sensitive-biome-calming-gel-45gr-a0ed8c",
    ),
    "daily_style": (
        "smooth-cotton-crew-neck-sweater-97d9db",
        "light-souffle-yarn-relaxed-cardigan-7651f5",
        "pocketable-uv-protection-parka-water-repellent-nanodesign-0153f0",
        "utility-short-jacket-58a69a",
    ),
}

SORT_ORDERS = {
    "best_sellers": 3,
    "new_arrivals": 4,
    "skincare": 5,
    "daily_style": 6,
}


def _product_ids(bind, slugs: tuple[str, ...]) -> list[str]:
    query = sa.text(
        """
        SELECT id, slug
        FROM products
        WHERE status = 'active' AND slug IN :slugs
        """
    ).bindparams(sa.bindparam("slugs", expanding=True))
    rows = bind.execute(query, {"slugs": list(slugs)}).mappings().all()
    by_slug = {row["slug"]: row["id"] for row in rows}
    return [by_slug[slug] for slug in slugs if slug in by_slug]


def _prepare_legacy_rows(bind) -> None:
    for legacy, canonical in (
        ("curated_primary", "new_arrivals"),
        ("curated_secondary", "best_sellers"),
    ):
        canonical_exists = bind.execute(
            sa.text(
                """
                SELECT id
                FROM cms_content_entries
                WHERE content_type = 'homepage_section' AND slug = :slug
                LIMIT 1
                """
            ),
            {"slug": canonical},
        ).scalar()
        legacy_ids = bind.execute(
            sa.text(
                """
                SELECT id
                FROM cms_content_entries
                WHERE content_type = 'homepage_section' AND slug = :legacy
                ORDER BY created_at, id
                """
            ),
            {"legacy": legacy},
        ).scalars().all()
        if not canonical_exists:
            if legacy_ids:
                bind.execute(
                    sa.text(
                        """
                        UPDATE cms_content_entries
                        SET slug = :canonical
                        WHERE id = :entry_id
                        """
                    ),
                    {"canonical": canonical, "entry_id": legacy_ids[0]},
                )
                for duplicate_id in legacy_ids[1:]:
                    bind.execute(
                        sa.text(
                            """
                            UPDATE cms_content_entries
                            SET status = 'archived', is_visible = false
                            WHERE id = :entry_id
                            """
                        ),
                        {"entry_id": duplicate_id},
                    )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE cms_content_entries
                    SET status = 'archived', is_visible = false
                    WHERE content_type = 'homepage_section' AND slug = :legacy
                    """
                ),
                {"legacy": legacy},
            )


def _upsert_section(bind, slug: str, product_ids: list[str]) -> None:
    row = bind.execute(
        sa.text(
            """
            SELECT id, draft_snapshot
            FROM cms_content_entries
            WHERE content_type = 'homepage_section' AND slug = :slug
            ORDER BY created_at, id
            LIMIT 1
            """
        ),
        {"slug": slug},
    ).mappings().first()
    if row and row["draft_snapshot"] is not None:
        # Never discard an operator's in-progress CMS draft during deployment.
        return

    payload = json.dumps(
        {"source": "catalog", "product_ids": product_ids, "limit": 4},
        ensure_ascii=False,
    )
    internal_name = f"Homepage: {LOCALES['id'][slug]}"
    values = {
        "slug": slug,
        "internal_name": internal_name,
        "sort_order": SORT_ORDERS[slug],
        "payload": payload,
    }
    if row:
        values["entry_id"] = row["id"]
        bind.execute(
            sa.text(
                """
                UPDATE cms_content_entries
                SET internal_name = :internal_name,
                    status = 'published',
                    is_visible = true,
                    sort_order = :sort_order,
                    payload = CAST(:payload AS json),
                    published_at = COALESCE(published_at, now()),
                    updated_at = now()
                WHERE id = :entry_id
                """
            ),
            values,
        )
    else:
        values["entry_id"] = bind.execute(
            sa.text("SELECT replace(gen_random_uuid()::text, '-', '')")
        ).scalar()
        bind.execute(
            sa.text(
                """
                INSERT INTO cms_content_entries
                    (id, content_type, internal_name, slug, status, placement,
                     sort_order, is_visible, payload, published_at, created_at, updated_at)
                VALUES
                    (:entry_id, 'homepage_section', :internal_name, :slug, 'published',
                     'home', :sort_order, true, CAST(:payload AS json), now(), now(), now())
                """
            ),
            values,
        )

    for locale, titles in LOCALES.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO cms_content_translations (id, entry_id, locale, title)
                VALUES (replace(gen_random_uuid()::text, '-', ''), :entry_id, :locale, :title)
                ON CONFLICT (entry_id, locale)
                DO UPDATE SET title = EXCLUDED.title
                """
            ),
            {"entry_id": values["entry_id"], "locale": locale, "title": titles[slug]},
        )


def upgrade() -> None:
    bind = op.get_bind()
    _prepare_legacy_rows(bind)
    for slug, slugs in PRODUCT_SLUGS.items():
        _upsert_section(bind, slug, _product_ids(bind, slugs))


def downgrade() -> None:
    # Preserve operator-selected homepage content on downgrade.
    pass
