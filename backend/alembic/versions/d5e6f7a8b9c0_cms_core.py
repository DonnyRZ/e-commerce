"""m9: CMS core + admin payment-review columns

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("reviewed_by", sa.String(length=32), nullable=True))
    op.add_column("payments", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "cms_media_assets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("storage_provider", sa.String(length=20), server_default="local", nullable=False),
        sa.Column("storage_key", sa.String(length=160), nullable=False),
        sa.Column("original_filename", sa.String(length=255), server_default="", nullable=False),
        sa.Column("mime_type", sa.String(length=80), server_default="", nullable=False),
        sa.Column("file_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(length=64), server_default="", nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cms_media_assets"),
        sa.UniqueConstraint("storage_key", name="uq_cms_media_assets_storage_key"),
    )
    op.create_table(
        "cms_media_translations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("media_id", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False),
        sa.Column("alt_text", sa.String(length=255), server_default="", nullable=False),
        sa.Column("caption", sa.String(length=500), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["cms_media_assets.id"], name="fk_cms_media_translations_media_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_cms_media_translations"),
        sa.UniqueConstraint("media_id", "locale", name="uq_cms_media_translations_media_locale"),
    )
    op.create_index("ix_cms_media_translations_media_id", "cms_media_translations", ["media_id"])

    op.create_table(
        "cms_content_entries",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("internal_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("slug", sa.String(length=160), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("placement", sa.String(length=80), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("media_id", sa.String(length=32), nullable=True),
        sa.Column("cta_url", sa.String(length=500), nullable=True),
        sa.Column("secondary_cta_url", sa.String(length=500), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["cms_media_assets.id"], name="fk_cms_content_entries_media_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_cms_content_entries"),
    )
    op.create_index("ix_cms_content_entries_content_type", "cms_content_entries", ["content_type"])
    op.create_index("ix_cms_content_entries_slug", "cms_content_entries", ["slug"])
    op.create_index("ix_cms_content_entries_status", "cms_content_entries", ["status"])

    op.create_table(
        "cms_content_translations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("entry_id", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False),
        sa.Column("title", sa.String(length=500), server_default="", nullable=False),
        sa.Column("eyebrow", sa.String(length=255), server_default="", nullable=False),
        sa.Column("subtitle", sa.String(length=500), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("cta_label", sa.String(length=120), server_default="", nullable=False),
        sa.Column("secondary_cta_label", sa.String(length=120), server_default="", nullable=False),
        sa.Column("alt_text", sa.String(length=255), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["cms_content_entries.id"], name="fk_cms_content_translations_entry_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_cms_content_translations"),
        sa.UniqueConstraint("entry_id", "locale", name="uq_cms_content_translations_entry_locale"),
    )
    op.create_index("ix_cms_content_translations_entry_id", "cms_content_translations", ["entry_id"])

    op.create_table(
        "cms_revisions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("content_id", sa.String(length=32), nullable=False),
        sa.Column("version_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cms_revisions"),
    )
    op.create_index("ix_cms_revisions_content_type", "cms_revisions", ["content_type"])
    op.create_index("ix_cms_revisions_content_id", "cms_revisions", ["content_id"])

    op.create_table(
        "cms_audit_logs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("target_type", sa.String(length=40), server_default="", nullable=False),
        sa.Column("target_id", sa.String(length=40), server_default="", nullable=False),
        sa.Column("safe_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cms_audit_logs"),
    )
    op.create_index("ix_cms_audit_logs_actor_user_id", "cms_audit_logs", ["actor_user_id"])
    op.create_index("ix_cms_audit_logs_action", "cms_audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("cms_audit_logs")
    op.drop_table("cms_revisions")
    op.drop_table("cms_content_translations")
    op.drop_table("cms_content_entries")
    op.drop_table("cms_media_translations")
    op.drop_table("cms_media_assets")
    op.drop_column("payments", "reviewed_at")
    op.drop_column("payments", "reviewed_by")
    op.drop_column("payments", "review_note")
