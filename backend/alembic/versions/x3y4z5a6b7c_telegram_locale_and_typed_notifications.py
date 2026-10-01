"""Track Telegram locale provenance and render order notifications at send time."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "x3y4z5a6b7c"
down_revision: Union[str, None] = "w2x3y4z5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "telegram_conversations",
        sa.Column(
            "locale_source",
            sa.String(length=20),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.create_check_constraint(
        "ck_telegram_conversations_locale_source",
        "telegram_conversations",
        "locale_source IN ('web', 'direct_default', 'admin', 'legacy')",
    )

    op.add_column(
        "telegram_order_notification_outbox",
        sa.Column("event_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "telegram_order_notification_outbox",
        sa.Column("event_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE telegram_order_notification_outbox
            SET event_type = CASE
                    WHEN event_key = 'payment_confirmed' THEN 'payment_confirmed'
                    WHEN event_key LIKE 'payment_rejected:%' THEN 'payment_rejected'
                    WHEN event_key LIKE 'fulfillment:%' THEN 'fulfillment'
                    ELSE 'legacy'
                END,
                event_payload = CASE
                    WHEN event_key LIKE 'payment_rejected:%' THEN
                        jsonb_build_object(
                            'reason', CASE
                                WHEN position('Alasan: ' in message_text) > 0 THEN
                                    substring(
                                        message_text
                                        from position('Alasan: ' in message_text) + length('Alasan: ')
                                    )
                                ELSE ''
                            END
                        )
                    WHEN event_key LIKE 'fulfillment:%' THEN
                        jsonb_build_object('stage', substring(event_key from '^fulfillment:(.*)$'))
                    ELSE '{}'::jsonb
                END
            """
        )
    )
    op.alter_column(
        "telegram_order_notification_outbox",
        "event_type",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="legacy",
    )
    op.alter_column(
        "telegram_order_notification_outbox",
        "event_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.drop_column("telegram_order_notification_outbox", "event_payload")
    op.drop_column("telegram_order_notification_outbox", "event_type")
    op.drop_constraint(
        "ck_telegram_conversations_locale_source",
        "telegram_conversations",
        type_="check",
    )
    op.drop_column("telegram_conversations", "locale_source")
