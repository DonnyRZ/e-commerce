"""Durable Telegram payment-notification delivery queue."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "s8t9u0v1w2x3"
down_revision: Union[str, None] = "r7s8t9u0v1w2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_payment_notification_outbox",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "payment_id",
            sa.String(length=32),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'blocked', 'unavailable')",
            name="ck_telegram_payment_outbox_status",
        ),
    )
    op.create_index(
        "ix_telegram_payment_outbox_status_created",
        "telegram_payment_notification_outbox",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_telegram_payment_outbox_payment_created",
        "telegram_payment_notification_outbox",
        ["payment_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_payment_outbox_payment_created",
        table_name="telegram_payment_notification_outbox",
    )
    op.drop_index(
        "ix_telegram_payment_outbox_status_created",
        table_name="telegram_payment_notification_outbox",
    )
    op.drop_table("telegram_payment_notification_outbox")
