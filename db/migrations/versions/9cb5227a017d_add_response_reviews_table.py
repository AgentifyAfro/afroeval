"""add response_reviews table

Revision ID: 9cb5227a017d
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15 20:52:36.338782

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '9cb5227a017d'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('response_reviews',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('response_id', sa.Uuid(), nullable=False),
    sa.Column('reviewer_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('language_performance_score', sa.Float(), nullable=True),
    sa.Column('language_performance_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('cultural_appropriateness_score', sa.Float(), nullable=True),
    sa.Column('cultural_appropriateness_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('hallucination_risk_score', sa.Float(), nullable=True),
    sa.Column('hallucination_risk_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('bias_fairness_score', sa.Float(), nullable=True),
    sa.Column('bias_fairness_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('code_switching_quality_score', sa.Float(), nullable=True),
    sa.Column('code_switching_quality_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('safety_robustness_score', sa.Float(), nullable=True),
    sa.Column('safety_robustness_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['response_id'], ['model_responses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_response_reviews_response_id'), 'response_reviews', ['response_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_response_reviews_response_id'), table_name='response_reviews')
    op.drop_table('response_reviews')
