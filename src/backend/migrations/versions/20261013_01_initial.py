"""Initial P0 schema.

Revision ID: 20261013_01
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "20261013_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("clarification_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("clarification_count BETWEEN 0 AND 1"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("agent_run_id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("chat_sessions.session_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("final_action", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("model_config_safe", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("request_hash", sa.String(64)),
        sa.Column("response_data", sa.JSON()),
        sa.UniqueConstraint("session_id", "idempotency_key"),
    )
    op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_table(
        "chat_messages",
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("chat_sessions.session_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.agent_run_id")
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("message_pt_br", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_table(
        "agent_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.agent_run_id"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("producer", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("payload_redacted", sa.JSON(), nullable=False),
        sa.Column("validation_errors_redacted", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_events_agent_run_id", "agent_events", ["agent_run_id"])
    op.create_table(
        "knowledge_sources",
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.Column("path", sa.String(255), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("internal_category", sa.String(64), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "tickets",
        sa.Column("ticket_id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("chat_sessions.session_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.agent_run_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("adapter_mode", sa.String(16), nullable=False),
        sa.Column("internal_category", sa.String(64), nullable=False),
        sa.Column("servicenow_category", sa.String(64), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=False),
        sa.Column("urgency", sa.Integer(), nullable=False),
        sa.Column("resulting_priority", sa.String(2), nullable=False),
        sa.Column("redacted_payload", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("servicenow_sys_id", sa.String(64)),
        sa.Column("servicenow_number", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tickets_session_id", "tickets", ["session_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])


def downgrade() -> None:
    op.drop_table("tickets")
    op.drop_table("knowledge_sources")
    op.drop_table("agent_events")
    op.drop_table("chat_messages")
    op.drop_table("agent_runs")
    op.drop_table("chat_sessions")
