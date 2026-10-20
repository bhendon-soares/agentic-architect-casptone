"""P1 IA telemetry; no illustrative pricing is activated.

Revision ID: 20261019_01
Revises: 20261013_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20261019_01"
down_revision = "20261013_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("original_run_id", sa.String(36)))
    op.create_table(
        "agent_run_telemetry",
        sa.Column("telemetry_id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.agent_run_id"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(32), nullable=False),
        sa.Column("model_used", sa.String(255)),
        sa.Column("deployment_id", sa.String(255)),
        sa.Column("timestamp_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_end", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("tokens_input", sa.Integer()),
        sa.Column("tokens_output", sa.Integer()),
        sa.Column("tokens_cache", sa.Integer()),
        sa.Column("cache_in_input", sa.Boolean()),
        sa.Column("estimated_cost_value", sa.Numeric(18, 8)),
        sa.Column("estimated_cost_currency", sa.String(3)),
        sa.Column("pricing_config_id", sa.String(36)),
        sa.UniqueConstraint("agent_run_id", "step_index"),
    )
    op.create_index(
        "ix_agent_run_telemetry_agent_run_id", "agent_run_telemetry", ["agent_run_id"]
    )
    op.create_table(
        "agent_run_attempts",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.agent_run_id"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer()),
        sa.Column("attempt_type", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_agent_run_attempts_agent_run_id", "agent_run_attempts", ["agent_run_id"]
    )
    op.create_table(
        "pricing_config_versions",
        sa.Column("pricing_config_id", sa.String(36), primary_key=True),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("deployment_id", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("token_type", sa.String(16), nullable=False),
        sa.Column("rate_per_million", sa.Numeric(18, 8), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "agent_run_results_summary",
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.agent_run_id"),
            primary_key=True,
        ),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_run_results_summary")
    op.drop_table("pricing_config_versions")
    op.drop_index("ix_agent_run_attempts_agent_run_id", table_name="agent_run_attempts")
    op.drop_table("agent_run_attempts")
    op.drop_index(
        "ix_agent_run_telemetry_agent_run_id", table_name="agent_run_telemetry"
    )
    op.drop_table("agent_run_telemetry")
    op.drop_column("agent_runs", "original_run_id")
