"""Store Telegram rich message slides and media albums in the CMS inbox."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "v1w2x3y4z5a"
down_revision: Union[str, None] = "u0v1w2x3y4z"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "telegram_inbox_messages",
        sa.Column("rich_content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "telegram_inbox_messages",
        sa.Column("media_group_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telegram_inbox_messages", "media_group_id")
    op.drop_column("telegram_inbox_messages", "rich_content")
