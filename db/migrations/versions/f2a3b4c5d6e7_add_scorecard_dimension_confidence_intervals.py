"""add dimension_confidence_intervals to scorecards

Revision ID: f2a3b4c5d6e7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-26 00:00:00.000000

Descriptive 95% confidence interval per dimension ({dimension: [lo, hi]} on the
0–100 scale). Nullable — historical scorecards have NULL and render "—".
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2a3b4c5d6e7'
down_revision: str | None = 'd1e2f3a4b5c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column("dimension_confidence_intervals", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scorecards", "dimension_confidence_intervals")
