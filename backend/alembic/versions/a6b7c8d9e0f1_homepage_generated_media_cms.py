"""Link the generated homepage visuals to CMS media entries.

The generated hero and department images were already uploaded to the CMS
media library. This migration exposes the department assets as editable CMS
content and removes the legacy homepage image paths once a CMS media link is
available.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "z5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Preserve an already selected hero asset. Only connect the known imported
    # hero file when the content entry has no media relation yet.
    bind.execute(
        sa.text(
            """
            WITH hero_media AS (
                SELECT id
                FROM cms_media_assets
                WHERE original_filename = 'home-hero.jpg'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            )
            UPDATE cms_content_entries AS hero
            SET media_id = (SELECT id FROM hero_media)
            WHERE hero.content_type = 'hero'
              AND hero.slug = 'home-hero'
              AND hero.media_id IS NULL
              AND EXISTS (SELECT 1 FROM hero_media)
            """
        )
    )

    # The old desktop/mobile paths were frontend assets. Once the hero is
    # linked to CMS media, both breakpoints should use that CMS-managed image.
    bind.execute(
        sa.text(
            """
            UPDATE cms_content_entries
            SET payload = CAST(
                (COALESCE(payload::jsonb, '{}'::jsonb)
                    - 'hero_asset_url'
                    - 'hero_mobile_asset_url'
                    - 'hero_poster_url')
                AS json
            )
            WHERE content_type = 'hero'
              AND slug = 'home-hero'
              AND media_id IS NOT NULL
              AND COALESCE(payload::jsonb, '{}'::jsonb) ?|
                  ARRAY['hero_asset_url', 'hero_mobile_asset_url', 'hero_poster_url']
            """
        )
    )

    # Make the three image-gen department photos first-class, editable CMS
    # entries. Category media_id remains untouched as a storefront fallback.
    bind.execute(
        sa.text(
            """
            INSERT INTO cms_content_entries (
                id, content_type, internal_name, slug, status, placement,
                sort_order, is_visible, media_id, payload, published_at,
                created_at, updated_at
            )
            SELECT
                md5('homepage-department-visual:' || category.slug),
                'department_visual',
                'Homepage department: ' || COALESCE(english.name, category.slug),
                category.slug,
                'published',
                'homepage',
                category.sort_order,
                TRUE,
                category.media_id,
                '{}'::json,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM categories AS category
            LEFT JOIN category_translations AS english
              ON english.category_id = category.id AND english.locale = 'en'
            WHERE category.kind = 'department'
              AND category.is_active = TRUE
              AND category.slug IN ('women-muslimah', 'uniqlo-products', 'tropical-halal-skincare')
              AND category.media_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM cms_content_entries AS existing
                  WHERE existing.content_type = 'department_visual'
                    AND existing.slug = category.slug
              )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO cms_content_translations (
                id, entry_id, locale, alt_text, created_at, updated_at
            )
            SELECT
                md5('homepage-department-visual-alt:' || entry.id || ':' || locale.locale),
                entry.id,
                locale.locale,
                COALESCE(
                    NULLIF(media_translation.alt_text, ''),
                    NULLIF(category_translation.name, ''),
                    entry.slug
                ),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM cms_content_entries AS entry
            JOIN categories AS category ON category.slug = entry.slug
            CROSS JOIN (VALUES ('en'), ('id'), ('uz'), ('ru')) AS locale(locale)
            LEFT JOIN cms_media_translations AS media_translation
              ON media_translation.media_id = entry.media_id
             AND media_translation.locale = locale.locale
            LEFT JOIN category_translations AS category_translation
              ON category_translation.category_id = category.id
             AND category_translation.locale = locale.locale
            WHERE entry.content_type = 'department_visual'
              AND entry.slug IN ('women-muslimah', 'uniqlo-products', 'tropical-halal-skincare')
              AND NOT EXISTS (
                  SELECT 1
                  FROM cms_content_translations AS existing
                  WHERE existing.entry_id = entry.id
                    AND existing.locale = locale.locale
              )
            """
        )
    )


def downgrade() -> None:
    # Keep CMS content and image links intact: operators may edit them after
    # deployment, so rolling back code must not delete that work.
    pass
