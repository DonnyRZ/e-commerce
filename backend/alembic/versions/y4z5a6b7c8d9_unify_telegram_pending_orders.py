"""Route Telegram Inbox confirmations through Pending Orders."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "y4z5a6b7c8d9"
down_revision: Union[str, None] = "x3y4z5a6b7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "telegram_cart_inquiries",
        "cart_id",
        existing_type=sa.String(length=32),
        nullable=True,
    )
    op.alter_column(
        "telegram_cart_inquiries",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.add_column(
        "telegram_cart_inquiries",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="web"),
    )
    op.add_column(
        "telegram_cart_inquiries",
        sa.Column("conversation_id", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_telegram_cart_inquiries_conversation_id",
        "telegram_cart_inquiries",
        "telegram_conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_telegram_cart_inquiries_conversation_id",
        "telegram_cart_inquiries",
        ["conversation_id"],
    )
    op.create_unique_constraint(
        "uq_telegram_inquiry_conversation_idempotency",
        "telegram_cart_inquiries",
        ["conversation_id", "idempotency_key"],
    )
    op.create_check_constraint(
        "ck_telegram_cart_inquiries_source",
        "telegram_cart_inquiries",
        "source IN ('web', 'telegram_inbox')",
    )


def downgrade() -> None:
    # Preserve queued inbox requests as usable cart-scoped inquiries if this
    # migration is rolled back to a version without source metadata.
    op.execute(
        sa.text(
            "UPDATE telegram_cart_inquiries "
            "SET cart_id = COALESCE(cart_id, conversation_id, id), "
            "expires_at = COALESCE(expires_at, created_at + interval '3650 days') "
            "WHERE cart_id IS NULL OR expires_at IS NULL"
        )
    )
    op.drop_constraint(
        "ck_telegram_cart_inquiries_source", "telegram_cart_inquiries", type_="check"
    )
    op.drop_constraint(
        "uq_telegram_inquiry_conversation_idempotency",
        "telegram_cart_inquiries",
        type_="unique",
    )
    op.drop_index(
        "ix_telegram_cart_inquiries_conversation_id",
        table_name="telegram_cart_inquiries",
    )
    op.drop_constraint(
        "fk_telegram_cart_inquiries_conversation_id",
        "telegram_cart_inquiries",
        type_="foreignkey",
    )
    op.drop_column("telegram_cart_inquiries", "conversation_id")
    op.drop_column("telegram_cart_inquiries", "source")
    op.alter_column(
        "telegram_cart_inquiries",
        "cart_id",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "telegram_cart_inquiries",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
