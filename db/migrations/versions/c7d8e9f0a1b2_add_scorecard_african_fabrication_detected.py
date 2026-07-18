"""add african_fabrication_detected flag to scorecards (Methodology v1.2)

Revision ID: c7d8e9f0a1b2
Revises: e4f5a6b7c8d9
Create Date: 2026-07-17 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d8e9f0a1b2'
down_revision: str | None = 'e4f5a6b7c8d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column("african_fabrication_detected", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("scorecards", "african_fabrication_detected")
