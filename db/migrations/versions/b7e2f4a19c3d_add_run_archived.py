"""add archived flag to runs (console curation)

Revision ID: b7e2f4a19c3d
Revises: dda5b8820ce4
Create Date: 2026-06-30 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e2f4a19c3d'
down_revision: str | None = 'dda5b8820ce4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("runs", "archived")
