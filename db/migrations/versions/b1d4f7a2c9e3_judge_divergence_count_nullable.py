"""make scorecards.judge_divergence_count nullable (gap G7)

Revision ID: b1d4f7a2c9e3
Revises: a7c3e9d1f5b2
Create Date: 2026-08-04 00:00:00.000000

judge_divergence_count was int NOT NULL DEFAULT 0, which conflated "not computed"
(LaBSE unavailable → no items entered the divergence loop) with "computed, none found".
Make it nullable and drop the default so the dispatcher can persist NULL for the
not-computed case — the same null-not-estimated pattern as irr_score — keeping the
Phase-2 calibration corpus honest. Existing rows keep their 0 value (a historical run
cannot be retroactively distinguished; new runs are correct).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b1d4f7a2c9e3"
down_revision: str | None = "a7c3e9d1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("scorecards", "judge_divergence_count", nullable=True)
    op.execute("ALTER TABLE scorecards ALTER COLUMN judge_divergence_count DROP DEFAULT")


def downgrade() -> None:
    op.execute("UPDATE scorecards SET judge_divergence_count = 0 WHERE judge_divergence_count IS NULL")
    op.alter_column(
        "scorecards", "judge_divergence_count", nullable=False, server_default="0"
    )
