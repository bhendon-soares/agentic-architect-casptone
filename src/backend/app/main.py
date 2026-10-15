"""ASGI entry point for the support API."""

import os
from datetime import datetime, timezone
from hashlib import sha256
from ipaddress import ip_address
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.adapters.tickets import TicketOutcomeUnknown, TicketRejected, create_incident
from app.knowledge.catalog import sync_catalog
from app.persistence.database import get_session
from app.persistence.models import (
    AgentEvent,
    AgentRun,
    ChatMessage,
    ChatSession,
    KnowledgeSource,
    Ticket,
)
from app.runtime.crew import (
    InvalidAgentOutput,
    RuntimeUnavailable,
    TicketPayloadDraft,
    run_workflow,
)
from app.runtime.policy import TriageResult, redact, requests_third_party_secret

app = FastAPI(title="IT Help Desk MVP")


def envelope(
    data: object, request: Request, agent_run_id: str | None = None, **meta: object
) -> dict:
    return {
        "data": data,
        "error": None,
        "meta": {
            "request_id": request.state.request_id,
            "agent_run_id": agent_run_id,
            **meta,
        },
    }


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    code = exc.detail if isinstance(exc.detail, str) else "INVALID_REQUEST"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "data": None,
            "error": {
                "code": code,
                "message": code,
                "retryable": False,
                "details": None,
            },
            "meta": {"request_id": request.state.request_id, "agent_run_id": None},
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "data": None,
            "error": {
                "code": "INVALID_REQUEST",
                "message": "Dados invalidos.",
                "retryable": False,
                "details": None,
            },
            "meta": {"request_id": request.state.request_id, "agent_run_id": None},
        },
    )


def identifier(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(422, "INVALID_ID") from exc


def local_admin(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host == "testclient":
        return
    try:
        if ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(403, "ADMIN_LOCAL_ONLY")


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class MessageInput(BaseModel):
    message_text: str = Field(min_length=1, max_length=2000)


MINIMUM_TICKET_DATA_MESSAGE = (
    "Nao ha dados suficientes para abrir um incidente. "
    "Procure o suporte pelo canal oficial."
)


def failure(
    request: Request, code: str, status: int, agent_run_id: str | None = None
) -> JSONResponse:
    messages = {
        "TURN_IN_PROGRESS": "Aguarde o atendimento atual.",
        "IDEMPOTENCY_CONFLICT": "Esta chave ja foi usada com outra mensagem.",
        "TICKET_CREATE_FAILED": (
            "A criacao falhou. Consulte o registro local antes de tentar novamente."
        ),
        "TICKET_OUTCOME_UNKNOWN": (
            "Nao foi possivel confirmar o incidente. "
            "Consulte o suporte antes de tentar novamente."
        ),
        "RUNTIME_UNAVAILABLE": "Atendimento temporariamente indisponivel.",
        "AGENT_OUTPUT_INVALID": "Nao foi possivel validar a resposta do atendimento.",
        "MINIMUM_TICKET_DATA_MISSING": MINIMUM_TICKET_DATA_MESSAGE,
    }
    return JSONResponse(
        status_code=status,
        content={
            "data": None,
            "error": {
                "code": code,
                "message": messages.get(code, code),
                "retryable": False,
                "details": None,
            },
            "meta": {
                "request_id": request.state.request_id,
                "agent_run_id": agent_run_id,
            },
        },
    )


def ticket_data(ticket: Ticket) -> dict:
    return {
        name: getattr(ticket, name)
        for name in (
            "ticket_id",
            "session_id",
            "agent_run_id",
            "status",
            "adapter_mode",
            "internal_category",
            "servicenow_category",
            "impact",
            "urgency",
            "resulting_priority",
            "servicenow_sys_id",
            "servicenow_number",
            "redacted_payload",
            "error_code",
            "source_refs",
            "created_at",
            "updated_at",
        )
    }


@app.get("/health")
def health(request: Request) -> dict:
    return envelope({"status": "ok"}, request)


@app.post("/api/chat/sessions", status_code=201)
def create_session(request: Request, db: Session = Depends(get_session)) -> dict:
    record = ChatSession()
    db.add(record)
    db.commit()
    db.refresh(record)
    return envelope(
        {
            "session_id": record.session_id,
            "status": record.status,
            "clarification_count": record.clarification_count,
            "created_at": record.created_at,
        },
        request,
    )


@app.post("/api/chat/sessions/{session_id}/messages")
def post_message(
    session_id: str,
    body: MessageInput,
    request: Request,
    idempotency_key: str | None = Header(None, max_length=128),
    db: Session = Depends(get_session),
):
    session_id = identifier(session_id)
    text = body.message_text.strip()
    if not text:
        return failure(request, "INVALID_MESSAGE", 422)
    safe_text = redact(text)
    request_hash = sha256(safe_text.encode()).hexdigest()
    record = db.scalar(
        select(ChatSession)
        .where(ChatSession.session_id == session_id)
        .with_for_update()
    )
    if record is None:
        return failure(request, "SESSION_NOT_FOUND", 404)
    if idempotency_key:
        previous = db.scalar(
            select(AgentRun).where(
                AgentRun.session_id == session_id,
                AgentRun.idempotency_key == idempotency_key,
            )
        )
        if previous is not None:
            if previous.request_hash != request_hash:
                return failure(
                    request, "IDEMPOTENCY_CONFLICT", 409, previous.agent_run_id
                )
            if previous.status == "running":
                return failure(request, "TURN_IN_PROGRESS", 409, previous.agent_run_id)
            if previous.error_code:
                status = {
                    "TICKET_CREATE_FAILED": 502,
                    "TICKET_OUTCOME_UNKNOWN": 504,
                    "RUNTIME_UNAVAILABLE": 503,
                    "MINIMUM_TICKET_DATA_MISSING": 422,
                }.get(previous.error_code, 502)
                return failure(
                    request, previous.error_code, status, previous.agent_run_id
                )
            return envelope(previous.response_data, request, previous.agent_run_id)
    if db.scalar(
        select(AgentRun.agent_run_id).where(
            AgentRun.session_id == session_id, AgentRun.status == "running"
        )
    ):
        return failure(request, "TURN_IN_PROGRESS", 409)
    run = AgentRun(
        session_id=session_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    db.add(run)
    db.flush()
    db.add(
        ChatMessage(
            session_id=session_id,
            agent_run_id=run.agent_run_id,
            role="user",
            message_pt_br=safe_text,
        )
    )
    db.commit()

    try:
        if requests_third_party_secret(text):
            result = {
                "action": "blocked",
                "message": (
                    "Nao posso fornecer a senha de outra pessoa. "
                    "Procure o suporte pelos canais oficiais."
                ),
                "summary": "Pedido bloqueado por seguranca.",
                "sources": [],
                "triage": None,
                "payload": None,
            }
        else:
            workflow_text = safe_text
            if record.clarification_count:
                question = db.scalar(
                    select(ChatMessage)
                    .where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == "assistant",
                    )
                    .order_by(
                        ChatMessage.created_at.desc(), ChatMessage.message_id.desc()
                    )
                    .limit(1)
                )
                if question is not None:
                    original = db.scalar(
                        select(ChatMessage).where(
                            ChatMessage.agent_run_id == question.agent_run_id,
                            ChatMessage.role == "user",
                        )
                    )
                    if original is not None:
                        workflow_text = (
                            f"Relato inicial: {original.message_pt_br}\n"
                            f"Pergunta de esclarecimento: {question.message_pt_br}\n"
                            f"Resposta do usuario: {safe_text}"
                        )
            result = run_workflow(
                workflow_text, record.clarification_count, db, run.agent_run_id
            )
        result["message"] = redact(result["message"])
        result["summary"] = redact(result["summary"])
        result["sources"] = [
            {
                "title": redact(source["title"]),
                "path": source["path"],
                "snippet": redact(source["snippet"]),
            }
            for source in result["sources"]
        ]
        if result["payload"] is not None:
            result["payload"] = {
                key: redact(value) if isinstance(value, str) else value
                for key, value in result["payload"].items()
            }
    except RuntimeUnavailable:
        run.status, run.error_code = "failed", "RUNTIME_UNAVAILABLE"
        db.commit()
        return failure(request, "RUNTIME_UNAVAILABLE", 503, run.agent_run_id)
    except Exception as exc:
        code = "AGENT_OUTPUT_INVALID"
        reasons = {
            "Unknown category": "UNKNOWN_CATEGORY",
            "Unregistered evidence": "UNREGISTERED_EVIDENCE",
            "Unapproved response": "POLICY_UNAPPROVED",
            "Response without evidence": "RESPONSE_WITHOUT_EVIDENCE",
            "Clarification limit reached": "CLARIFICATION_LIMIT_REACHED",
            "Minimum ticket data missing": "MINIMUM_TICKET_DATA_MISSING",
            "Ticket fields mismatch": "TICKET_FIELDS_MISMATCH",
        }
        reason = (
            reasons.get(str(exc), "WORKFLOW_FAILED")
            if isinstance(exc, InvalidAgentOutput)
            else "WORKFLOW_FAILED"
        )
        if reason == "MINIMUM_TICKET_DATA_MISSING":
            code = reason
        run.status, run.error_code = "failed", code
        db.add(
            AgentEvent(
                agent_run_id=run.agent_run_id,
                task_id="workflow",
                producer="backend",
                status="failed",
                payload_redacted={"code": code},
                validation_errors_redacted=[{"code": reason}],
            )
        )
        db.commit()
        return failure(request, code, 422 if code == "MINIMUM_TICKET_DATA_MISSING" else 502, run.agent_run_id)

    action = result["action"]
    if action not in ("respond", "ask_clarification", "open_ticket", "blocked") or (
        action == "respond" and not result["sources"]
    ):
        run.status, run.error_code = "failed", "AGENT_OUTPUT_INVALID"
        db.commit()
        return failure(request, "AGENT_OUTPUT_INVALID", 502, run.agent_run_id)
    if action == "ask_clarification":
        if record.clarification_count:
            run.status, run.error_code = "failed", "AGENT_OUTPUT_INVALID"
            db.commit()
            return failure(request, "AGENT_OUTPUT_INVALID", 502, run.agent_run_id)
        record.clarification_count += 1
    run.final_action = action
    db.add(
        AgentEvent(
            agent_run_id=run.agent_run_id,
            task_id="decision",
            producer="backend",
            status="validated",
            payload_redacted={"final_action": action},
        )
    )
    ticket = None
    if action == "open_ticket":
        triage = result["triage"]
        payload = result["payload"]
        try:
            validated_triage = TriageResult.model_validate(
                {
                    **triage,
                    "missing_required_fields": triage.get(
                        "missing_required_fields", []
                    ),
                }
            )
            validated_payload = TicketPayloadDraft.model_validate(payload)
            assert (
                validated_triage.confidence >= 0.70
                or record.clarification_count == 1
            )
            assert not validated_triage.missing_required_fields
            assert validated_payload.impact == validated_triage.impact
            assert validated_payload.urgency == validated_triage.urgency
            assert validated_payload.category == validated_triage.servicenow_category
        except (AssertionError, AttributeError, TypeError, ValueError):
            run.status, run.error_code = "failed", "AGENT_OUTPUT_INVALID"
            db.commit()
            return failure(request, "AGENT_OUTPUT_INVALID", 502, run.agent_run_id)
        ticket = Ticket(
            session_id=session_id,
            agent_run_id=run.agent_run_id,
            adapter_mode=os.getenv("TICKET_ADAPTER_MODE", "mock"),
            internal_category=triage["internal_category"],
            servicenow_category=triage["servicenow_category"],
            impact=triage["impact"],
            urgency=triage["urgency"],
            resulting_priority=triage["resulting_priority"],
            redacted_payload=payload,
        )
        db.add(ticket)
        db.commit()
        try:
            incident = create_incident(payload, run.agent_run_id, ticket.adapter_mode)
        except (TicketRejected, TicketOutcomeUnknown) as exc:
            uncertain = isinstance(exc, TicketOutcomeUnknown)
            code = "TICKET_OUTCOME_UNKNOWN" if uncertain else "TICKET_CREATE_FAILED"
            run.status = ticket.status = "outcome_unknown" if uncertain else "failed"
            run.error_code = ticket.error_code = code
            run.finished_at = datetime.now(timezone.utc)
            db.add(
                AgentEvent(
                    agent_run_id=run.agent_run_id,
                    task_id="ticket",
                    producer="backend",
                    status=ticket.status,
                    payload_redacted={"code": code},
                )
            )
            db.commit()
            return failure(request, code, 504 if uncertain else 502, run.agent_run_id)
        ticket.status = "created"
        ticket.servicenow_sys_id, ticket.servicenow_number = (
            incident.sys_id,
            incident.number,
        )
        result["message"] = (
            "Abri um incidente para validacao manual pelo suporte. "
            f"Numero: {incident.number}."
        )

    turn = {
        "session_id": session_id,
        "agent_run_id": run.agent_run_id,
        "final_action": action,
        "message_pt_br": result["message"],
        "summary": result["summary"],
        "sources": result["sources"],
        "triage": result["triage"],
        "ticket": {
            "ticket_id": ticket.ticket_id,
            "status": ticket.status,
            "servicenow_sys_id": ticket.servicenow_sys_id,
            "servicenow_number": ticket.servicenow_number,
        }
        if ticket
        else None,
    }
    run.response_data = turn
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    db.add(
        ChatMessage(
            session_id=session_id,
            agent_run_id=run.agent_run_id,
            role="assistant",
            message_pt_br=result["message"],
        )
    )
    db.commit()
    return envelope(turn, request, run.agent_run_id)


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(
    session_id: str, request: Request, db: Session = Depends(get_session)
) -> dict:
    session_id = identifier(session_id)
    record = db.get(ChatSession, session_id)
    if record is None:
        raise HTTPException(404, "SESSION_NOT_FOUND")
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.message_id)
    ).all()
    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.session_id == session_id)
        .order_by(AgentRun.started_at, AgentRun.agent_run_id)
    ).all()
    return envelope(
        {
            "session_id": session_id,
            "status": record.status,
            "clarification_count": record.clarification_count,
            "messages": [
                {
                    "message_id": message.message_id,
                    "agent_run_id": message.agent_run_id,
                    "role": message.role,
                    "message_pt_br": message.message_pt_br,
                    "created_at": message.created_at,
                }
                for message in messages
            ],
            "turns": [run.response_data for run in runs if run.response_data],
            "outcomes": [
                {
                    "agent_run_id": run.agent_run_id,
                    "code": run.error_code,
                    "message_pt_br": MINIMUM_TICKET_DATA_MESSAGE,
                }
                for run in runs
                if run.error_code == "MINIMUM_TICKET_DATA_MISSING"
            ],
        },
        request,
    )


@app.get("/api/admin/conversations")
def list_conversations(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
    _: None = Depends(local_admin),
) -> dict:
    activities = union_all(
        select(ChatSession.session_id, ChatSession.updated_at.label("at")),
        select(ChatMessage.session_id, ChatMessage.created_at.label("at")),
        select(AgentRun.session_id, AgentRun.started_at.label("at")),
        select(AgentRun.session_id, AgentRun.finished_at.label("at")).where(
            AgentRun.finished_at.is_not(None)
        ),
        select(Ticket.session_id, Ticket.updated_at.label("at")),
    ).subquery()
    last_activity = (
        select(activities.c.session_id, func.max(activities.c.at).label("at"))
        .group_by(activities.c.session_id)
        .subquery()
    )
    ranked_runs = (
        select(
            AgentRun.session_id,
            AgentRun.status,
            AgentRun.final_action,
            AgentRun.error_code,
            func.row_number()
            .over(
                partition_by=AgentRun.session_id,
                order_by=(AgentRun.started_at.desc(), AgentRun.agent_run_id.desc()),
            )
            .label("position"),
        )
        .subquery()
    )
    total = db.scalar(select(func.count()).select_from(ChatSession)) or 0
    rows = db.execute(
        select(ChatSession, last_activity.c.at, ranked_runs)
        .join(last_activity, last_activity.c.session_id == ChatSession.session_id)
        .outerjoin(
            ranked_runs,
            (ranked_runs.c.session_id == ChatSession.session_id)
            & (ranked_runs.c.position == 1),
        )
        .order_by(last_activity.c.at.desc(), ChatSession.session_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return envelope(
        {
            "items": [
                {
                    "session_id": record.session_id,
                    "status": record.status,
                    "created_at": utc_iso(record.created_at),
                    "updated_at": utc_iso(record.updated_at),
                    "last_activity_at": utc_iso(activity),
                    "last_run": {
                        "final_action": final_action,
                        "run_status": run_status,
                        "error_code": error_code,
                    }
                    if run_status is not None
                    else None,
                }
                for record, activity, _, run_status, final_action, error_code, _ in rows
            ],
            "total": total,
        },
        request,
        limit=limit,
        offset=offset,
    )


@app.get("/api/admin/conversations/{session_id}")
def get_admin_conversation(
    session_id: str,
    request: Request,
    db: Session = Depends(get_session),
    _: None = Depends(local_admin),
) -> dict:
    session_id = identifier(session_id)
    record = db.get(ChatSession, session_id)
    if record is None:
        raise HTTPException(404, "SESSION_NOT_FOUND")
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.message_id)
    ).all()
    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.session_id == session_id)
        .order_by(AgentRun.started_at, AgentRun.agent_run_id)
    ).all()
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.session_id == session_id)
        .order_by(Ticket.created_at, Ticket.ticket_id)
    ).all()
    return envelope(
        {
            "session_id": session_id,
            "status": record.status,
            "created_at": utc_iso(record.created_at),
            "updated_at": utc_iso(record.updated_at),
            "clarification_count": record.clarification_count,
            "messages": [
                {
                    "message_id": message.message_id,
                    "agent_run_id": message.agent_run_id,
                    "role": message.role,
                    "message_pt_br": redact(message.message_pt_br),
                    "created_at": utc_iso(message.created_at),
                }
                for message in messages
            ],
            "runs": [
                {
                    "agent_run_id": run.agent_run_id,
                    "status": run.status,
                    "started_at": utc_iso(run.started_at),
                    "finished_at": utc_iso(run.finished_at),
                    "final_action": run.final_action,
                    "error_code": run.error_code,
                    "summary": redact(run.response_data["summary"])
                    if run.response_data and run.response_data.get("summary")
                    else None,
                    "sources": [
                        {
                            "title": redact(source["title"]),
                            "path": redact(source["path"]),
                            "snippet": redact(source["snippet"]),
                        }
                        for source in (run.response_data.get("sources") or [])
                    ]
                    if run.response_data
                    else [],
                }
                for run in runs
            ],
            "tickets": [
                {
                    "ticket_id": ticket.ticket_id,
                    "agent_run_id": ticket.agent_run_id,
                    "status": ticket.status,
                    "error_code": ticket.error_code,
                    "servicenow_number": ticket.servicenow_number,
                    "created_at": utc_iso(ticket.created_at),
                    "updated_at": utc_iso(ticket.updated_at),
                }
                for ticket in tickets
            ],
        },
        request,
    )


@app.get("/api/tickets")
def list_tickets(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
) -> dict:
    total = db.scalar(select(func.count()).select_from(Ticket))
    items = db.scalars(
        select(Ticket)
        .order_by(Ticket.created_at.desc(), Ticket.ticket_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return envelope(
        {"items": [ticket_data(item) for item in items], "total": total},
        request,
        limit=limit,
        offset=offset,
    )


@app.get("/api/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str, request: Request, db: Session = Depends(get_session)
) -> dict:
    ticket = db.get(Ticket, identifier(ticket_id))
    if ticket is None:
        raise HTTPException(404, "TICKET_NOT_FOUND")
    return envelope(ticket_data(ticket), request)


@app.get("/api/agent-runs/{agent_run_id}")
def get_run(
    agent_run_id: str, request: Request, db: Session = Depends(get_session)
) -> dict:
    run = db.get(AgentRun, identifier(agent_run_id))
    if run is None:
        raise HTTPException(404, "RUN_NOT_FOUND")
    events = db.scalars(
        select(AgentEvent)
        .where(AgentEvent.agent_run_id == run.agent_run_id)
        .order_by(AgentEvent.created_at, AgentEvent.event_id)
    ).all()
    return envelope(
        {
            "agent_run_id": run.agent_run_id,
            "session_id": run.session_id,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "final_action": run.final_action,
            "error_code": run.error_code,
            "events": [
                {
                    "event_id": event.event_id,
                    "task_id": event.task_id,
                    "producer": event.producer,
                    "status": event.status,
                    "created_at": event.created_at,
                    "payload": event.payload_redacted,
                    "validation_errors": event.validation_errors_redacted,
                }
                for event in events
            ],
        },
        request,
        run.agent_run_id,
    )


@app.get("/api/metrics/summary")
def metrics(request: Request, db: Session = Depends(get_session)) -> dict:
    def count(statement):
        return db.scalar(statement) or 0

    return envelope(
        {
            "total_conversations": count(select(func.count()).select_from(ChatSession)),
            "tickets_created": count(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.status == "created")
            ),
            "responses_with_source": count(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.status == "completed")
                .where(AgentRun.final_action == "respond")
                .where(AgentRun.response_data.is_not(None))
                .where(func.json_array_length(AgentRun.response_data["sources"]) > 0)
            ),
            "blocked_requests": count(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.final_action == "blocked")
            ),
        },
        request,
    )


@app.get("/api/knowledge/sources")
def knowledge_sources(request: Request, db: Session = Depends(get_session)) -> dict:
    sync_catalog(db)
    sources = db.scalars(select(KnowledgeSource).order_by(KnowledgeSource.path)).all()
    return envelope(
        {
            "items": [
                {
                    "title": item.title,
                    "path": item.path,
                    "internal_category": item.internal_category,
                    "approved": item.approved,
                }
                for item in sources
            ]
        },
        request,
    )
