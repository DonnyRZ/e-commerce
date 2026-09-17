"""single-owner operating model and checkout uniqueness guards

This migration keeps the historical seller columns for rollback/audit
compatibility, but normalises catalog/order ownership to the one internal
store owner. Public seller routes are removed from the application surface;
Admin Core is the only management workflow.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Prefer the explicit store account, then the first active admin/owner.
    # If no operator account exists yet, leave rows untouched so deployment
    # fails visibly during the operator bootstrap instead of inventing one.
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE owner_id text;
            BEGIN
                SELECT id INTO owner_id
                FROM users
                WHERE email = 'official@muslimahcantik.id'
                ORDER BY created_at ASC, id ASC
                LIMIT 1;

                IF owner_id IS NULL THEN
                    SELECT id INTO owner_id
                    FROM users
                    WHERE role IN ('admin', 'owner') AND is_active = TRUE
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1;
                END IF;

                IF owner_id IS NOT NULL THEN
                    UPDATE products SET seller_id = owner_id;
                    UPDATE order_items SET seller_id = owner_id;
                    UPDATE seller_order_fulfillments SET seller_id = owner_id;
                END IF;

                -- Seller accounts are legacy data in this single-operator
                -- deployment. Keep their rows for audit/history, but make
                -- them unable to authenticate as a seller.
                UPDATE users
                SET role = 'customer', is_active = FALSE, token_version = token_version + 1
                WHERE role = 'seller' AND (owner_id IS NULL OR id <> owner_id);
            END $$;
            """
        )
    )

    # A principal can have exactly one active cart, and an order can have
    # exactly one non-terminal payment attempt. Partial indexes preserve
    # historical failed/refunded payment records without allowing duplicate
    # live checkout state.
    op.create_index(
        "uq_carts_user_id_not_null",
        "carts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_carts_guest_token_not_null",
        "carts",
        ["guest_token"],
        unique=True,
        postgresql_where=sa.text("guest_token IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_one_active_order",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(
            "status NOT IN ('failed', 'cancelled', 'expired', 'refunded', 'reversed')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_one_active_order", table_name="payments")
    op.drop_index("uq_carts_guest_token_not_null", table_name="carts")
    op.drop_index("uq_carts_user_id_not_null", table_name="carts")
