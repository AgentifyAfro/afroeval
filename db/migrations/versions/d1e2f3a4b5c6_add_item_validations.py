"""add item_validations table (Methodology v1.4 Tier 1 path)

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-07-19 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'd1e2f3a4b5c6'
down_revision: str | None = 'c7d8e9f0a1b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'item_validations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('item_content_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('validator_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('batch_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                  server_default=''),
        sa.Column('factual_accuracy', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('language_quality', sa.Integer(), nullable=False),
        sa.Column('cultural_score', sa.Integer(), nullable=False),
        sa.Column('schema_compliant', sa.Boolean(), nullable=False),
        sa.Column('justification', sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                  server_default=''),
        sa.Column('verdict', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['benchmark_items.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id', 'validator_id',
                            name='uq_item_validations_item_validator'),
    )
    op.create_index(op.f('ix_item_validations_item_id'), 'item_validations', ['item_id'])
    op.create_index(op.f('ix_item_validations_validator_id'), 'item_validations',
                    ['validator_id'])
    op.create_index(op.f('ix_item_validations_batch_id'), 'item_validations', ['batch_id'])
    op.create_index(op.f('ix_item_validations_item_content_hash'), 'item_validations',
                    ['item_content_hash'])


def downgrade() -> None:
    op.drop_index(op.f('ix_item_validations_item_content_hash'), table_name='item_validations')
    op.drop_index(op.f('ix_item_validations_batch_id'), table_name='item_validations')
    op.drop_index(op.f('ix_item_validations_validator_id'), table_name='item_validations')
    op.drop_index(op.f('ix_item_validations_item_id'), table_name='item_validations')
    op.drop_table('item_validations')
