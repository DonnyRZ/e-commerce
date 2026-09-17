"""Merge the existing schema head with the media asset link migration.

Revision ID: b1c2d3e4f5a6
Revises: f0a1b2c3d4e5, a1b2c3d4e5f6
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = ("f0a1b2c3d4e5", "a1b2c3d4e5f6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The schema change lives in a1b2c3d4e5f6; this revision only converges
    # the pre-existing operator head and the new media-link head.
    pass


def downgrade() -> None:
    pass
