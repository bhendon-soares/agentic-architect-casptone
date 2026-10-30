"""ASGI entry point for the support API."""

import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text, union_all
from sqlalchemy.orm import Session

from app.adapters.tickets import TicketOutcomeUnknown, TicketRejected, create_incident
from app.auth import (
    client_ip,
    current_user,
    hasher,
    normalized_email,
    require_admin,
    secret,
    set_session_cookie,
    user_data,
    validate_password,
    verify_password,
)
from app.knowledge.catalog import sync_catalog
from app.persistence.database import get_session
from app.persistence.models import (
    AgentEvent,
    AgentRun,
    AgentRunAttempt,
    AgentRunResultsSummary,
    AuthAudit,
    ChatMessage,
    ChatSession,
    KnowledgeSource,
    LoginAttempt,
    RevokedSession,
    Ticket,
    User,
    utc_now,
)
from app.runtime.crew import (
    InvalidAgentOutput,
    RuntimeUnavailable,
    TicketPayloadDraft,
    run_workflow,
)
from app.runtime.policy import TriageResult, redact, requests_third_party_secret

app = FastAPI(title="IT Help Desk MVP")
LOGIN_LOCK_DURATION = timedelta(minutes=15)
LOGIN_ATTEMPT_RESET = timedelta(hours=24)


def login_lock_active(attempt: LoginAttempt, now: datetime) -> bool:
    if attempt.locked_at is None or attempt.unlocked_at is not None:
        return False
    locked_at = attempt.locked_at.replace(tzinfo=timezone.utc)
    repeat_count = max(0, (attempt.failed_count - 5) // 5)
    return now < locked_at + LOGIN_LOCK_DURATION * (2 ** min(repeat_count, 4))


def redact_data(value: object) -> object:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, dict):
        return {
            key: item
            if key in {"session_id", "agent_run_id", "ticket_id"}
            else redact_data(item)
            for key, item in value.items()
        }
    return value


@app.on_event("startup")
def check_secret() -> None:
    secret()


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
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        allowed = {
            origin.strip()
            for origin in os.getenv("APP_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        }
        if request.headers.get("origin") not in allowed:
            return failure(request, "CSRF_REJECTED", 403)
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


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class MessageInput(BaseModel):
    message_text: str = Field(min_length=1, max_length=2000)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str


class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: str


class CreateUserInput(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    role: str = Field(pattern="^(user|admin)$")
    temporary_password: str = Field(min_length=12)


class UpdateUserInput(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=255)
    role: str | None = Field(None, pattern="^(user|admin)$")
    is_active: bool | None = None


class ResetPasswordInput(BaseModel):
    temporary_password: str = Field(min_length=12)


class UnlockInput(BaseModel):
    email: str
    ip: str


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


def ticket_data(ticket: Ticket, include_payload: bool = False) -> dict:
    data = {
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
            "error_code",
            "source_refs",
            "created_at",
            "updated_at",
        )
    }
    if not include_payload:
        return data
    data.update(
        {
            "redacted_payload": {
                name: ticket.redacted_payload.get(name)
                for name in (
                    "short_description",
                    "description",
                    "impact",
                    "urgency",
                    "category",
                )
            },
            "submission_started_at": utc_iso(ticket.submission_started_at),
            "submission_state": submission_state(ticket),
        }
    )
    return data


def submission_state(ticket: Ticket) -> str:
    # Terminal status wins: rows created before 20261021_01 have no start time.
    if ticket.status == "created":
        return "simulated" if ticket.adapter_mode == "mock" else "created"
    if ticket.status == "failed":
        return "rejected"
    if ticket.status == "outcome_unknown":
        return "uncertain"
    return "prepared" if ticket.submission_started_at is None else "attempted"


def record_result(db: Session, run: AgentRun, result: str) -> None:
    db.add(AgentRunResultsSummary(agent_run_id=run.agent_run_id, result=result))


@app.get("/health")
def health(request: Request) -> dict:
    return envelope({"status": "ok"}, request)


@app.post("/api/auth/login")
def login(body: LoginInput, request: Request, db: Session = Depends(get_session)):
    email = normalized_email(body.email)
    ip = client_ip(request)
    now = utc_now()
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"{ip}:{email}"},
        )
    attempt = db.scalar(
        select(LoginAttempt)
        .where(LoginAttempt.ip == ip, LoginAttempt.email_normalized == email)
        .with_for_update()
    )
    if attempt and login_lock_active(attempt, now):
        return failure(request, "LOGIN_LOCKED", 429)
    if attempt and attempt.last_failed_at and (
        now - attempt.last_failed_at.replace(tzinfo=timezone.utc)
        >= LOGIN_ATTEMPT_RESET
    ):
        attempt.failed_count = 0
        attempt.locked_at = None
        attempt.unlocked_at = None
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        if attempt is None:
            attempt = LoginAttempt(ip=ip, email_normalized=email, failed_count=0)
            db.add(attempt)
        attempt.failed_count += 1
        attempt.last_failed_at = now
        if attempt.failed_count >= 5 and attempt.failed_count % 5 == 0:
            attempt.locked_at = now
            attempt.unlocked_at = None
        db.add(
            AuthAudit(
                action="login_locked"
                if login_lock_active(attempt, now)
                else "login_failed",
                target_id=user.user_id if user else None,
                ip=ip,
            )
        )
        db.commit()
        return failure(request, "INVALID_CREDENTIALS", 401)
    if attempt:
        attempt.failed_count = 0
        attempt.locked_at = None
        attempt.unlocked_at = None
    db.add(
        AuthAudit(
            action="login_success", actor_id=user.user_id, target_id=user.user_id, ip=ip
        )
    )
    db.commit()
    response = JSONResponse(envelope({"user": user_data(user)}, request))
    set_session_cookie(response, user)
    return response


@app.get("/api/auth/me")
def me(request: Request, user: User = Depends(current_user)) -> dict:
    return envelope({"user": user_data(user)}, request)


@app.post("/api/auth/logout")
def logout(
    request: Request,
    db: Session = Depends(get_session),
    _: User = Depends(current_user),
):
    claims = request.state.session_claims
    db.execute(delete(RevokedSession).where(RevokedSession.expires_at <= utc_now()))
    db.add(
        RevokedSession(
            jti=claims["jti"],
            expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
        )
    )
    db.commit()
    response = JSONResponse(envelope({}, request))
    response.delete_cookie("session", path="/", httponly=True, samesite="strict")
    return response


@app.post("/api/auth/change-password")
def change_password(
    body: ChangePasswordInput,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    validate_password(body.new_password)
    if body.new_password == body.current_password or not verify_password(
        body.current_password, user.password_hash
    ):
        raise HTTPException(422, "INVALID_PASSWORD_CHANGE")
    user.password_hash = hasher.hash(body.new_password)
    user.password_changed_at = utc_now()
    user.must_change_password = False
    db.add(
        AuthAudit(
            action="password_changed",
            actor_id=user.user_id,
            target_id=user.user_id,
            ip=client_ip(request),
        )
    )
    db.commit()
    response = JSONResponse(envelope({"user": user_data(user)}, request))
    set_session_cookie(response, user)
    return response


def user_admin_data(user: User, db: Session) -> dict:
    locks = db.scalars(
        select(LoginAttempt).where(
            LoginAttempt.email_normalized == user.email,
            LoginAttempt.locked_at.is_not(None),
            LoginAttempt.unlocked_at.is_(None),
        )
    ).all()
    locks = [lock for lock in locks if login_lock_active(lock, utc_now())]
    return {
        **user_data(user),
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "login_locked": bool(locks),
        "login_locks": [{"ip": lock.ip, "locked_at": lock.locked_at} for lock in locks],
    }


@app.get("/api/admin/users")
def list_users(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> dict:
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search:
        query = query.where(
            User.email.ilike(f"%{search}%") | User.display_name.ilike(f"%{search}%")
        )
    users = db.scalars(
        query.order_by(User.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return envelope(
        {"items": [user_admin_data(user, db) for user in users], "total": total},
        request,
    )


@app.get("/api/admin/users/{user_id}")
def get_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> dict:
    user = db.get(User, identifier(user_id))
    if user is None:
        raise HTTPException(404, "USER_NOT_FOUND")
    return envelope(user_admin_data(user, db), request)


@app.post("/api/admin/users", status_code=201)
def create_user(
    body: CreateUserInput,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    email = normalized_email(body.email)
    if db.scalar(select(User.user_id).where(User.email == email)):
        raise HTTPException(409, "EMAIL_TAKEN")
    user = User(
        email=email,
        display_name=body.display_name.strip(),
        role=body.role,
        password_hash=hasher.hash(body.temporary_password),
        password_changed_at=utc_now(),
        created_by=admin.user_id,
    )
    db.add(user)
    db.flush()
    db.add(
        AuthAudit(
            action="user_created",
            actor_id=admin.user_id,
            target_id=user.user_id,
            ip=client_ip(request),
        )
    )
    db.commit()
    return envelope(user_admin_data(user, db), request)


@app.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserInput,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    user = db.get(User, identifier(user_id))
    if user is None:
        raise HTTPException(404, "USER_NOT_FOUND")
    if user.user_id == admin.user_id and body.is_active is False:
        raise HTTPException(409, "SELF_DEACTIVATION")
    if (
        user.user_id == admin.user_id
        and body.role is not None
        and body.role != user.role
    ):
        raise HTTPException(409, "SELF_ROLE_CHANGE")
    if (
        user.is_active
        and user.role == "admin"
        and (body.is_active is False or body.role == "user")
    ):
        db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.role == "admin")
            .with_for_update()
        ).all()
        active_admins = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True), User.role == "admin")
        )
        if active_admins <= 1:
            raise HTTPException(409, "LAST_ADMIN")
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    user.updated_at = utc_now()
    db.add(
        AuthAudit(
            action="user_updated",
            actor_id=admin.user_id,
            target_id=user.user_id,
            ip=client_ip(request),
        )
    )
    db.commit()
    return envelope(user_admin_data(user, db), request)


@app.post("/api/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordInput,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    user = db.get(User, identifier(user_id))
    if user is None:
        raise HTTPException(404, "USER_NOT_FOUND")
    user.password_hash = hasher.hash(body.temporary_password)
    user.password_changed_at = utc_now()
    user.must_change_password = True
    db.add(
        AuthAudit(
            action="password_reset",
            actor_id=admin.user_id,
            target_id=user.user_id,
            ip=client_ip(request),
        )
    )
    db.commit()
    return envelope(user_admin_data(user, db), request)


@app.post("/api/admin/login-locks/unlock")
def unlock_login(
    body: UnlockInput,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> dict:
    attempt = db.scalar(
        select(LoginAttempt).where(
            LoginAttempt.ip == body.ip,
            LoginAttempt.email_normalized == normalized_email(body.email),
            LoginAttempt.locked_at.is_not(None),
            LoginAttempt.unlocked_at.is_(None),
        )
    )
    if attempt is None:
        raise HTTPException(404, "LOGIN_LOCK_NOT_FOUND")
    attempt.unlocked_at = utc_now()
    attempt.unlocked_by = admin.user_id
    attempt.failed_count = 0
    db.add(
        AuthAudit(
            action="login_unlocked", actor_id=admin.user_id, ip=client_ip(request)
        )
    )
    db.commit()
    return envelope({}, request)


@app.post("/api/chat/sessions", status_code=201)
def create_session(
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict:
    record = ChatSession(user_id=user.user_id)
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
    user: User = Depends(current_user),
):
    session_id = identifier(session_id)
    text = body.message_text.strip()
    if not text:
        return failure(request, "INVALID_MESSAGE", 422)
    safe_text = redact(text)
    request_hash = sha256(safe_text.encode()).hexdigest()
    record = db.scalar(
        select(ChatSession)
        .where(
            ChatSession.session_id == session_id, ChatSession.user_id == user.user_id
        )
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
            db.add(
                AgentRunAttempt(
                    agent_run_id=previous.agent_run_id,
                    attempt_type="replay",
                    outcome="success" if not previous.error_code else "failure",
                )
            )
            db.commit()
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
    prior_failure = db.scalar(
        select(AgentRun)
        .where(
            AgentRun.session_id == session_id,
            AgentRun.request_hash == request_hash,
            AgentRun.status.in_(("failed", "outcome_unknown")),
        )
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    if prior_failure is not None:
        run.original_run_id = prior_failure.agent_run_id
    db.add(run)
    db.flush()
    if prior_failure is not None:
        db.add(
            AgentRunAttempt(
                agent_run_id=run.agent_run_id,
                attempt_type="operational_retry",
                outcome="started",
            )
        )
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
                    "Nao posso fornecer dados pessoais ou credenciais de outra pessoa. "
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
                            f"Relato inicial: {redact(original.message_pt_br)}\n"
                            "Pergunta de esclarecimento: "
                            f"{redact(question.message_pt_br)}\n"
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
        run.finished_at = datetime.now(timezone.utc)
        record_result(db, run, "failed")
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
        run.finished_at = datetime.now(timezone.utc)
        record_result(db, run, "failed")
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
        return failure(
            request,
            code,
            422 if code == "MINIMUM_TICKET_DATA_MISSING" else 502,
            run.agent_run_id,
        )

    action = result["action"]
    if action not in ("respond", "ask_clarification", "open_ticket", "blocked") or (
        action == "respond" and not result["sources"]
    ):
        run.status, run.error_code = "failed", "AGENT_OUTPUT_INVALID"
        run.finished_at = datetime.now(timezone.utc)
        record_result(db, run, "failed")
        db.commit()
        return failure(request, "AGENT_OUTPUT_INVALID", 502, run.agent_run_id)
    if action == "ask_clarification":
        if record.clarification_count:
            run.status, run.error_code = "failed", "AGENT_OUTPUT_INVALID"
            run.finished_at = datetime.now(timezone.utc)
            record_result(db, run, "failed")
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
                validated_triage.confidence >= 0.70 or record.clarification_count == 1
            )
            assert not validated_triage.missing_required_fields
            assert validated_payload.impact == validated_triage.impact
            assert validated_payload.urgency == validated_triage.urgency
            assert validated_payload.category == validated_triage.servicenow_category
        except (AssertionError, AttributeError, TypeError, ValueError):
            run.status, run.error_code = "failed", "AGENT_OUTPUT_INVALID"
            run.finished_at = datetime.now(timezone.utc)
            record_result(db, run, "failed")
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
        ticket.submission_started_at = datetime.now(timezone.utc)
        db.commit()
        try:
            incident = create_incident(payload, run.agent_run_id, ticket.adapter_mode)
        except (TicketRejected, TicketOutcomeUnknown) as exc:
            uncertain = isinstance(exc, TicketOutcomeUnknown)
            code = "TICKET_OUTCOME_UNKNOWN" if uncertain else "TICKET_CREATE_FAILED"
            run.status = ticket.status = "outcome_unknown" if uncertain else "failed"
            run.error_code = ticket.error_code = code
            run.finished_at = datetime.now(timezone.utc)
            record_result(db, run, action)
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
            "Registrei um incidente simulado (modo de teste); ele nao foi enviado "
            f"ao ServiceNow. Referencia: {incident.number}."
            if ticket.adapter_mode == "mock"
            else "Abri um incidente para validacao manual pelo suporte. "
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
            "adapter_mode": ticket.adapter_mode,
            "servicenow_sys_id": ticket.servicenow_sys_id,
            "servicenow_number": ticket.servicenow_number,
        }
        if ticket
        else None,
    }
    run.response_data = turn
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    record_result(db, run, action)
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


@app.get("/api/chat/sessions")
def list_own_sessions(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict:
    own = ChatSession.user_id == user.user_id
    records = db.scalars(
        select(ChatSession)
        .where(own)
        .order_by(ChatSession.updated_at.desc(), ChatSession.session_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return envelope(
        {
            "items": [
                {
                    "session_id": record.session_id,
                    "status": record.status,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
            "total": db.scalar(
                select(func.count()).select_from(ChatSession).where(own)
            ),
        },
        request,
    )


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> dict:
    session_id = identifier(session_id)
    record = db.scalar(
        select(ChatSession).where(
            ChatSession.session_id == session_id, ChatSession.user_id == user.user_id
        )
    )
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
                    "message_pt_br": redact(message.message_pt_br),
                    "created_at": message.created_at,
                }
                for message in messages
            ],
            "turns": [
                redact_data(run.response_data) for run in runs if run.response_data
            ],
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
    _: User = Depends(require_admin),
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
    ranked_runs = select(
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
    ).subquery()
    total = db.scalar(select(func.count()).select_from(ChatSession)) or 0
    rows = db.execute(
        select(ChatSession, User, last_activity.c.at, ranked_runs)
        .join(User, User.user_id == ChatSession.user_id)
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
                    "owner": {"display_name": owner.display_name, "email": owner.email},
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
                for (
                    record, owner, activity, _, run_status, final_action, error_code, _
                ) in rows
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
    _: User = Depends(require_admin),
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
            "owner": {
                "display_name": db.get(User, record.user_id).display_name,
                "email": db.get(User, record.user_id).email,
            },
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
                    "adapter_mode": ticket.adapter_mode,
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


@app.get("/api/tickets", dependencies=[Depends(require_admin)])
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


@app.get("/api/tickets/{ticket_id}", dependencies=[Depends(require_admin)])
def get_ticket(
    ticket_id: str, request: Request, db: Session = Depends(get_session)
) -> dict:
    ticket = db.get(Ticket, identifier(ticket_id))
    if ticket is None:
        raise HTTPException(404, "TICKET_NOT_FOUND")
    return envelope(ticket_data(ticket), request)


@app.get("/api/admin/tickets/{ticket_id}")
def get_admin_ticket(
    ticket_id: str,
    request: Request,
    db: Session = Depends(get_session),
    _: User = Depends(require_admin),
) -> dict:
    ticket = db.get(Ticket, identifier(ticket_id))
    if ticket is None:
        raise HTTPException(404, "TICKET_NOT_FOUND")
    return envelope(ticket_data(ticket, include_payload=True), request)


@app.get("/api/agent-runs/{agent_run_id}", dependencies=[Depends(require_admin)])
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


@app.get("/api/metrics/summary", dependencies=[Depends(require_admin)])
def metrics(request: Request, db: Session = Depends(get_session)) -> dict:
    def count(statement):
        return db.scalar(statement) or 0

    return envelope(
        {
            "total_conversations": count(select(func.count()).select_from(ChatSession)),
            "tickets_created": count(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.status == "created", Ticket.adapter_mode != "mock")
            ),
            "tickets_simulated": count(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.status == "created", Ticket.adapter_mode == "mock")
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


@app.get("/api/knowledge/sources", dependencies=[Depends(require_admin)])
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


from app.ia_tab import router as ia_router  # noqa: E402

app.include_router(ia_router, dependencies=[Depends(require_admin)])
