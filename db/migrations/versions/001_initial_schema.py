"""Initial schema — all AfroEval core tables.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benchmark_packs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_held_out", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_packs_name", "benchmark_packs", ["name"])
    op.create_index("ix_benchmark_packs_version", "benchmark_packs", ["version"])

    op.create_table(
        "benchmark_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pack_id", sa.UUID(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("expected_behavior", sa.Text(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("cohort", sa.String(), nullable=False, server_default=""),
        sa.Column("provenance", sa.String(), nullable=False, server_default=""),
        sa.Column("sme_author_id", sa.String(), nullable=False, server_default=""),
        sa.Column("validation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("irr_score", sa.Float(), nullable=True),
        sa.Column("is_gold", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["pack_id"], ["benchmark_packs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_items_pack_id", "benchmark_items", ["pack_id"])

    op.create_table(
        "assessments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("model_provider", sa.String(), nullable=False),
        sa.Column("model_identifier", sa.String(), nullable=False),
        sa.Column("benchmark_pack_ids", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False, server_default="operator"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_assessment_id", "runs", ["assessment_id"])

    op.create_table(
        "model_responses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["benchmark_items.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_responses_run_id", "model_responses", ["run_id"])
    op.create_index("ix_model_responses_item_id", "model_responses", ["item_id"])

    op.create_table(
        "metric_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("response_id", sa.UUID(), nullable=False),
        sa.Column("dimension", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("evaluator_version", sa.String(), nullable=False, server_default="0.1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["response_id"], ["model_responses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_results_response_id", "metric_results", ["response_id"])

    op.create_table(
        "scorecards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("composite_score", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("confidence_flag", sa.String(), nullable=False, server_default="standard"),
        sa.Column("dimension_scores", sa.JSON(), nullable=True),
        sa.Column("dimension_weights", sa.JSON(), nullable=True),
        sa.Column("failing_examples", sa.JSON(), nullable=True),
        sa.Column("remediation_roadmap", sa.JSON(), nullable=True),
        sa.Column("benchmark_pack_version", sa.String(), nullable=False, server_default=""),
        sa.Column("methodology_version", sa.String(), nullable=False, server_default="v1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("pdf_path", sa.String(), nullable=True),
        sa.Column("json_path", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_scorecards_run_id", "scorecards", ["run_id"])


def downgrade() -> None:
    op.drop_table("scorecards")
    op.drop_table("metric_results")
    op.drop_table("model_responses")
    op.drop_table("runs")
    op.drop_table("assessments")
    op.drop_table("benchmark_items")
    op.drop_table("benchmark_packs")
