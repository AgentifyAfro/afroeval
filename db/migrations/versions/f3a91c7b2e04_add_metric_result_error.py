"""add error + error_cause to metric_results

Revision ID: f3a91c7b2e04
Revises: f2a3b4c5d6e7
Create Date: 2026-07-31 00:00:00.000000

Infra-error plumbing: mark a MetricResult row as a judge/infra failure (rate limit,
content filter, parse error, timeout, missing dependency) rather than a real measurement,
so the read path can exclude it and reconstruction matches scoring. Both nullable-safe:
existing rows are error=false / error_cause=NULL (normal measurements).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a91c7b2e04'
down_revision: str | None = 'f2a3b4c5d6e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metric_results",
        sa.Column("error", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "metric_results",
        sa.Column("error_cause", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("metric_results", "error_cause")
    op.drop_column("metric_results", "error")
