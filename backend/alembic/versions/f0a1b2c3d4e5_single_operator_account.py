"""Normalise legacy operator accounts to one active Admin Console owner."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE owner_id text;
            BEGIN
                SELECT id INTO owner_id
                FROM users
                WHERE email = 'official@muslimahcantik.id'
                  AND is_active = TRUE
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
                    UPDATE users
                    SET role = 'admin', is_active = TRUE
                    WHERE id = owner_id;

                    UPDATE users
                    SET role = 'customer', is_active = FALSE,
                        token_version = token_version + 1
                    WHERE role IN ('admin', 'owner') AND id <> owner_id;

                    UPDATE products SET seller_id = owner_id;
                    UPDATE order_items SET seller_id = owner_id;
                    UPDATE seller_order_fulfillments SET seller_id = owner_id;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # Account deactivation is intentionally not reversed automatically.
    pass
