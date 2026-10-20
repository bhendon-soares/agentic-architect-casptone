"""Persistence models for the support workflow."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (CheckConstraint("clarification_count BETWEEN 0 AND 1"),)

    session_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    status: Mapped[str] = mapped_column(String(24), default="active")
    clarification_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key"),)

    agent_run_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    finished_at: Mapped[datetime | None]
    final_action: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    model_config_safe: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    response_data: Mapped[dict | None] = mapped_column(JSON)
    original_run_id: Mapped[str | None] = mapped_column(String(36))


class AgentRunTelemetry(Base):
    __tablename__ = "agent_run_telemetry"
    __table_args__ = (UniqueConstraint("agent_run_id", "step_index"),)

    telemetry_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id"), index=True
    )
    step_index: Mapped[int]
    step_name: Mapped[str] = mapped_column(String(32))
    model_used: Mapped[str | None] = mapped_column(String(255))
    deployment_id: Mapped[str | None] = mapped_column(String(255))
    timestamp_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timestamp_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None]
    state: Mapped[str] = mapped_column(String(16))
    tokens_input: Mapped[int | None]
    tokens_output: Mapped[int | None]
    tokens_cache: Mapped[int | None]
    cache_in_input: Mapped[bool | None]
    estimated_cost_value: Mapped[float | None] = mapped_column(Numeric(18, 8))
    estimated_cost_currency: Mapped[str | None] = mapped_column(String(3))
    pricing_config_id: Mapped[str | None] = mapped_column(String(36))


class AgentRunAttempt(Base):
    __tablename__ = "agent_run_attempts"

    attempt_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id"), index=True
    )
    step_index: Mapped[int | None]
    attempt_type: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    observed_at: Mapped[datetime] = mapped_column(default=utc_now)


class PricingConfigVersion(Base):
    __tablename__ = "pricing_config_versions"

    pricing_config_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    model: Mapped[str] = mapped_column(String(255))
    deployment_id: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3))
    token_type: Mapped[str] = mapped_column(String(16))
    rate_per_million: Mapped[float] = mapped_column(Numeric(18, 8))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class AgentRunResultsSummary(Base):
    __tablename__ = "agent_run_results_summary"

    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id"), primary_key=True
    )
    result: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(default=utc_now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id"), index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.agent_run_id")
    )
    role: Mapped[str] = mapped_column(String(16))
    message_pt_br: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(64))
    producer: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    payload_redacted: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_errors_redacted: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    source_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    internal_category: Mapped[str] = mapped_column(String(64))
    approved: Mapped[bool] = mapped_column(default=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id"), index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.agent_run_id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    adapter_mode: Mapped[str] = mapped_column(String(16))
    internal_category: Mapped[str] = mapped_column(String(64))
    servicenow_category: Mapped[str] = mapped_column(String(64))
    impact: Mapped[int]
    urgency: Mapped[int]
    resulting_priority: Mapped[str] = mapped_column(String(2))
    redacted_payload: Mapped[dict] = mapped_column(JSON)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    servicenow_sys_id: Mapped[str | None] = mapped_column(String(64))
    servicenow_number: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
