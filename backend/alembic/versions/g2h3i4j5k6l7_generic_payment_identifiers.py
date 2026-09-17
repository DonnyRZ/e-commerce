"""use provider-neutral payment identifiers

Revision ID: g2h3i4j5k6l7
Revises: d7e8f9a0b1c2
Create Date: 2026-09-13

The existing payment history is retained. Only the active ORM vocabulary is
made provider-neutral so a future payment workflow can be added without
reintroducing a retired provider contract.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_payments_click_trans_id", table_name="payments")
    op.alter_column(
        "payments", "click_trans_id", new_column_name="provider_transaction_id"
    )
    op.alter_column(
        "payments", "click_paydoc_id", new_column_name="provider_document_id"
    )
    op.alter_column(
        "payment_events", "click_trans_id", new_column_name="provider_transaction_id"
    )
    op.create_index(
        "ix_payments_provider_transaction_id",
        "payments",
        ["provider_transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_payments_provider_transaction_id", table_name="payments")
    op.alter_column(
        "payment_events", "provider_transaction_id", new_column_name="click_trans_id"
    )
    op.alter_column(
        "payments", "provider_document_id", new_column_name="click_paydoc_id"
    )
    op.alter_column(
        "payments", "provider_transaction_id", new_column_name="click_trans_id"
    )
    op.create_index(
        "ix_payments_click_trans_id",
        "payments",
        ["click_trans_id"],
        unique=False,
    )
