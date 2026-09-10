"""m8 follow-up: backfill seller fulfillments for pre-existing orders

Orders created before M8 have no seller_order_fulfillments rows; without
this backfill they would be invisible to sellers after upgrade.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO seller_order_fulfillments
            (id, order_id, seller_id, status, created_at, updated_at)
        SELECT replace(gen_random_uuid()::text, '-', ''),
               oi.order_id, oi.seller_id, 'pending', now(), now()
        FROM (SELECT DISTINCT order_id, seller_id FROM order_items) oi
        LEFT JOIN seller_order_fulfillments f
               ON f.order_id = oi.order_id AND f.seller_id = oi.seller_id
        WHERE f.id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM seller_order_fulfillments f
        WHERE NOT EXISTS (
            SELECT 1 FROM orders o
            WHERE o.id = f.order_id AND o.created_at >= f.created_at - interval '1 second'
        )
        """
    )
