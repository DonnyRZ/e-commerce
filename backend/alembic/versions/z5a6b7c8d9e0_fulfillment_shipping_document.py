"""Store a private shipping document on its fulfillment stage."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "z5a6b7c8d9e0"
down_revision: Union[str, None] = "y4z5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "order_fulfillment_stages",
        sa.Column("shipping_document_key", sa.String(length=180), nullable=True),
    )
    op.add_column(
        "order_fulfillment_stages",
        sa.Column("shipping_document_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "order_fulfillment_stages",
        sa.Column("shipping_document_mime_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "order_fulfillment_stages",
        sa.Column("shipping_document_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "order_fulfillment_stages",
        sa.Column("shipping_document_checksum", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_order_fulfillment_shipping_document_key",
        "order_fulfillment_stages",
        ["shipping_document_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_order_fulfillment_shipping_document_key",
        "order_fulfillment_stages",
        type_="unique",
    )
    op.drop_column("order_fulfillment_stages", "shipping_document_checksum")
    op.drop_column("order_fulfillment_stages", "shipping_document_size")
    op.drop_column("order_fulfillment_stages", "shipping_document_mime_type")
    op.drop_column("order_fulfillment_stages", "shipping_document_filename")
    op.drop_column("order_fulfillment_stages", "shipping_document_key")
