"""enable RLS on public tables, no anon/authenticated policies

Revision ID: dda5b8820ce4
Revises: 9cb5227a017d
Create Date: 2026-06-25 16:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'dda5b8820ce4'
down_revision: str | None = '9cb5227a017d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "benchmark_packs",
    "benchmark_items",
    "assessments",
    "runs",
    "model_responses",
    "metric_results",
    "scorecards",
    "response_reviews",
    "alembic_version",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
