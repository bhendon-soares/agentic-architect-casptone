"""Sequential, validated agent stages; no agent can write to ServiceNow."""

import os
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from crewai import LLM, Agent, Crew, Process, Task
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.catalog import knowledge_base, sync_catalog
from app.persistence.models import AgentEvent, AgentRunTelemetry, KnowledgeSource
from app.runtime.policy import CATEGORIES, TriageResult, priority, redact

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
AGENTS_CONFIG = CONFIG_DIR / "agents.yaml"
TASKS_CONFIG = CONFIG_DIR / "tasks.yaml"
PROCESS = Process.sequential
ALLOW_DELEGATION = False
MEMORY_ENABLED = False
MAX_ITER = 12
MAX_EXECUTION_SECONDS = 60
LLM_TIMEOUT_SECONDS = 30


class ResponseDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_pt_br: str = Field(min_length=1)
    candidate_action: Literal["respond", "ask_clarification", "open_ticket", "blocked"]
    summary: str = Field(min_length=1)


class TriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    internal_category: str
    impact: int = Field(ge=1, le=3)
    urgency: int = Field(ge=1, le=3)
    confidence: float = Field(ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)


class EvidenceSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_paths: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    veto_to_blocked: bool


class TicketPayloadDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    short_description: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    impact: int = Field(ge=1, le=3)
    urgency: int = Field(ge=1, le=3)
    category: str


class RuntimeUnavailable(Exception):
    pass


class InvalidAgentOutput(Exception):
    pass


def local_evidence(category: str, db: Session) -> list[dict]:
    if category not in CATEGORIES or category == "unknown":
        return []
    base = knowledge_base()
    source = (base / f"{category}.md").resolve()
    if not source.is_relative_to(base) or not source.is_file():
        return []
    content = source.read_text(encoding="utf-8")
    record = db.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.path == f"knowledge/{category}.md"
        )
    )
    if (
        record is None
        or not record.approved
        or record.internal_category != category
        or record.content_hash != sha256(content.encode()).hexdigest()
        or "Aprovacao: somente para demo" not in content
        or not content.strip()
    ):
        return []
    return [
        {
            "title": redact(content.splitlines()[0].lstrip("# ")),
            "path": f"knowledge/{category}.md",
            "snippet": redact(content.split("## ")[-1].strip())[:500],
        }
    ]


def run_workflow(
    message: str, clarification_count: int, db: Session, agent_run_id: str
) -> dict:
    model = os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeUnavailable("LLM model not configured")
    if model.startswith("azure/") and not all(
        os.getenv(name) for name in ("AZURE_API_KEY", "AZURE_ENDPOINT")
    ):
        raise RuntimeUnavailable("Azure LLM configuration incomplete")
    try:
        max_rpm = int(os.getenv("LLM_MAX_RPM", "10"))
    except ValueError as exc:
        raise RuntimeUnavailable("Invalid LLM rate limit") from exc
    if max_rpm <= 0:
        raise RuntimeUnavailable("Invalid LLM rate limit")

    sync_catalog(db)
    agents_config = yaml.safe_load(AGENTS_CONFIG.read_text(encoding="utf-8"))
    tasks_config = yaml.safe_load(TASKS_CONFIG.read_text(encoding="utf-8"))
    stages = {
        "IntakeTriageAgent": "triage",
        "KnowledgeAgent": "knowledge",
        "ResponseAgent": "response",
        "QAPolicyAgent": "policy",
        "TicketingEscalationAgent": "ticketing",
    }

    def stage(
        role: str, goal: str, description: str, schema: type[BaseModel]
    ) -> BaseModel:
        name = stages[role]
        if (
            agents_config[name]["role"] != role
            or tasks_config[name]["output"] != schema.__name__
        ):
            raise RuntimeUnavailable("Crew configuration mismatch")
        llm_options = {"model": model, "timeout": LLM_TIMEOUT_SECONDS}
        if (
            model.startswith("azure/")
            and urlparse(os.environ["AZURE_ENDPOINT"]).path.rstrip("/") == "/openai/v1"
        ):
            llm_options.update(
                model=f"openai/{model.removeprefix('azure/')}",
                base_url=os.environ["AZURE_ENDPOINT"],
                api_key=os.environ["AZURE_API_KEY"],
            )
        agent = Agent(
            role=agents_config[name]["role"],
            goal=agents_config[name]["goal"],
            backstory="Suporte interno em portugues brasileiro.",
            allow_delegation=ALLOW_DELEGATION,
            max_iter=MAX_ITER,
            max_rpm=max_rpm,
            max_execution_time=MAX_EXECUTION_SECONDS,
            llm=LLM(**llm_options),
            verbose=False,
        )
        task = Task(
            description=description,
            expected_output="JSON valido para o schema solicitado.",
            agent=agent,
            output_pydantic=schema,
            max_retry_limit=2,
        )
        telemetry = AgentRunTelemetry(
            agent_run_id=agent_run_id,
            step_index=list(stages).index(role),
            step_name=name,
            timestamp_start=datetime.now(timezone.utc),
            state="running",
        )
        db.add(telemetry)
        db.commit()
        started = time.perf_counter()
        try:
            result = Crew(
                agents=[agent],
                tasks=[task],
                process=PROCESS,
                memory=MEMORY_ENABLED,
                verbose=False,
            ).kickoff()
            if result.pydantic is None:
                raise InvalidAgentOutput("Invalid structured output")
            validated = schema.model_validate(result.pydantic.model_dump())
        except Exception:
            telemetry.state = "failed"
            db.add(
                AgentEvent(
                    agent_run_id=agent_run_id,
                    task_id=name,
                    producer=role,
                    status="failed",
                    validation_errors_redacted=[{"code": "STAGE_FAILED"}],
                )
            )
            raise
        else:
            telemetry.state = "complete"
        finally:
            telemetry.timestamp_end = datetime.now(timezone.utc)
            telemetry.duration_ms = max(0.0, (time.perf_counter() - started) * 1000)
            db.commit()
        db.add(
            AgentEvent(
                agent_run_id=agent_run_id,
                task_id=name,
                producer=role,
                status="validated",
                payload_redacted={"output_schema": schema.__name__},
            )
        )
        db.commit()
        return validated

    triage_input = stage(
        "IntakeTriageAgent",
        "Classificar e priorizar com seguranca",
        f"Classifique o relato redigido: {message}. "
        f"Escolha internal_category entre {list(CATEGORIES)}. "
        "Indique impact, urgency, confidence, risk_flags e missing_required_fields.",
        TriageInput,
    )
    if triage_input.internal_category not in CATEGORIES:
        raise InvalidAgentOutput("Unknown category")
    if clarification_count and triage_input.missing_required_fields:
        raise InvalidAgentOutput("Minimum ticket data missing")
    triage_fields = {
        **triage_input.model_dump(),
        "risk_flags": [redact(flag) for flag in triage_input.risk_flags],
        "missing_required_fields": [
            redact(field) for field in triage_input.missing_required_fields
        ],
        "servicenow_category": CATEGORIES[triage_input.internal_category],
        "resulting_priority": priority(
            triage_input.internal_category, triage_input.impact, triage_input.urgency
        ),
    }
    sources = local_evidence(triage_input.internal_category, db)
    evidence = stage(
        "KnowledgeAgent",
        "Selecionar somente evidencia local aplicavel",
        f"Relato redigido: {message}. Fontes elegiveis: {sources}. "
        "Retorne selected_paths apenas para fonte operacional realmente aplicavel. "
        "Se nenhuma fonte se aplica, retorne lista vazia.",
        EvidenceSet,
    )
    eligible = {source["path"] for source in sources}
    if any(path not in eligible for path in evidence.selected_paths):
        raise InvalidAgentOutput("Unregistered evidence")
    sources = [
        source for source in sources if source["path"] in evidence.selected_paths
    ]
    draft = stage(
        "ResponseAgent",
        "Redigir resposta fundamentada",
        f"Relato: {message}. Triagem validada: {triage_fields}. "
        f"Fonte local elegivel: {sources}. "
        f"Esclarecimentos anteriores: {clarification_count}. "
        "Com confidence abaixo de 0.70, pergunte no primeiro turno. "
        "Apos um esclarecimento, proponha ticket se houver dados minimos seguros. "
        "Se ja houve esclarecimento, o relato inclui a pergunta anterior e a "
        "resposta do usuario; nao use ask_clarification novamente. "
        "candidate_action deve ser exatamente respond, ask_clarification, "
        "open_ticket ou blocked. Use respond apenas quando a fonte sustentar "
        "a instrucao; "
        "se nao, pergunte uma vez ou proponha ticket. Nao invente procedimentos.",
        ResponseDraft,
    )
    policy = stage(
        "QAPolicyAgent",
        "Revisar seguranca e evidencias",
        f"Relato redigido: {message}. Fonte: {sources}. "
        f"Resposta: {draft.model_dump_json()}. Vete instrucoes inseguras ou "
        "procedimentos sem fonte. Abrir ticket ou pedir esclarecimento sem "
        "fonte e permitido se a resposta nao inventar procedimentos e for segura. "
        "Vete e bloqueie somente pedidos inseguros; aprove encaminhamento seguro.",
        PolicyDecision,
    )
    action = "blocked" if policy.veto_to_blocked else draft.candidate_action
    if action != "blocked" and triage_input.confidence < 0.70:
        action = "open_ticket" if clarification_count else "ask_clarification"
    if action not in ("respond", "ask_clarification", "open_ticket", "blocked"):
        raise InvalidAgentOutput("Unknown action")
    if not policy.approved and not policy.veto_to_blocked:
        raise InvalidAgentOutput("Unapproved response")
    triage = TriageResult.model_validate({**triage_fields, "initial_action": action})
    if action == "respond" and not sources:
        raise InvalidAgentOutput("Response without evidence")
    if action == "ask_clarification" and clarification_count:
        raise InvalidAgentOutput("Clarification limit reached")
    payload = None
    if action == "open_ticket":
        if triage.missing_required_fields:
            raise InvalidAgentOutput("Minimum ticket data missing")
        payload = stage(
            "TicketingEscalationAgent",
            "Preparar incidente redigido",
            f"Relato redigido: {message}. Triagem: {triage.model_dump_json()}. "
            "Retorne somente cinco campos: short_description, description, "
            "impact, urgency, category. Sem dados pessoais ou credenciais.",
            TicketPayloadDraft,
        )
        if (
            payload.impact != triage.impact
            or payload.urgency != triage.urgency
            or payload.category != triage.servicenow_category
        ):
            raise InvalidAgentOutput("Ticket fields mismatch")
    return {
        "action": action,
        "message": (
            "Nao posso atender a este pedido. Procure o suporte pelos canais oficiais."
            if action == "blocked"
            else (
                "Qual servico apresenta o problema e o que acontece ao tentar "
                "acessa-lo?"
            )
            if action == "ask_clarification" and draft.candidate_action != action
            else redact(draft.message_pt_br)
        ),
        "summary": (
            "Pedido bloqueado por seguranca."
            if action == "blocked"
            else "Encaminhamento para suporte manual."
            if action == "open_ticket" and draft.candidate_action != action
            else redact(draft.summary)
        ),
        "sources": sources if action == "respond" else [],
        "triage": triage.model_dump(exclude={"missing_required_fields"}),
        "payload": {
            field: redact(str(value)) if isinstance(value, str) else value
            for field, value in payload.model_dump().items()
        }
        if payload
        else None,
    }
