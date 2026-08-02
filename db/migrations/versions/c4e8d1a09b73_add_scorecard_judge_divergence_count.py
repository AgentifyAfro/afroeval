"""add judge_divergence_count to scorecards

Revision ID: c4e8d1a09b73
Revises: f3a91c7b2e04
Create Date: 2026-08-01 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8d1a09b73"
down_revision: str | None = "f3a91c7b2e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column("judge_divergence_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("scorecards", "judge_divergence_count")
