"""enable RLS on item_validations (added after the initial RLS migration)

Revision ID: a7c3e9d1f5b2
Revises: c4e8d1a09b73
Create Date: 2026-08-03 00:00:00.000000

item_validations (Methodology v1.4 Tier-1 path) was created after dda5b8820ce4
(the initial "enable RLS on public tables" migration), so it never had RLS enabled
— Supabase flagged it as rls_disabled_in_public (anyone with the project URL + the
public anon key could read/write it via PostgREST). Enable RLS with NO anon/
authenticated policies so the public REST path is denied, while the app's direct
postgres connection (which has BYPASSRLS) is unaffected — identical treatment to the
9 tables in dda5b8820ce4. Idempotent: ENABLE on an already-enabled table is a no-op
(prod was closed manually first; this codifies it for fresh DBs / CI).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a7c3e9d1f5b2"
down_revision: str | None = "c4e8d1a09b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.item_validations ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE public.item_validations DISABLE ROW LEVEL SECURITY")
