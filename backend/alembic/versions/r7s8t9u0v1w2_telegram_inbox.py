"""Telegram Business CMS inbox and confirmed product candidates."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "r7s8t9u0v1w2"
down_revision: Union[str, None] = "q6r7s8t9u0v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_conversations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("connection_id", sa.String(255), sa.ForeignKey(
            "telegram_business_connections.connection_id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_user_id", sa.String(32)),
        sa.Column("customer_username", sa.String(64), nullable=False, server_default=""),
        sa.Column("customer_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("telegram_language_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("locale", sa.String(5), nullable=False, server_default="id"),
        sa.Column("status", sa.String(24), nullable=False, server_default="needs_admin"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_customer_message_at", sa.DateTime(timezone=True)),
        sa.Column("last_admin_message_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "chat_id", name="uq_telegram_conversations_connection_chat"),
    )
    op.create_index("ix_telegram_conversations_connection_id", "telegram_conversations", ["connection_id"])
    op.create_index("ix_telegram_conversations_chat_id", "telegram_conversations", ["chat_id"])
    op.create_index("ix_telegram_conversations_customer_user_id", "telegram_conversations", ["customer_user_id"])
    op.create_index("ix_telegram_conversations_status", "telegram_conversations", ["status"])
    op.create_index("ix_telegram_conversations_last_message_at", "telegram_conversations", ["last_message_at"])
    op.create_index("ix_telegram_conversations_status_activity", "telegram_conversations", ["status", "last_message_at"])

    op.create_table(
        "telegram_inbox_messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("telegram_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(255), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("update_id", sa.BigInteger()),
        sa.Column("sender_user_id", sa.String(32)),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("source", sa.String(12), nullable=False, server_default="telegram"),
        sa.Column("message_type", sa.String(12), nullable=False, server_default="text"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("photo_file_id", sa.String(512)),
        sa.Column("photo_file_unique_id", sa.String(128)),
        sa.Column("photo_file_size", sa.Integer()),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "chat_id", "telegram_message_id", name="uq_telegram_inbox_messages_telegram_message"),
    )
    op.create_index("ix_telegram_inbox_messages_conversation_id", "telegram_inbox_messages", ["conversation_id"])
    op.create_index("ix_telegram_inbox_messages_connection_id", "telegram_inbox_messages", ["connection_id"])
    op.create_index("ix_telegram_inbox_messages_chat_id", "telegram_inbox_messages", ["chat_id"])
    op.create_index("ix_telegram_inbox_messages_update_id", "telegram_inbox_messages", ["update_id"])
    op.create_index("ix_telegram_inbox_messages_created_at", "telegram_inbox_messages", ["created_at"])
    op.create_index("ix_telegram_inbox_messages_conversation_created", "telegram_inbox_messages", ["conversation_id", "created_at"])

    op.create_table(
        "telegram_product_candidates",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("telegram_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_message_id", sa.String(32), sa.ForeignKey("telegram_inbox_messages.id", ondelete="SET NULL")),
        sa.Column("product_id", sa.String(32), nullable=False),
        sa.Column("variant_id", sa.String(32), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("option_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("image_url", sa.String(500)),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("confirmation_source", sa.String(12)),
        sa.Column("callback_token", sa.String(24), nullable=False),
        sa.Column("confirmation_message_id", sa.BigInteger()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("callback_token", name="uq_telegram_product_candidates_callback_token"),
    )
    op.create_index("ix_telegram_product_candidates_conversation_id", "telegram_product_candidates", ["conversation_id"])
    op.create_index("ix_telegram_product_candidates_product_id", "telegram_product_candidates", ["product_id"])
    op.create_index("ix_telegram_product_candidates_variant_id", "telegram_product_candidates", ["variant_id"])
    op.create_index("ix_telegram_product_candidates_status", "telegram_product_candidates", ["status"])
    op.create_index("ix_telegram_product_candidates_order_id", "telegram_product_candidates", ["order_id"])
    op.create_index("ix_telegram_product_candidates_conversation_status", "telegram_product_candidates", ["conversation_id", "status"])

    op.add_column("orders", sa.Column("telegram_conversation_id", sa.String(32)))
    op.create_foreign_key(
        "fk_orders_telegram_conversation_id",
        "orders", "telegram_conversations", ["telegram_conversation_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_orders_telegram_conversation_id", "orders", ["telegram_conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_telegram_conversation_id", table_name="orders")
    op.drop_constraint("fk_orders_telegram_conversation_id", "orders", type_="foreignkey")
    op.drop_column("orders", "telegram_conversation_id")
    op.drop_index("ix_telegram_product_candidates_conversation_status", table_name="telegram_product_candidates")
    op.drop_index("ix_telegram_product_candidates_order_id", table_name="telegram_product_candidates")
    op.drop_index("ix_telegram_product_candidates_status", table_name="telegram_product_candidates")
    op.drop_index("ix_telegram_product_candidates_variant_id", table_name="telegram_product_candidates")
    op.drop_index("ix_telegram_product_candidates_product_id", table_name="telegram_product_candidates")
    op.drop_index("ix_telegram_product_candidates_conversation_id", table_name="telegram_product_candidates")
    op.drop_table("telegram_product_candidates")
    op.drop_index("ix_telegram_inbox_messages_conversation_created", table_name="telegram_inbox_messages")
    op.drop_index("ix_telegram_inbox_messages_created_at", table_name="telegram_inbox_messages")
    op.drop_index("ix_telegram_inbox_messages_update_id", table_name="telegram_inbox_messages")
    op.drop_index("ix_telegram_inbox_messages_chat_id", table_name="telegram_inbox_messages")
    op.drop_index("ix_telegram_inbox_messages_connection_id", table_name="telegram_inbox_messages")
    op.drop_index("ix_telegram_inbox_messages_conversation_id", table_name="telegram_inbox_messages")
    op.drop_table("telegram_inbox_messages")
    op.drop_index("ix_telegram_conversations_status_activity", table_name="telegram_conversations")
    op.drop_index("ix_telegram_conversations_last_message_at", table_name="telegram_conversations")
    op.drop_index("ix_telegram_conversations_status", table_name="telegram_conversations")
    op.drop_index("ix_telegram_conversations_customer_user_id", table_name="telegram_conversations")
    op.drop_index("ix_telegram_conversations_chat_id", table_name="telegram_conversations")
    op.drop_index("ix_telegram_conversations_connection_id", table_name="telegram_conversations")
    op.drop_table("telegram_conversations")
