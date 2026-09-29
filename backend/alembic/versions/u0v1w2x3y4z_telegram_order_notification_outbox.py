"""Add durable Telegram notifications for order transitions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u0v1w2x3y4z"
down_revision: Union[str, None] = "t9u0v1w2x3y"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_order_notification_outbox",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(length=32),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="pending"
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "order_id", "event_key", name="uq_telegram_order_notification_event"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'unavailable')",
            name="ck_telegram_order_notification_status",
        ),
    )
    op.create_index(
        "ix_telegram_order_notification_order_id",
        "telegram_order_notification_outbox",
        ["order_id"],
    )
    op.create_index(
        "ix_telegram_order_notification_status_created",
        "telegram_order_notification_outbox",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_order_notification_status_created",
        table_name="telegram_order_notification_outbox",
    )
    op.drop_index(
        "ix_telegram_order_notification_order_id",
        table_name="telegram_order_notification_outbox",
    )
    op.drop_table("telegram_order_notification_outbox")
