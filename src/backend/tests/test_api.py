"""HTTP contracts on an isolated relational database."""

import importlib.util
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.adapters.tickets import TicketOutcomeUnknown, TicketRejected
from app.main import app
from app.persistence.database import get_session
from app.persistence.models import Base
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
