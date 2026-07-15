"""add safety_unverified flag to scorecards (Methodology v1.1)

Revision ID: e4f5a6b7c8d9
Revises: b7e2f4a19c3d
Create Date: 2026-07-14 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'b7e2f4a19c3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scorecards",
        sa.Column("safety_unverified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("scorecards", "safety_unverified")
