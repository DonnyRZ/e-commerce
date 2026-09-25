"""CMS-managed manual transfer destinations and Telegram delivery state."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "q6r7s8t9u0v1"
down_revision: Union[str, None] = "p5q6r7s8t9u0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_destinations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("callback_key", sa.String(length=12), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("destination_type", sa.String(length=20), nullable=False),
        sa.Column("account_number", sa.String(length=34), nullable=False),
        sa.Column("holder_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("slot >= 0 AND slot < 4", name="ck_payment_destinations_slot"),
        sa.CheckConstraint(
            "destination_type IN ('bank_account', 'card')",
            name="ck_payment_destinations_type",
        ),
        sa.UniqueConstraint("slot", name="uq_payment_destinations_slot"),
        sa.UniqueConstraint("callback_key", name="uq_payment_destinations_callback_key"),
    )
    op.create_index(
        "ix_payment_destinations_is_active", "payment_destinations", ["is_active"]
    )

    op.add_column("payments", sa.Column("destination_id", sa.String(length=32)))
    op.create_foreign_key(
        "fk_payments_destination_id",
        "payments",
        "payment_destinations",
        ["destination_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "payments",
        sa.Column(
            "destination_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "payments", sa.Column("telegram_selection_token", sa.String(length=24))
    )
    op.create_unique_constraint(
        "uq_payments_telegram_selection_token",
        "payments",
        ["telegram_selection_token"],
    )
    op.add_column(
        "payments", sa.Column("telegram_payment_message_id", sa.BigInteger())
    )
    op.add_column(
        "payments",
        sa.Column(
            "telegram_payment_status",
            sa.String(length=24),
            nullable=False,
            server_default="not_sent",
        ),
    )
    op.create_index(
        "ix_payments_telegram_payment_status", "payments", ["telegram_payment_status"]
    )
    op.add_column(
        "payments", sa.Column("telegram_payment_error", sa.String(length=80))
    )


def downgrade() -> None:
    op.drop_column("payments", "telegram_payment_error")
    op.drop_index("ix_payments_telegram_payment_status", table_name="payments")
    op.drop_column("payments", "telegram_payment_status")
    op.drop_column("payments", "telegram_payment_message_id")
    op.drop_constraint(
        "uq_payments_telegram_selection_token", "payments", type_="unique"
    )
    op.drop_column("payments", "telegram_selection_token")
    op.drop_column("payments", "destination_snapshot")
    op.drop_constraint("fk_payments_destination_id", "payments", type_="foreignkey")
    op.drop_column("payments", "destination_id")
    op.drop_index("ix_payment_destinations_is_active", table_name="payment_destinations")
    op.drop_table("payment_destinations")
