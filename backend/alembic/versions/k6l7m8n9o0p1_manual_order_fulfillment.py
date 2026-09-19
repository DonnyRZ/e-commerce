"""manual transfer review and two-leg order fulfillment

The migration is additive. Existing order, payment, inventory, Telegram, and
CMS rows remain intact; the new workflow is entered only by the admin order
creation endpoint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k6l7m8n9o0p1"
down_revision: Union[str, None] = "j5k6l7m8n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "telegram_cart_inquiries",
        sa.Column("order_id", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_telegram_inquiries_order",
        "telegram_cart_inquiries",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_telegram_cart_inquiries_order_id",
        "telegram_cart_inquiries",
        ["order_id"],
        unique=True,
    )
    op.add_column(
        "telegram_cart_inquiries",
        sa.Column("telegram_connection_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "telegram_cart_inquiries",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_telegram_cart_inquiries_telegram_connection_id",
        "telegram_cart_inquiries",
        ["telegram_connection_id"],
    )
    op.create_index(
        "ix_telegram_cart_inquiries_telegram_chat_id",
        "telegram_cart_inquiries",
        ["telegram_chat_id"],
    )

    op.add_column(
        "orders",
        sa.Column("order_source", sa.String(length=30), nullable=False, server_default="checkout"),
    )

    op.create_table(
        "manual_payment_evidence",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("payment_id", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=180), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("mime_type", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("uploaded_by", sa.String(length=32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_manual_payment_evidence_payment_id", "manual_payment_evidence", ["payment_id"]
    )
    op.create_index(
        "ix_manual_payment_evidence_payment_created",
        "manual_payment_evidence",
        ["payment_id", "created_at"],
    )

    op.create_table(
        "order_fulfillment_stages",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("carrier", sa.String(length=80), nullable=True),
        sa.Column("tracking_number", sa.String(length=120), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("acted_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("order_id", "stage", name="uq_order_fulfillment_stage"),
    )
    op.create_index(
        "ix_order_fulfillment_stages_order_id", "order_fulfillment_stages", ["order_id"]
    )
    op.create_index(
        "ix_order_fulfillment_order_stage", "order_fulfillment_stages", ["order_id", "stage"]
    )


def downgrade() -> None:
    op.drop_index("ix_order_fulfillment_order_stage", table_name="order_fulfillment_stages")
    op.drop_index("ix_order_fulfillment_stages_order_id", table_name="order_fulfillment_stages")
    op.drop_table("order_fulfillment_stages")
    op.drop_index("ix_manual_payment_evidence_payment_created", table_name="manual_payment_evidence")
    op.drop_index("ix_manual_payment_evidence_payment_id", table_name="manual_payment_evidence")
    op.drop_table("manual_payment_evidence")
    op.drop_column("orders", "order_source")
    op.drop_index("ix_telegram_cart_inquiries_telegram_chat_id", table_name="telegram_cart_inquiries")
    op.drop_index("ix_telegram_cart_inquiries_telegram_connection_id", table_name="telegram_cart_inquiries")
    op.drop_index("ix_telegram_cart_inquiries_order_id", table_name="telegram_cart_inquiries")
    op.drop_constraint("fk_telegram_inquiries_order", "telegram_cart_inquiries", type_="foreignkey")
    op.drop_column("telegram_cart_inquiries", "telegram_chat_id")
    op.drop_column("telegram_cart_inquiries", "telegram_connection_id")
    op.drop_column("telegram_cart_inquiries", "order_id")
