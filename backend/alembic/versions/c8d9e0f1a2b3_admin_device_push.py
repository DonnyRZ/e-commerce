"""Persistent admin device subscriptions and retryable Web Push delivery."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_push_subscriptions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(100), nullable=False),
        sa.Column("auth", sa.String(32), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_admin_push_subscriptions_user_id", "admin_push_subscriptions", ["user_id"]
    )
    op.create_table(
        "admin_push_deliveries",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.String(32),
            sa.ForeignKey("admin_push_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_status", sa.Integer(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "subscription_id", "event_key", name="uq_admin_push_delivery_event"
        ),
    )
    op.create_index(
        "ix_admin_push_delivery_due",
        "admin_push_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade():
    op.drop_table("admin_push_deliveries")
    op.drop_table("admin_push_subscriptions")
