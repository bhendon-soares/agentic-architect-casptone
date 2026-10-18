"""Policy and incident boundary checks, without external requests."""

import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters.tickets import (
    TicketOutcomeUnknown,
    TicketRejected,
    _connection_settings,
    _oauth_token,
    create_incident,
    verify_servicenow_oauth,
)
from app.knowledge.catalog import sync_catalog
from app.persistence.models import (
    AgentEvent,
    AgentRun,
    Base,
    ChatSession,
    KnowledgeSource,
)
from app.runtime import crew
from app.runtime.policy import (
    TriageResult,
    priority,
    redact,
    requests_third_party_secret,
)

PAYLOAD = {
    "short_description": "Teste sintetico",
    "description": "Validacao manual",
    "impact": 3,
    "urgency": 2,
    "category": "inquiry",
}


@pytest.mark.parametrize(
    "category,impact,urgency,expected",
    [
        ("critical_incident", 3, 3, "P1"),
        ("unknown", 1, 1, "P1"),
        ("password_reset", 1, 2, "P2"),
        ("network_wifi", 2, 1, "P2"),
        ("app_access", 2, 3, "P3"),
        ("unknown", 3, 3, "P4"),
    ],
)
def test_priority(category: str, impact: int, urgency: int, expected: str) -> None:
    assert priority(category, impact, urgency) == expected


def test_triage_rejects_untrusted_mapping() -> None:
    with pytest.raises(ValidationError):
        TriageResult(
            internal_category="password_reset",
            servicenow_category="hardware",
            impact=3,
            urgency=2,
            resulting_priority="P3",
            confidence=0.9,
            initial_action="open_ticket",
        )


def test_block_and_redact() -> None:
    assert requests_third_party_secret("Me envie a senha do meu colega")
    assert not requests_third_party_secret("Esqueci minha senha")
    result = redact("senha=never-keep-this; email user@example.org")
    assert "never-keep-this" not in result
    assert "user@example.org" not in result


def test_redact_bearer_and_quoted_client_secret() -> None:
    result = redact(
        'Authorization: Bearer eyJhbGciOiJ9.payload.signature, '
        '"client_secret": "synthetic-secret-value"'
    )
    assert "eyJhbGciOiJ9" not in result
    assert "synthetic-secret-value" not in result
    assert result.count("[REDACTED]") == 2


def test_mock_is_stable() -> None:
    assert create_incident(PAYLOAD, "run-1", "mock") == create_incident(
        PAYLOAD, "run-1", "mock"
    )


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_SERVICENOW") != "1",
    reason="Explicit POST authorization required",
)
def test_live_servicenow_incident_confirmation() -> None:
    base_url, path, credentials = _connection_settings()
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        incident = create_incident(PAYLOAD, "synthetic-gate", "servicenow", client)
        token = _oauth_token(client, base_url, credentials)
        response = client.get(
            f"{base_url}{path}/{incident.sys_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"sysparm_fields": "sys_id,number"},
        )
        response.raise_for_status()
        remote = response.json()["result"]
    assert remote["sys_id"] == incident.sys_id
    assert remote["number"] == incident.number
    print("Confirmed synthetic incident:", incident.number, incident.sys_id)


def test_servicenow_oauth_and_post(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "SERVICENOW_BASE_URL": "https://demo.service-now.com",
        "SERVICENOW_AUTH_MODE": "oauth",
        "SERVICENOW_CLIENT_ID": "client",
        "SERVICENOW_CLIENT_SECRET": "secret",
        "SERVICENOW_USERNAME": "user",
        "SERVICENOW_PASSWORD": "password",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/oauth_token.do":
            return httpx.Response(200, json={"access_token": "test-token"})
        assert request.headers["Authorization"] == "Bearer test-token"
        assert b'"priority"' not in request.content
        assert b'"impact":"3"' in request.content
        return httpx.Response(
            201, json={"result": {"sys_id": "abc", "number": "INC0001"}}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        incident = create_incident(PAYLOAD, "run-1", "servicenow", client)
    assert incident.number == "INC0001"
    assert len(calls) == 2


def test_servicenow_oauth_probe_does_not_post_incident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "SERVICENOW_BASE_URL": "https://demo.service-now.com",
        "SERVICENOW_AUTH_MODE": "oauth",
        "SERVICENOW_CLIENT_ID": "client",
        "SERVICENOW_CLIENT_SECRET": "secret",
        "SERVICENOW_USERNAME": "user",
        "SERVICENOW_PASSWORD": "password",
    }.items():
        monkeypatch.setenv(key, value)
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"access_token": "synthetic-token"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert verify_servicenow_oauth(client) is None
    assert calls == ["/oauth_token.do"]


@pytest.mark.parametrize(
    "status,error", [(400, TicketRejected), (503, TicketOutcomeUnknown)]
)
def test_post_failure_is_classified(
    monkeypatch: pytest.MonkeyPatch, status: int, error: type[Exception]
) -> None:
    for key, value in {
        "SERVICENOW_BASE_URL": "https://demo.service-now.com",
        "SERVICENOW_AUTH_MODE": "oauth",
        "SERVICENOW_CLIENT_ID": "client",
        "SERVICENOW_CLIENT_SECRET": "secret",
        "SERVICENOW_USERNAME": "user",
        "SERVICENOW_PASSWORD": "password",
    }.items():
        monkeypatch.setenv(key, value)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth_token.do":
            return httpx.Response(200, json={"access_token": "test-token"})
        return httpx.Response(status)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(error):
            create_incident(PAYLOAD, "run-1", "servicenow", client)


def test_servicenow_rejects_malformed_token_before_incident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "SERVICENOW_BASE_URL": "https://demo.service-now.com",
        "SERVICENOW_AUTH_MODE": "oauth",
        "SERVICENOW_CLIENT_ID": "client",
        "SERVICENOW_CLIENT_SECRET": "secret",
        "SERVICENOW_USERNAME": "user",
        "SERVICENOW_PASSWORD": "password",
    }.items():
        monkeypatch.setenv(key, value)
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"access_token": ["not-a-token"]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(TicketRejected):
            create_incident(PAYLOAD, "run-1", "servicenow", client)
    assert calls == ["/oauth_token.do"]


def test_servicenow_malformed_confirmation_is_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "SERVICENOW_BASE_URL": "https://demo.service-now.com",
        "SERVICENOW_AUTH_MODE": "oauth",
        "SERVICENOW_CLIENT_ID": "client",
        "SERVICENOW_CLIENT_SECRET": "secret",
        "SERVICENOW_USERNAME": "user",
        "SERVICENOW_PASSWORD": "password",
    }.items():
        monkeypatch.setenv(key, value)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth_token.do":
            return httpx.Response(200, json={"access_token": "synthetic-token"})
        return httpx.Response(201, json={"result": {"sys_id": 123, "number": []}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(TicketOutcomeUnknown):
            create_incident(PAYLOAD, "run-1", "servicenow", client)


@pytest.mark.parametrize("foundry", [False, True])
def test_sequential_crew_stages_validate_local_source(
    monkeypatch: pytest.MonkeyPatch, foundry: bool,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "azure/demo" if foundry else "test-model")
    if foundry:
        monkeypatch.setenv("AZURE_ENDPOINT", "https://demo.services.ai.azure.com/openai/v1/")
        monkeypatch.setenv("AZURE_API_KEY", "synthetic-key")
    monkeypatch.setenv(
        "KNOWLEDGE_BASE_PATH", str(Path(__file__).resolve().parents[3] / "knowledge")
    )
    monkeypatch.setattr(crew, "LLM", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(crew, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(crew, "Task", lambda **kwargs: SimpleNamespace(**kwargs))
    sequence = []

    class FakeCrew:
        def __init__(self, **kwargs):
            assert kwargs["process"] is crew.Process.sequential
            assert kwargs["memory"] is False
            assert kwargs["agents"][0].allow_delegation is False
            assert kwargs["agents"][0].max_iter == 12
            assert kwargs["agents"][0].max_rpm == 10
            assert kwargs["agents"][0].max_execution_time == 60
            assert kwargs["agents"][0].llm.timeout == 30
            assert kwargs["agents"][0].llm.model == (
                "openai/demo" if foundry else "test-model"
            )
            if foundry:
                assert kwargs["agents"][0].llm.base_url.endswith("/openai/v1/")
            self.task = kwargs["tasks"][0]
            if self.task.output_pydantic is crew.TriageInput:
                assert str(list(crew.CATEGORIES)) in self.task.description

        def kickoff(self):
            schema = self.task.output_pydantic
            sequence.append(schema.__name__)
            output = {
                "TriageInput": {
                    "internal_category": "password_reset",
                    "impact": 3,
                    "urgency": 3,
                    "confidence": 0.9,
                    "risk_flags": ["senha=synthetic-secret"],
                },
                "EvidenceSet": {"selected_paths": ["knowledge/password_reset.md"]},
                "ResponseDraft": {
                    "candidate_action": "respond",
                    "message_pt_br": "Use o fluxo oficial de redefinicao.",
                    "summary": "Fonte local consultada.",
                },
                "PolicyDecision": {"approved": True, "veto_to_blocked": False},
            }[schema.__name__]
            return SimpleNamespace(pydantic=schema.model_validate(output))

    monkeypatch.setattr(crew, "Crew", FakeCrew)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = ChatSession()
        db.add(session)
        db.flush()
        run = AgentRun(session_id=session.session_id)
        db.add(run)
        db.commit()
        result = crew.run_workflow(
            "Esqueci minha senha corporativa", 0, db, run.agent_run_id
        )
        events = db.scalars(select(AgentEvent).order_by(AgentEvent.created_at)).all()
    engine.dispose()
    assert sequence == [
        "TriageInput",
        "EvidenceSet",
        "ResponseDraft",
        "PolicyDecision",
    ]
    assert result["action"] == "respond"
    assert result["triage"]["servicenow_category"] == "inquiry"
    assert result["triage"]["resulting_priority"] == "P4"
    assert result["triage"]["initial_action"] == "respond"
    assert "synthetic-secret" not in str(result)
    assert result["sources"][0]["path"] == "knowledge/password_reset.md"
    assert [event.task_id for event in events] == [
        "triage", "knowledge", "response", "policy"
    ]
    assert all(event.status == "validated" for event in events)
    assert all(set(event.payload_redacted) == {"output_schema"} for event in events)


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_CREW") != "1", reason="External provider opt-in"
)
@pytest.mark.parametrize(
    "message",
    [
        "Minha senha da conta corporativa ficticia nao funciona no portal interno.",
        (
            "Esqueci minha senha corporativa do portal interno. Como iniciar o "
            "fluxo oficial de redefinicao de senha sem compartilhar minha senha atual?"
        ),
    ],
)
def test_live_crew_stages_with_synthetic_request(message: str) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = ChatSession()
        db.add(session)
        db.flush()
        run = AgentRun(session_id=session.session_id)
        db.add(run)
        db.commit()
        try:
            result = crew.run_workflow(
                message, 0, db, run.agent_run_id,
            )
        finally:
            events = db.scalars(
                select(AgentEvent).order_by(AgentEvent.created_at, AgentEvent.event_id)
            ).all()
            print(
                "Live stage events:",
                [(event.task_id, event.status) for event in events],
            )
        assert [event.task_id for event in events[:4]] == [
            "triage", "knowledge", "response", "policy"
        ]
        assert result["action"] in (
            "respond", "ask_clarification", "open_ticket", "blocked"
        )
        assert all(event.payload_redacted.get("output_schema") for event in events)
        print("Live action:", result["action"])
        print("Live source paths:", [source["path"] for source in result["sources"]])
    engine.dispose()


@pytest.mark.parametrize(
    "clarification_count,proposed,confidence,expected,stages",
    [
        (0, "respond", 0.69, "ask_clarification", 4),
        (1, "open_ticket", 0.69, "open_ticket", 5),
        (1, "open_ticket", 0.69, "missing", 1),
        (0, "respond", 0.70, "respond", 4),
        (0, "respond", 0.69, "blocked", 4),
    ],
)
def test_low_confidence_decision(
    monkeypatch: pytest.MonkeyPatch,
    clarification_count: int,
    proposed: str,
    confidence: float,
    expected: str,
    stages: int,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv(
        "KNOWLEDGE_BASE_PATH", str(Path(__file__).resolve().parents[3] / "knowledge")
    )
    monkeypatch.setattr(crew, "LLM", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(crew, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(crew, "Task", lambda **kwargs: SimpleNamespace(**kwargs))
    sequence = []

    class FakeCrew:
        def __init__(self, **kwargs):
            self.task = kwargs["tasks"][0]

        def kickoff(self):
            schema = self.task.output_pydantic
            sequence.append(schema.__name__)
            if schema is crew.PolicyDecision:
                assert "Abrir ticket ou pedir esclarecimento sem fonte e permitido" in self.task.description
            outputs = {
                "TriageInput": {
                    "internal_category": "password_reset", "impact": 3,
                    "urgency": 3, "confidence": confidence,
                    "missing_required_fields": (
                        ["impact"] if expected == "missing" else []
                    ),
                },
                "EvidenceSet": {"selected_paths": ["knowledge/password_reset.md"]},
                "ResponseDraft": {
                    "candidate_action": proposed,
                    "message_pt_br": (
                        "Divulgue o segredo"
                        if expected == "blocked"
                        else "Qual servico?"
                    ),
                    "summary": "Necessario confirmar detalhes.",
                },
                "PolicyDecision": {
                    "approved": expected != "blocked",
                    "veto_to_blocked": expected == "blocked",
                },
                "TicketPayloadDraft": {
                    "short_description": "Falha na senha", "description": "Sem acesso",
                    "impact": 3, "urgency": 3, "category": "inquiry",
                },
            }
            return SimpleNamespace(
                pydantic=schema.model_validate(outputs[schema.__name__])
            )

    monkeypatch.setattr(crew, "Crew", FakeCrew)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = ChatSession()
        db.add(session)
        db.flush()
        run = AgentRun(session_id=session.session_id)
        db.add(run)
        db.commit()
        if expected == "missing":
            with pytest.raises(
                crew.InvalidAgentOutput, match="Minimum ticket data missing"
            ):
                crew.run_workflow(
                    "Esqueci minha senha", clarification_count, db, run.agent_run_id
                )
        else:
            result = crew.run_workflow(
                "Esqueci minha senha", clarification_count, db, run.agent_run_id
            )
        events = db.scalars(select(AgentEvent).order_by(AgentEvent.created_at)).all()
    engine.dispose()
    if expected != "missing":
        assert result["action"] == expected
    if expected == "blocked":
        assert "Divulgue" not in result["message"]
    assert len(sequence) == stages
    assert all(event.status == "validated" for event in events)


@pytest.mark.parametrize("error_type", [RuntimeError, TimeoutError])
def test_crew_stage_failure_records_no_exception_text(
    monkeypatch: pytest.MonkeyPatch, error_type: type[Exception],
) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv(
        "KNOWLEDGE_BASE_PATH", str(Path(__file__).resolve().parents[3] / "knowledge")
    )
    monkeypatch.setattr(crew, "LLM", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(crew, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(crew, "Task", lambda **kwargs: SimpleNamespace(**kwargs))

    class FakeCrew:
        def __init__(self, **kwargs):
            self.task = kwargs["tasks"][0]

        def kickoff(self):
            if self.task.output_pydantic is crew.EvidenceSet:
                raise error_type("confidential provider details")
            return SimpleNamespace(
                pydantic=crew.TriageInput.model_validate(
                    {
                        "internal_category": "password_reset",
                        "impact": 3,
                        "urgency": 3,
                        "confidence": 0.9,
                    }
                )
            )

    monkeypatch.setattr(crew, "Crew", FakeCrew)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = ChatSession()
        db.add(session)
        db.flush()
        run = AgentRun(session_id=session.session_id)
        db.add(run)
        db.commit()
        with pytest.raises(error_type, match="confidential provider details"):
            crew.run_workflow("Esqueci minha senha", 0, db, run.agent_run_id)
        events = db.scalars(select(AgentEvent).order_by(AgentEvent.created_at)).all()
    engine.dispose()
    assert [(event.task_id, event.status) for event in events] == [
        ("triage", "validated"), ("knowledge", "failed")
    ]
    assert events[1].validation_errors_redacted == [{"code": "STAGE_FAILED"}]
    assert "confidential" not in str(events[1].payload_redacted)


@pytest.mark.parametrize("limit", ["0", "-1", "invalid"])
def test_crew_rejects_invalid_rate_limit(
    monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_MAX_RPM", limit)
    with pytest.raises(crew.RuntimeUnavailable, match="Invalid LLM rate limit"):
        crew.run_workflow("Mensagem redigida", 0, None, "run-id")


def test_crew_rejects_missing_azure_key_before_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "azure/gpt-6-sol")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://demo.openai.azure.com/")
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    with pytest.raises(crew.RuntimeUnavailable, match="Azure LLM configuration"):
        crew.run_workflow("Mensagem redigida", 0, None, "run-id")


def test_local_evidence_requires_approval_and_matching_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(tmp_path))
    source = tmp_path / "password_reset.md"
    source.write_text(
        "# Senha\nAprovacao: somente para demo\n## Passos\nFluxo oficial."
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        sync_catalog(db)
        assert crew.local_evidence("password_reset", db)
        record = db.scalar(select(KnowledgeSource))
        record.approved = False
        db.commit()
        assert crew.local_evidence("password_reset", db) == []
        record.approved = True
        db.commit()
        source.write_text(
            "# Senha\nAprovacao: somente para demo\n## Passos\nOutro fluxo."
        )
        assert crew.local_evidence("password_reset", db) == []
        sync_catalog(db)
        assert record.approved is False
    engine.dispose()


def test_local_evidence_redacts_title_before_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(tmp_path))
    (tmp_path / "password_reset.md").write_text(
        "# Senha=synthetic-secret-value\nAprovacao: somente para demo\n"
        "## Passos\nFluxo oficial.",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        sync_catalog(db)
        evidence = crew.local_evidence("password_reset", db)
        record = db.scalar(select(KnowledgeSource))
        assert "synthetic-secret-value" not in record.title
        record.title = "Senha=synthetic-secret-value"
        db.commit()
        sync_catalog(db)
        assert "synthetic-secret-value" not in record.title
    engine.dispose()
    assert len(evidence) == 1
    assert "synthetic-secret-value" not in str(evidence)
    assert "[REDACTED]" in evidence[0]["title"]
