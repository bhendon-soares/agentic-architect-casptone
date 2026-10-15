"""HTTP contracts on an isolated relational database."""

import importlib.util
import json
import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.adapters.tickets import TicketOutcomeUnknown, TicketRejected
from app.main import app, local_admin
from app.persistence.database import get_session
from app.persistence.models import AgentRun, Base, ChatMessage, ChatSession
from app.runtime.crew import InvalidAgentOutput
from app.runtime.policy import CATEGORIES, priority

CASES_PATH = (
    Path(__file__).resolve().parents[3]
    / "project-context/1.define/support-cases.json"
)
SUPPORT_CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from pathlib import Path

    monkeypatch.setenv(
        "KNOWLEDGE_BASE_PATH", str(Path(__file__).resolve().parents[3] / "knowledge")
    )
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def test_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_session_and_admin_reads(client: TestClient) -> None:
    created = client.post("/api/chat/sessions", json={})
    assert created.status_code == 201
    session_id = created.json()["data"]["session_id"]
    assert created.json()["meta"]["request_id"]
    history = client.get(f"/api/chat/sessions/{session_id}")
    assert history.json()["data"]["messages"] == []
    assert history.json()["data"]["turns"] == []
    assert client.get("/api/tickets").json()["data"] == {"items": [], "total": 0}
    sources = client.get("/api/knowledge/sources").json()["data"]["items"]
    assert len(sources) == 7
    assert all(source["approved"] for source in sources)
    assert client.get("/api/metrics/summary").json()["data"]["total_conversations"] == 1


def test_missing_ticket_data_after_clarification(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def workflow(message, clarification_count, db, agent_run_id):
        assert clarification_count == 1
        raise InvalidAgentOutput("Minimum ticket data missing")

    monkeypatch.setattr("app.main.run_workflow", workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    db = next(app.dependency_overrides[get_session]())
    db.get(ChatSession, session_id).clarification_count = 1
    db.commit()
    url = f"/api/chat/sessions/{session_id}/messages"
    body = {"message_text": "Nao sei explicar"}
    headers = {"Idempotency-Key": "missing-data"}
    response = client.post(url, json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MINIMUM_TICKET_DATA_MISSING"
    assert response.json()["error"]["retryable"] is False
    assert client.post(url, json=body, headers=headers).status_code == 422
    run_id = response.json()["meta"]["agent_run_id"]
    history = client.get(f"/api/chat/sessions/{session_id}").json()["data"]
    assert history["turns"] == []
    assert history["messages"][0]["agent_run_id"] == run_id
    assert history["outcomes"] == [{
        "agent_run_id": run_id,
        "code": "MINIMUM_TICKET_DATA_MISSING",
        "message_pt_br": response.json()["error"]["message"],
    }]
    assert client.get(f"/api/agent-runs/{run_id}").json()["data"]["final_action"] is None
    assert client.get("/api/tickets").json()["data"]["total"] == 0


def test_admin_conversations_order_pagination_and_detail(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_session]())
    start = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    ids = [f"{index:08d}-0000-4000-8000-000000000000" for index in range(1, 5)]
    for session_id in ids:
        db.add(ChatSession(session_id=session_id, created_at=start, updated_at=start))
    db.flush()
    db.add(
        ChatMessage(
            session_id=ids[0], role="user", message_pt_br="senha=sentinel-123",
            created_at=start + timedelta(minutes=3),
        )
    )
    failed_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    completed_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    db.add(
        AgentRun(
            agent_run_id=completed_id, session_id=ids[0], status="completed",
            final_action="blocked", started_at=start + timedelta(minutes=1),
            response_data={"summary": "Pedido bloqueado.", "sources": []},
        )
    )
    db.add(
        AgentRun(
            agent_run_id=failed_id, session_id=ids[0], status="failed",
            started_at=start + timedelta(minutes=4), error_code="RUNTIME_UNAVAILABLE",
        )
    )
    db.add(
        AgentRun(
            session_id=ids[1], status="completed", final_action="respond",
            started_at=start + timedelta(minutes=2),
            response_data={
                "summary": "Resumo senha=sentinel-123",
                "sources": [{
                    "title": "Manual", "path": "knowledge/unknown.md",
                    "snippet": "token=sentinel-123", "private": "do not return",
                }],
                "private": "do not return",
            },
        )
    )
    db.add(
        ChatMessage(
            session_id=ids[2], role="user", message_pt_br="Outra conversa",
            created_at=start + timedelta(minutes=2),
        )
    )
    db.commit()
    db.close()

    first = client.get("/api/admin/conversations?limit=2&offset=0").json()
    assert first["error"] is None
    assert first["meta"]["limit"] == 2
    assert first["data"]["total"] == 4
    assert [item["session_id"] for item in first["data"]["items"]] == ids[:2]
    assert first["data"]["items"][0]["last_run"] == {
        "final_action": None,
        "run_status": "failed",
        "error_code": "RUNTIME_UNAVAILABLE",
    }
    assert first["data"]["items"][0]["last_activity_at"] == "2026-10-15T12:04:00+00:00"
    assert [item["session_id"] for item in client.get(
        "/api/admin/conversations?limit=2&offset=2"
    ).json()["data"]["items"]] == ids[2:]
    assert client.get("/api/admin/conversations?offset=10").json()["data"] == {
        "items": [], "total": 4
    }
    detail = client.get(f"/api/admin/conversations/{ids[0]}").json()["data"]
    assert [run["agent_run_id"] for run in detail["runs"]] == [completed_id, failed_id]
    assert detail["runs"][1]["sources"] == []
    assert detail["runs"][1]["summary"] is None
    assert detail["tickets"] == []
    assert client.get(f"/api/chat/sessions/{ids[0]}").json()["data"]["turns"] == [
        {"summary": "Pedido bloqueado.", "sources": []}
    ]
    sourced = client.get(f"/api/admin/conversations/{ids[1]}").json()
    assert "sentinel-123" not in json.dumps(sourced)
    assert "private" not in json.dumps(sourced)


def test_admin_local_and_invalid_requests(client: TestClient) -> None:
    for path, code in (
        ("/api/admin/conversations?limit=0", "INVALID_REQUEST"),
        ("/api/admin/conversations?limit=101", "INVALID_REQUEST"),
        ("/api/admin/conversations?offset=-1", "INVALID_REQUEST"),
        ("/api/admin/conversations/not-uuid", "INVALID_ID"),
        (
            "/api/admin/conversations/00000000-0000-4000-8000-000000000000",
            "SESSION_NOT_FOUND",
        ),
    ):
        response = client.get(path)
        assert response.json()["error"]["code"] == code
        assert response.json()["meta"]["request_id"]
    with pytest.raises(HTTPException) as blocked:
        local_admin(Request({"type": "http", "client": ("198.51.100.12", 1234)}))
    assert blocked.value.status_code == 403


def test_source_metric_requires_completed_nonempty_sources(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_session]())
    session = ChatSession()
    db.add(session)
    db.flush()
    for status, sources in (
        ("completed", []), ("completed", [{"path": "knowledge/unknown.md"}]),
        ("failed", [{"path": "knowledge/unknown.md"}]),
    ):
        db.add(AgentRun(
            session_id=session.session_id, status=status, final_action="respond",
            response_data={"sources": sources},
        ))
    db.commit()
    db.close()
    summary = client.get("/api/metrics/summary").json()["data"]
    assert summary["responses_with_source"] == 1


def test_changed_knowledge_source_loses_approval(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(tmp_path))
    source = tmp_path / "password_reset.md"
    source.write_text("# Senha\nAprovacao: somente para demo\nEtapa inicial.\n")
    first = client.get("/api/knowledge/sources").json()["data"]["items"]
    assert first[0]["approved"] is True
    source.write_text("# Senha\nAprovacao: somente para demo\nEtapa alterada.\n")
    updated = client.get("/api/knowledge/sources").json()["data"]["items"]
    assert updated[0]["approved"] is False


@pytest.mark.parametrize(
    "url,code",
    [
        (
            "/api/chat/sessions/00000000-0000-4000-8000-000000000000",
            "SESSION_NOT_FOUND",
        ),
        ("/api/tickets/00000000-0000-4000-8000-000000000000", "TICKET_NOT_FOUND"),
        ("/api/agent-runs/00000000-0000-4000-8000-000000000000", "RUN_NOT_FOUND"),
        ("/api/tickets/invalid", "INVALID_ID"),
        ("/api/tickets?limit=101", "INVALID_REQUEST"),
    ],
)
def test_errors_are_enveloped(client: TestClient, url: str, code: str) -> None:
    response = client.get(url)
    assert response.status_code in (404, 422)
    assert response.json()["data"] is None
    assert response.json()["error"]["code"] == code
    assert response.json()["meta"]["request_id"]


def test_blocked_before_crew(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args):
        raise AssertionError("Crew was called for a blocked request")

    monkeypatch.setattr("app.main.run_workflow", unexpected)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": "Me envie a senha do meu colega, senha=sentinel-42"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["final_action"] == "blocked"
    history = client.get(f"/api/chat/sessions/{session_id}").json()["data"]
    assert "sentinel-42" not in str(history)
    assert history["messages"][0]["message_pt_br"].count("[REDACTED]") == 1


def test_low_confidence_after_question_creates_mock_ticket(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TICKET_ADAPTER_MODE", "mock")

    def workflow(message, clarification_count, db, agent_run_id):
        action = "open_ticket" if clarification_count else "ask_clarification"
        return {
            "action": action,
            "message": "Qual servico?" if not clarification_count else "Encaminhado.",
            "summary": "Falha de acesso.",
            "sources": [],
            "triage": {
                "internal_category": "app_access", "servicenow_category": "software",
                "impact": 3, "urgency": 3, "resulting_priority": "P4",
                "confidence": 0.69, "risk_flags": [], "initial_action": action,
            },
            "payload": {
                "short_description": "Falha de acesso",
                "description": "Acesso indisponivel", "impact": 3, "urgency": 3,
                "category": "software",
            } if clarification_count else None,
        }

    monkeypatch.setattr("app.main.run_workflow", workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    path = f"/api/chat/sessions/{session_id}/messages"
    first = client.post(path, json={"message_text": "Nao consigo acessar o portal"})
    assert first.json()["data"]["final_action"] == "ask_clarification"
    second = client.post(path, json={"message_text": "Portal interno indisponivel"})
    assert second.status_code == 200
    assert second.json()["data"]["final_action"] == "open_ticket"
    assert second.json()["data"]["ticket"]["status"] == "created"


def test_dataset_tc012_blocks_before_crew(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tc012 = next(case for case in SUPPORT_CASES if case["id"] == "TC012")

    def unexpected(*args):
        raise AssertionError("Crew was called for TC012")

    monkeypatch.setattr("app.main.run_workflow", unexpected)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": tc012["input"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["final_action"] == tc012["expected_action"]
    assert client.get("/api/tickets").json()["data"]["total"] == 0


@pytest.mark.parametrize(
    "case", [case for case in SUPPORT_CASES if case["id"] != "TC012"],
    ids=lambda case: case["id"],
)
def test_dataset_deterministic_http_contract(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, case: dict
) -> None:
    from app.adapters.tickets import Incident

    category = case["expected_category"]
    action = case["expected_action"]
    impact = case.get("expected_impact", 3)
    urgency = case.get("expected_urgency", 3)
    source_path = f"knowledge/{case['expected_source']}"
    sources = (
        [{"title": "Fonte aprovada", "path": source_path, "snippet": "Passo local"}]
        if action == "respond"
        else []
    )
    triage = {
        "internal_category": category,
        "servicenow_category": CATEGORIES[category],
        "impact": impact,
        "urgency": urgency,
        "resulting_priority": priority(category, impact, urgency),
        "confidence": 0.9,
        "initial_action": action,
    }
    payload = {
        "short_description": "Incidente sintetico",
        "description": "Validacao manual sem dados pessoais",
        "impact": impact,
        "urgency": urgency,
        "category": CATEGORIES[category],
    }
    monkeypatch.setattr(
        "app.main.run_workflow",
        lambda *args: {
            "action": action,
            "message": "Orientacao de suporte",
            "summary": "Triagem concluida",
            "sources": sources,
            "triage": triage,
            "payload": payload if action == "open_ticket" else None,
        },
    )
    monkeypatch.setattr(
        "app.main.create_incident",
        lambda *args: Incident("sys-synthetic", "INC-SYNTHETIC"),
    )
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": case["input"]},
    )
    assert response.status_code == 200
    turn = response.json()["data"]
    assert turn["final_action"] == action
    assert turn["triage"]["internal_category"] == category
    assert turn["triage"]["resulting_priority"] == priority(category, impact, urgency)
    assert [source["path"] for source in turn["sources"]] == (
        [source_path] if action == "respond" else []
    )
    assert (turn["ticket"] is not None) == (action == "open_ticket")
    if action == "open_ticket":
        ticket_id = turn["ticket"]["ticket_id"]
        ticket = client.get(f"/api/tickets/{ticket_id}").json()["data"]
        assert ticket["internal_category"] == category
        assert ticket["status"] == "created"
        assert ticket["servicenow_number"] == "INC-SYNTHETIC"
    history = client.get(f"/api/chat/sessions/{session_id}").json()["data"]
    assert history["turns"][0] == turn
    assert history["clarification_count"] == (action == "ask_clarification")


def test_response_replay_and_clarification(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def workflow(
        message: str, clarification_count: int, db: Session, agent_run_id: str
    ) -> dict:
        calls.append((message, clarification_count))
        if clarification_count == 0:
            return {
                "action": "ask_clarification",
                "message": "Qual servico?",
                "summary": "Aguardando detalhes.",
                "sources": [],
                "triage": None,
                "payload": None,
            }
        return {
            "action": "respond",
            "message": "Consulte o procedimento.",
            "summary": "Fonte consultada.",
            "sources": [
                {
                    "title": "Fonte",
                    "path": "knowledge/password_reset.md",
                    "snippet": "Procedimento",
                }
            ],
            "triage": None,
            "payload": None,
        }

    monkeypatch.setattr("app.main.run_workflow", workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    url = f"/api/chat/sessions/{session_id}/messages"
    first = client.post(
        url,
        json={"message_text": "Preciso de ajuda"},
        headers={"Idempotency-Key": "first"},
    )
    assert first.json()["data"]["final_action"] == "ask_clarification"
    assert (
        client.post(
            url,
            json={"message_text": "Preciso de ajuda"},
            headers={"Idempotency-Key": "first"},
        ).json()["data"]
        == first.json()["data"]
    )
    assert (
        client.post(
            url,
            json={"message_text": "Outra mensagem"},
            headers={"Idempotency-Key": "first"},
        ).status_code
        == 409
    )
    second = client.post(url, json={"message_text": "Senha corporativa"})
    assert second.json()["data"]["final_action"] == "respond"
    assert calls == [
        ("Preciso de ajuda", 0),
        (
            "Relato inicial: Preciso de ajuda\n"
            "Pergunta de esclarecimento: Qual servico?\n"
            "Resposta do usuario: Senha corporativa",
            1,
        ),
    ]
    history = client.get(f"/api/chat/sessions/{session_id}").json()["data"]
    assert history["messages"][-2]["message_pt_br"] == "Senha corporativa"
    assert (
        history["clarification_count"]
        == 1
    )
    assert (
        client.get("/api/metrics/summary").json()["data"]["responses_with_source"] == 1
    )


@pytest.mark.parametrize(
    "exception,status,expected",
    [
        (TicketRejected, 502, "failed"),
        (TicketOutcomeUnknown, 504, "outcome_unknown"),
    ],
)
def test_ticket_failure_never_reposts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    exception: type[Exception],
    status: int,
    expected: str,
) -> None:
    def workflow(*args):
        return {
            "action": "open_ticket",
            "message": "Abrindo incidente.",
            "summary": "Suporte manual.",
            "sources": [],
            "triage": {
                "internal_category": "password_reset",
                "servicenow_category": "inquiry",
                "impact": 3,
                "urgency": 2,
                "resulting_priority": "P3",
                "confidence": 0.9,
                "initial_action": "open_ticket",
            },
            "payload": {
                "short_description": "Teste",
                "description": "Teste",
                "impact": 3,
                "urgency": 2,
                "category": "inquiry",
            },
        }

    calls = []

    def adapter(payload, agent_run_id, mode):
        tickets = client.get("/api/tickets").json()["data"]["items"]
        run = client.get(f"/api/agent-runs/{agent_run_id}").json()["data"]
        assert tickets[0]["status"] == "pending"
        assert run["final_action"] == "open_ticket"
        calls.append(agent_run_id)
        raise exception()

    monkeypatch.setattr("app.main.run_workflow", workflow)
    monkeypatch.setattr("app.main.create_incident", adapter)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    url = f"/api/chat/sessions/{session_id}/messages"
    headers = {"Idempotency-Key": "ticket-turn"}
    response = client.post(
        url, json={"message_text": "Nao consigo verificar minha senha"}, headers=headers
    )
    assert response.status_code == status
    assert response.json()["error"]["retryable"] is False
    repeat = client.post(
        url, json={"message_text": "Nao consigo verificar minha senha"}, headers=headers
    )
    assert repeat.status_code == status
    assert len(calls) == 1
    assert client.get("/api/tickets").json()["data"]["items"][0]["status"] == expected
    assert client.get(f"/api/chat/sessions/{session_id}").json()["data"]["turns"] == []
    detail = client.get(f"/api/admin/conversations/{session_id}").json()["data"]
    assert detail["runs"][0]["agent_run_id"] == calls[0]
    assert detail["runs"][0]["status"] == expected
    assert detail["tickets"][0]["agent_run_id"] == calls[0]
    assert detail["tickets"][0]["status"] == expected


def test_ticket_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.adapters.tickets import Incident

    monkeypatch.setattr(
        "app.main.run_workflow",
        lambda *args: {
            "action": "open_ticket",
            "message": "Abrindo incidente.",
            "summary": "Atendimento manual.",
            "sources": [],
            "triage": {
                "internal_category": "password_reset",
                "servicenow_category": "inquiry",
                "impact": 3,
                "urgency": 2,
                "resulting_priority": "P3",
                "confidence": 0.9,
                "initial_action": "open_ticket",
            },
            "payload": {
                "short_description": "Teste",
                "description": "Teste",
                "impact": 3,
                "urgency": 2,
                "category": "inquiry",
            },
        },
    )
    monkeypatch.setattr(
        "app.main.create_incident", lambda *args: Incident("sys-1", "INC0001")
    )
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": "Nao consigo verificar minha senha"},
    )
    assert response.status_code == 200
    ticket = response.json()["data"]["ticket"]
    assert ticket["servicenow_number"] == "INC0001"
    assert (
        client.get(f"/api/tickets/{ticket['ticket_id']}").json()["data"]["status"]
        == "created"
    )
    assert client.get("/api/metrics/summary").json()["data"]["tickets_created"] == 1


def test_workflow_output_is_redacted_before_ticket_and_persistence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.adapters.tickets import Incident

    secret = "sentinel-ticket-42"
    monkeypatch.setattr(
        "app.main.run_workflow",
        lambda *args: {
            "action": "open_ticket",
            "message": f"Abertura com senha={secret}",
            "summary": f"Resumo com senha={secret}",
            "sources": [
                {
                    "title": f"Titulo senha={secret}",
                    "path": "knowledge/password_reset.md",
                    "snippet": f"Instrucao senha={secret}",
                }
            ],
            "triage": {
                "internal_category": "password_reset",
                "servicenow_category": "inquiry",
                "impact": 3,
                "urgency": 2,
                "resulting_priority": "P3",
                "confidence": 0.9,
                "initial_action": "open_ticket",
            },
            "payload": {
                "short_description": f"Senha={secret}",
                "description": f"Senha={secret}",
                "impact": 3,
                "urgency": 2,
                "category": "inquiry",
            },
        },
    )

    def adapter(payload, agent_run_id, mode):
        assert secret not in str(payload)
        return Incident("sys-1", "INC0001")

    monkeypatch.setattr("app.main.create_incident", adapter)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": "Preciso de ajuda"},
    )
    assert response.status_code == 200
    assert secret not in str(response.json())
    assert secret not in str(client.get(f"/api/chat/sessions/{session_id}").json())
    assert secret not in str(client.get("/api/tickets").json())


def test_malformed_workflow_output_is_safe_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.main.run_workflow", lambda *args: {"action": "respond"})
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": "Preciso de ajuda"},
    )
    assert response.status_code == 502


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("Clarification limit reached", "CLARIFICATION_LIMIT_REACHED"),
        ("Unapproved response", "POLICY_UNAPPROVED"),
        ("private provider details", "WORKFLOW_FAILED"),
    ],
)
def test_workflow_failure_records_only_known_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, reason: str, expected: str
) -> None:
    def invalid_workflow(*args):
        raise InvalidAgentOutput(reason)

    monkeypatch.setattr("app.main.run_workflow", invalid_workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": "Preciso de ajuda"},
    )
    assert response.status_code == 502
    run_id = response.json()["meta"]["agent_run_id"]
    events = client.get(f"/api/agent-runs/{run_id}").json()["data"]["events"]
    assert events[-1]["validation_errors"] == [{"code": expected}]
    assert reason not in str(events)
    assert response.json()["error"]["code"] == "AGENT_OUTPUT_INVALID"


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="requires local PostgreSQL"
)
def test_postgres_revision_is_reversible() -> None:
    from pathlib import Path

    from dotenv import load_dotenv
    from sqlalchemy import inspect

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    schema = f"test_backend_{uuid4().hex}"
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20261013_01_initial.py"
    )
    spec = importlib.util.spec_from_file_location("initial_revision", revision_path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        with engine.begin() as connection:
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            original = revision.op
            revision.op = Operations(MigrationContext.configure(connection))
            try:
                revision.upgrade()
                assert len(inspect(connection).get_table_names(schema=schema)) == 6
                revision.downgrade()
                assert inspect(connection).get_table_names(schema=schema) == []
            finally:
                revision.op = original
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()
