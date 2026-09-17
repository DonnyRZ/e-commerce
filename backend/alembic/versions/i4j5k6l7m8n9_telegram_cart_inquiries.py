"""Persist temporary Telegram cart inquiries and update deduplication.

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_business_connections",
        sa.Column("connection_id", sa.String(length=255), primary_key=True),
        sa.Column("business_user_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_reply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_read_messages", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_business_connections_username",
        "telegram_business_connections",
        ["username"],
    )

    op.create_table(
        "telegram_cart_inquiries",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("reference", sa.String(length=40), nullable=False, unique=True),
        sa.Column("cart_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "cart_id", "idempotency_key", name="uq_telegram_inquiry_cart_idempotency"
        ),
    )
    for name, column in (
        ("ix_telegram_cart_inquiries_cart_id", "cart_id"),
        ("ix_telegram_cart_inquiries_user_id", "user_id"),
        ("ix_telegram_cart_inquiries_status", "status"),
        ("ix_telegram_cart_inquiries_expires_at", "expires_at"),
    ):
        op.create_index(name, "telegram_cart_inquiries", [column])
    op.create_index(
        "ix_telegram_cart_inquiries_expires_status",
        "telegram_cart_inquiries",
        ["expires_at", "status"],
    )

    op.create_table(
        "telegram_update_receipts",
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telegram_update_receipts_status", "telegram_update_receipts", ["status"]
    )
    op.create_index(
        "ix_telegram_update_receipts_received_at",
        "telegram_update_receipts",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_update_receipts_received_at",
        table_name="telegram_update_receipts",
    )
    op.drop_index("ix_telegram_update_receipts_status", table_name="telegram_update_receipts")
    op.drop_table("telegram_update_receipts")
    op.drop_index("ix_telegram_cart_inquiries_expires_status", table_name="telegram_cart_inquiries")
    for name in (
        "ix_telegram_cart_inquiries_expires_at",
        "ix_telegram_cart_inquiries_status",
        "ix_telegram_cart_inquiries_user_id",
        "ix_telegram_cart_inquiries_cart_id",
    ):
        op.drop_index(name, table_name="telegram_cart_inquiries")
    op.drop_table("telegram_cart_inquiries")
    op.drop_index("ix_telegram_business_connections_username", table_name="telegram_business_connections")
    op.drop_table("telegram_business_connections")
