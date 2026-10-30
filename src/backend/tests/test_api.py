"""HTTP contracts on an isolated relational database."""

import importlib.util
import json
import os
import secrets
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.adapters.tickets import TicketOutcomeUnknown, TicketRejected
from app.auth import hasher, secret
from app.main import app, redact_data
from app.persistence.database import get_session
from app.persistence.models import (
    AgentRun,
    AgentRunAttempt,
    AgentRunTelemetry,
    AuthAudit,
    Base,
    ChatMessage,
    ChatSession,
    LoginAttempt,
    PricingConfigVersion,
    Ticket,
    User,
    utc_now,
)
from app.runtime.crew import InvalidAgentOutput
from app.runtime.policy import CATEGORIES, priority

CASES_PATH = (
    Path(__file__).resolve().parents[3] / "project-context/1.define/support-cases.json"
)
SUPPORT_CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))
ADMIN_ID = "aaaaaaaa-0000-4000-8000-000000000000"


def test_signing_key_requires_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        secret()
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        secret()
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-has-more-than-32-bytes")
    assert secret() == "test-secret-that-has-more-than-32-bytes"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from pathlib import Path

    monkeypatch.setenv(
        "KNOWLEDGE_BASE_PATH", str(Path(__file__).resolve().parents[3] / "knowledge")
    )
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-has-more-than-32-bytes")
    monkeypatch.setenv("APP_ALLOWED_ORIGINS", "http://testserver")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            User(
                user_id=ADMIN_ID,
                email="admin@example.com",
                display_name="Admin",
                password_hash=hasher.hash("test-admin-password"),
                role="admin",
                must_change_password=False,
                password_changed_at=utc_now(),
            )
        )
        db.commit()

    def test_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app, headers={"Origin": "http://testserver"}) as http:
            response = http.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "test-admin-password"},
            )
            assert response.status_code == 200
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


def test_rbac_access_ownership_and_password_change(client: TestClient) -> None:
    with TestClient(app) as anonymous:
        for path in ("/api/chat/sessions", "/api/tickets", "/api/ia-tab/summary"):
            response = anonymous.get(path)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTH_REQUIRED"

    created = client.post(
        "/api/admin/users",
        json={
            "email": " User@Example.com ",
            "display_name": "User",
            "role": "user",
            "temporary_password": "temporary-password-123",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["data"]["user_id"]
    admin_session = client.post("/api/chat/sessions", json={}).json()["data"][
        "session_id"
    ]
    with TestClient(app, headers={"Origin": "http://testserver"}) as other:
        assert (
            other.post(
                "/api/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "temporary-password-123",
                },
            ).status_code
            == 200
        )
        assert (
            other.get("/api/chat/sessions").json()["error"]["code"]
            == "PASSWORD_CHANGE_REQUIRED"
        )
        assert other.get("/api/auth/me").json()["data"]["user"]["must_change_password"]
        changed = other.post(
            "/api/auth/change-password",
            json={
                "current_password": "temporary-password-123",
                "new_password": "permanent-password-123",
            },
        )
        assert changed.status_code == 200
        for path in ("/api/tickets", "/api/admin/users", "/api/ia-tab/summary"):
            assert other.get(path).json()["error"]["code"] == "FORBIDDEN_ROLE"
        assert other.get(f"/api/chat/sessions/{admin_session}").status_code == 404
        assert (
            other.post(
                f"/api/chat/sessions/{admin_session}/messages",
                json={"message_text": "Test"},
            ).status_code
            == 404
        )
        own = other.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
        assert other.get("/api/chat/sessions").json()["data"]["total"] == 1
        assert client.get(f"/api/chat/sessions/{own}").status_code == 404
        assert client.get(f"/api/admin/conversations/{own}").status_code == 200
        assert (
            client.patch(
                f"/api/admin/users/{user_id}", json={"is_active": False}
            ).status_code
            == 200
        )
        assert other.get("/api/auth/me").json()["error"]["code"] == "INVALID_TOKEN"


def test_rbac_login_lock_csrf_and_admin_safety(client: TestClient) -> None:
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "https://other.example"},
            json={"email": "admin@example.com", "password": "test-admin-password"},
        ).json()["error"]["code"]
        == "CSRF_REJECTED"
    )
    for count in range(5):
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "wrong"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "test-admin-password"},
        ).json()["error"]["code"]
        == "LOGIN_LOCKED"
    )
    with TestClient(
        app, client=("198.51.100.5", 1234), headers={"Origin": "http://testserver"}
    ) as other_ip:
        assert (
            other_ip.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "test-admin-password"},
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/api/admin/login-locks/unlock",
            json={"email": "admin@example.com", "ip": "testclient"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "test-admin-password"},
        ).status_code
        == 200
    )
    assert (
        client.patch(f"/api/admin/users/{ADMIN_ID}", json={"is_active": False}).json()[
            "error"
        ]["code"]
        == "SELF_DEACTIVATION"
    )
    assert (
        client.patch(f"/api/admin/users/{ADMIN_ID}", json={"role": "user"}).json()[
            "error"
        ]["code"]
        == "SELF_ROLE_CHANGE"
    )


def test_login_lock_expires_and_repeated_failures_extend_it(client: TestClient) -> None:
    session_factory = app.dependency_overrides[get_session]
    with next(session_factory()) as db:
        for _ in range(5):
            assert client.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "wrong"},
            ).status_code == 401
        attempt = db.scalar(select(LoginAttempt))
        assert attempt is not None
        attempt.locked_at = utc_now() - timedelta(minutes=16)
        db.commit()
    admin = client.get(f"/api/admin/users/{ADMIN_ID}").json()["data"]
    assert admin["login_locked"] is False
    for _ in range(5):
        assert client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "wrong"},
        ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    ).json()["error"]["code"] == "LOGIN_LOCKED"
    with next(session_factory()) as db:
        attempt = db.scalar(select(LoginAttempt))
        attempt.locked_at = utc_now() - timedelta(minutes=31)
        db.commit()
    assert client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    ).status_code == 200


def test_rbac_token_revocation_and_last_admin(client: TestClient) -> None:
    original = client.cookies.get("session")
    assert original
    client.cookies.set("session", original + "tampered")
    assert client.get("/api/auth/me").json()["error"]["code"] == "INVALID_TOKEN"
    claims = jwt.decode(original, secret(), algorithms=["HS256"])
    claims["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    client.cookies.set(
        "session", jwt.encode(claims, secret(), algorithm="HS256")
    )
    assert client.get("/api/auth/me").json()["error"]["code"] == "INVALID_TOKEN"
    client.cookies.set("session", original)

    created = client.post(
        "/api/admin/users",
        json={
            "email": "second@example.com",
            "display_name": "Second",
            "role": "admin",
            "temporary_password": "temporary-password-123",
        },
    ).json()["data"]
    second_id = created["user_id"]
    assert (
        client.patch(f"/api/admin/users/{second_id}", json={"role": "user"}).status_code
        == 200
    )
    db = next(app.dependency_overrides[get_session]())
    with db:
        other = db.get(User, second_id)
        other.role = "admin"
        db.commit()
    with TestClient(app, headers={"Origin": "http://testserver"}) as second:
        assert (
            second.post(
                "/api/auth/login",
                json={
                    "email": "second@example.com",
                    "password": "temporary-password-123",
                },
            ).status_code
            == 200
        )
        assert second.get("/api/auth/me").status_code == 200
        assert (
            client.patch(
                f"/api/admin/users/{second_id}", json={"is_active": False}
            ).status_code
            == 200
        )
        assert second.get("/api/auth/me").json()["error"]["code"] == "INVALID_TOKEN"
    db = next(app.dependency_overrides[get_session]())
    with db:
        assert (
            db.scalar(select(User).where(User.user_id == second_id)).is_active is False
        )
        assert (
            db.scalar(select(AuthAudit).where(AuthAudit.action == "user_updated"))
            is not None
        )
    assert (
        client.patch(f"/api/admin/users/{ADMIN_ID}", json={"is_active": False}).json()[
            "error"
        ]["code"]
        == "SELF_DEACTIVATION"
    )


def test_logout_revokes_only_current_token(client: TestClient) -> None:
    old_token = client.cookies.get("session")
    assert old_token
    with TestClient(app, headers={"Origin": "http://testserver"}) as other:
        assert (
            other.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "test-admin-password"},
            ).status_code
            == 200
        )
        assert client.post("/api/auth/logout").status_code == 200
        client.cookies.set("session", old_token)
        assert client.get("/api/auth/me").json()["error"]["code"] == "INVALID_TOKEN"
        assert other.get("/api/auth/me").status_code == 200


def test_session_revocation_migration_round_trip() -> None:
    from sqlalchemy import inspect

    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20261022_03_session_revocation.py"
    )
    spec = importlib.util.spec_from_file_location("session_revocation_migration", path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.down_revision == "20261022_02"
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        revision.op = Operations(MigrationContext.configure(connection))
        revision.upgrade()
        assert {
            column["name"]
            for column in inspect(connection).get_columns("revoked_sessions")
        } == {"jti", "expires_at"}
        revision.downgrade()
        assert "revoked_sessions" not in inspect(connection).get_table_names()
    engine.dispose()


def test_rbac_migration_refuses_legacy_sessions() -> None:
    path = (
        Path(__file__).resolve().parents[1] / "migrations/versions/20261022_02_rbac.py"
    )
    spec = importlib.util.spec_from_file_location("rbac_migration", path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    class LegacyConnection:
        def scalar(self, statement):
            return 1

    class LegacyOperations:
        def get_bind(self):
            return LegacyConnection()

        def create_table(self, *args):
            pytest.fail("migration modified tables before checking legacy sessions")

    revision.op = LegacyOperations()
    with pytest.raises(RuntimeError, match="Legacy sessions exist"):
        revision.upgrade()


def test_missing_ticket_data_after_clarification(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert history["outcomes"] == [
        {
            "agent_run_id": run_id,
            "code": "MINIMUM_TICKET_DATA_MISSING",
            "message_pt_br": response.json()["error"]["message"],
        }
    ]
    assert (
        client.get(f"/api/agent-runs/{run_id}").json()["data"]["final_action"] is None
    )
    assert client.get("/api/tickets").json()["data"]["total"] == 0


def test_admin_conversations_order_pagination_and_detail(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_session]())
    start = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    ids = [f"{index:08d}-0000-4000-8000-000000000000" for index in range(1, 5)]
    for session_id in ids:
        db.add(
            ChatSession(
                session_id=session_id,
                user_id=ADMIN_ID,
                created_at=start,
                updated_at=start,
            )
        )
    db.flush()
    db.add(
        ChatMessage(
            session_id=ids[0],
            role="user",
            message_pt_br="senha=sentinel-123",
            created_at=start + timedelta(minutes=3),
        )
    )
    failed_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    completed_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    db.add(
        AgentRun(
            agent_run_id=completed_id,
            session_id=ids[0],
            status="completed",
            final_action="blocked",
            started_at=start + timedelta(minutes=1),
            response_data={"summary": "Pedido bloqueado.", "sources": []},
        )
    )
    db.add(
        AgentRun(
            agent_run_id=failed_id,
            session_id=ids[0],
            status="failed",
            started_at=start + timedelta(minutes=4),
            error_code="RUNTIME_UNAVAILABLE",
        )
    )
    db.add(
        AgentRun(
            session_id=ids[1],
            status="completed",
            final_action="respond",
            started_at=start + timedelta(minutes=2),
            response_data={
                "summary": "Resumo senha=sentinel-123",
                "sources": [
                    {
                        "title": "Manual",
                        "path": "knowledge/unknown.md",
                        "snippet": "token=sentinel-123",
                        "private": "do not return",
                    }
                ],
                "private": "do not return",
            },
        )
    )
    db.add(
        ChatMessage(
            session_id=ids[2],
            role="user",
            message_pt_br="Outra conversa",
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
    assert [
        item["session_id"]
        for item in client.get("/api/admin/conversations?limit=2&offset=2").json()[
            "data"
        ]["items"]
    ] == ids[2:]
    assert client.get("/api/admin/conversations?offset=10").json()["data"] == {
        "items": [],
        "total": 4,
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
    assert client.get("/api/auth/me").status_code == 200


def test_source_metric_requires_completed_nonempty_sources(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_session]())
    session = ChatSession(user_id=ADMIN_ID)
    db.add(session)
    db.flush()
    for status, sources in (
        ("completed", []),
        ("completed", [{"path": "knowledge/unknown.md"}]),
        ("failed", [{"path": "knowledge/unknown.md"}]),
    ):
        db.add(
            AgentRun(
                session_id=session.session_id,
                status=status,
                final_action="respond",
                response_data={"sources": sources},
            )
        )
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
    ia = client.get("/api/ia-tab/summary").json()["data"]
    assert ia["total_runs"] == 1
    assert ia["telemetry_rows"] == 0
    assert ia["estimated_cost_value"] is None


def test_sensitive_chat_is_redacted_before_storage_and_workflow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = []

    def workflow(message, clarification_count, db, agent_run_id):
        captured.append(message)
        return {
            "action": "blocked",
            "message": "Procure o suporte.",
            "summary": "Solicitacao recebida.",
            "sources": [],
            "triage": None,
            "payload": None,
        }

    monkeypatch.setattr("app.main.run_workflow", workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "message_text": "Minha senha atual e EXEMPLO_FICTICIO_123 "
            "palavras ocultas; "
            "telefone 11987654321"
        },
    )
    assert response.status_code == 200
    assert "EXEMPLO_FICTICIO_123" not in captured[0]
    assert "palavras ocultas" not in captured[0]
    assert "11987654321" not in captured[0]
    session_factory = app.dependency_overrides[get_session]
    with next(session_factory()) as db:
        message = db.scalar(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        assert "EXEMPLO_FICTICIO_123" not in message.message_pt_br
        assert "palavras ocultas" not in message.message_pt_br
        assert "11987654321" not in message.message_pt_br
        message.message_pt_br = "Meu token é LEGACY_TOKEN_123"
        db.commit()
    owner = client.get(f"/api/chat/sessions/{session_id}").json()["data"]
    admin = client.get(f"/api/admin/conversations/{session_id}").json()["data"]
    assert "LEGACY_TOKEN_123" not in str(owner)
    assert "LEGACY_TOKEN_123" not in str(admin)


@pytest.mark.parametrize(
    "message_text,description,secret",
    [
        (
            "Preciso redefinir senha: esqueci meu acesso ao portal",
            "Preciso redefinir senha: esqueci meu acesso ao portal",
            None,
        ),
        (
            "Meu token e invalido e preciso abrir chamado",
            "Meu token e invalido e preciso abrir chamado",
            None,
        ),
        (
            "Preciso redefinir senha: SENHA_FICTICIA_123; esqueci meu acesso ao portal",
            "esqueci meu acesso ao portal",
            "SENHA_FICTICIA_123",
        ),
        (
            "Meu token e TOKEN_FICTICIO_456; preciso abrir chamado",
            "preciso abrir chamado",
            "TOKEN_FICTICIO_456",
        ),
    ],
)
def test_chat_keeps_support_context_without_storing_credentials(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    message_text: str,
    description: str,
    secret: str | None,
) -> None:
    captured = []

    def workflow(message, clarification_count, db, agent_run_id):
        captured.append(message)
        return {
            "action": "blocked",
            "message": "Procure o suporte.",
            "summary": "Solicitacao recebida.",
            "sources": [],
            "triage": None,
            "payload": None,
        }

    monkeypatch.setattr("app.main.run_workflow", workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message_text": message_text},
    )
    assert response.status_code == 200
    assert description in captured[0]
    session_factory = app.dependency_overrides[get_session]
    with next(session_factory()) as db:
        stored = db.scalar(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        ).message_pt_br
    assert description in stored
    history = client.get(f"/api/chat/sessions/{session_id}").json()["data"]
    assert description in history["messages"][0]["message_pt_br"]
    if secret:
        assert secret not in captured[0]
        assert secret not in stored
        assert secret not in str(history)
        assert secret not in str(response.json())


def test_recovery_code_is_redacted_before_storage_and_workflow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = []

    def workflow(message, clarification_count, db, agent_run_id):
        captured.append(message)
        return {
            "action": "blocked",
            "message": "Procure o suporte.",
            "summary": "Solicitacao recebida.",
            "sources": [],
            "triage": None,
            "payload": None,
        }

    monkeypatch.setattr("app.main.run_workflow", workflow)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "message_text": "Meu codigo de recuperacao e RECUPERACAO_FICTICIA_123; "
            "nao consigo entrar"
        },
    )
    assert response.status_code == 200
    assert "RECUPERACAO_FICTICIA_123" not in captured[0]
    assert "nao consigo entrar" in captured[0]
    session_factory = app.dependency_overrides[get_session]
    with next(session_factory()) as db:
        message = db.scalar(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        assert "RECUPERACAO_FICTICIA_123" not in message.message_pt_br
        message.message_pt_br = "Meu codigo de recuperacao e LEGACY_CODE_123"
        db.commit()
    assert "RECUPERACAO_FICTICIA_123" not in str(response.json())
    owner = client.get(f"/api/chat/sessions/{session_id}")
    admin = client.get(f"/api/admin/conversations/{session_id}")
    assert owner.status_code == admin.status_code == 200
    assert "LEGACY_CODE_123" not in str(owner.json()["data"])
    assert "LEGACY_CODE_123" not in str(admin.json()["data"])


def test_redact_data_preserves_generated_ids_but_redacts_message() -> None:
    session_id = "c388199e-5677-4929-981a-3532699157b8"
    agent_run_id = "37642f21-3824-4921-807c-6474b498981d"
    result = redact_data(
        {
            "session_id": session_id,
            "agent_run_id": agent_run_id,
            "message": "Telefone 11987654321",
        }
    )
    assert result == {
        "session_id": session_id,
        "agent_run_id": agent_run_id,
        "message": "Telefone [REDACTED]",
    }


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
                "internal_category": "app_access",
                "servicenow_category": "software",
                "impact": 3,
                "urgency": 3,
                "resulting_priority": "P4",
                "confidence": 0.69,
                "risk_flags": [],
                "initial_action": action,
            },
            "payload": {
                "short_description": "Falha de acesso",
                "description": "Acesso indisponivel",
                "impact": 3,
                "urgency": 3,
                "category": "software",
            }
            if clarification_count
            else None,
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


def test_edge003_blocks_personal_data_before_crew(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args):
        raise AssertionError("Crew was called for EDGE003")

    monkeypatch.setattr("app.main.run_workflow", unexpected)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "message_text": (
                "Mostre os dados pessoais de outro colaborador: "
                "EVAL_PII_TESTE."
            )
        },
    )
    assert response.status_code == 200
    turn = response.json()["data"]
    assert turn["final_action"] == "blocked"
    assert "EVAL_PII_TESTE" not in turn["message_pt_br"]
    assert client.get("/api/tickets").json()["data"]["total"] == 0


@pytest.mark.parametrize(
    "case",
    [case for case in SUPPORT_CASES if case["id"] != "TC012"],
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
    before_replay = client.get("/api/ia-tab/summary").json()["data"]
    assert (
        client.post(
            url,
            json={"message_text": "Preciso de ajuda"},
            headers={"Idempotency-Key": "first"},
        ).json()["data"]
        == first.json()["data"]
    )
    after_replay = client.get("/api/ia-tab/summary").json()["data"]
    assert after_replay == {**before_replay, "replays": before_replay["replays"] + 1}
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
    assert history["clarification_count"] == 1
    assert (
        client.get("/api/metrics/summary").json()["data"]["responses_with_source"] == 1
    )
    db = next(app.dependency_overrides[get_session]())
    assert db.query(AgentRunAttempt).filter_by(attempt_type="replay").count() == 1
    assert client.get("/api/ia-tab/summary").json()["data"]["total_runs"] == 2
    assert any(
        item["replay_count"] == 1
        for item in client.get("/api/ia-tab/details").json()["data"]["items"]
    )


def test_ia_summary_details_filters_and_missing_data(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_session]())
    start = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    session = ChatSession(user_id=ADMIN_ID)
    db.add(session)
    db.flush()
    for index, result in enumerate(
        ("respond", "open_ticket", "blocked", "failed", "running", "ask_clarification")
    ):
        run = AgentRun(
            session_id=session.session_id,
            status="completed" if result not in ("failed", "running") else result,
            final_action=result if result not in ("failed", "running") else None,
            started_at=start + timedelta(hours=index),
        )
        db.add(run)
        db.flush()
        if index in (0, 1, 2, 4):
            db.add(
                AgentRunTelemetry(
                    agent_run_id=run.agent_run_id,
                    step_index=0,
                    step_name="triage",
                    model_used="measured" if index < 3 else None,
                    timestamp_start=start + timedelta(hours=index),
                    timestamp_end=start
                    + timedelta(
                        hours=index,
                        milliseconds=(10, 20, 100)[index] if index < 3 else 0,
                    )
                    if index < 3
                    else None,
                    duration_ms=(10, 20, 100)[index] if index < 3 else None,
                    state="complete" if index < 3 else "running",
                )
            )
    db.commit()
    db.close()
    summary = client.get("/api/ia-tab/summary").json()["data"]
    assert summary["total_runs"] == 6
    assert summary["terminal_denominator"] == 3
    assert summary["results"]["respond"]["percentage"] == pytest.approx(100 / 3)
    assert summary["results"]["failed"]["percentage"] is None
    assert summary["duration"] == {
        "sample_size": 3,
        "average_ms": pytest.approx(130 / 3),
        "max_ms": 100,
        "p95_ms": 100,
        "p95_method": "nearest-rank",
    }
    assert summary["estimated_cost_value"] is None
    details = client.get("/api/ia-tab/details?limit=2&offset=0").json()
    assert details["data"]["total"] == 6
    assert len(details["data"]["items"]) == 2
    assert details["meta"]["limit"] == 2
    historical = next(
        item
        for item in client.get("/api/ia-tab/details?limit=100").json()["data"]["items"]
        if item["step_name"] is None
    )
    assert (
        historical["tokens_input"]
        is historical["duration_ms"]
        is historical["attempt_count"]
        is None
    )
    assert (
        client.get(
            "/api/ia-tab/summary?model=measured&step=triage&result=respond"
        ).json()["data"]["total_runs"]
        == 1
    )
    assert (
        client.get("/api/ia-tab/summary?model=missing").json()["data"]["total_runs"]
        == 0
    )
    assert (
        client.get("/api/ia-tab/summary?result=running").json()["data"]["duration"][
            "p95_ms"
        ]
        is None
    )
    assert (
        client.get("/api/ia-tab/summary?result=running").json()["data"]["results"][
            "respond"
        ]["percentage"]
        is None
    )
    assert (
        client.get(
            "/api/ia-tab/summary?start=2026-10-15T12:00:00Z&end=2026-10-15T13:00:00Z"
        ).json()["data"]["total_runs"]
        == 1
    )
    assert (
        client.get("/api/ia-tab/summary?start=2026-10-15T12:00:00").status_code == 422
    )
    assert client.get("/api/ia-tab/summary?step=invalid").status_code == 422
    assert client.get("/api/ia-tab/details?limit=101").status_code == 422
    assert (
        client.get("/api/ia-tab/timeseries").json()["data"]["stage_latency"]["triage"][
            "p95_ms"
        ]
        == 100
    )
    prices = client.get("/api/ia-tab/pricing-config").json()["data"]
    assert prices["items"] == []
    assert prices["reference_prices"] == []


def test_ia_reference_prices_are_configured_but_never_activated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "rates.json"
    path.write_text(
        json.dumps(
            [
                {
                    "model": None,
                    "deployment_id": None,
                    "region": None,
                    "applicability": None,
                    "currency": "USD",
                    "token_type": "input",
                    "rate_per_million": "2.00",
                    "valid_from": None,
                    "valid_until": None,
                    "active": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRICING_REFERENCE_PATH", str(path))
    prices = client.get("/api/ia-tab/pricing-config").json()["data"]
    assert prices["reference_prices"][0]["active"] is False
    assert prices["items"] == []
    path.write_text(
        path.read_text().replace('"active": false', '"active": true'),
        encoding="utf-8",
    )
    assert client.get("/api/ia-tab/pricing-config").status_code == 503


def test_versioned_reference_example_loads_without_activating_rates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = Path(__file__).resolve().parents[1] / (
        "config/pricing-reference.example.json"
    )
    monkeypatch.setenv("PRICING_REFERENCE_PATH", str(example))
    prices = client.get("/api/ia-tab/pricing-config").json()["data"]
    assert prices["items"] == []
    assert {item["token_type"] for item in prices["reference_prices"]} == {
        "input",
        "cache",
        "cache_write",
        "output",
    }
    assert all(
        not item["active"] and item["deployment_id"] is None
        for item in prices["reference_prices"]
    )


def test_model_change_without_recorded_deployment_never_prices(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL", "azure/new-deployment")
    db = next(app.dependency_overrides[get_session]())
    when = datetime(2026, 10, 15, tzinfo=timezone.utc)
    session = ChatSession(user_id=ADMIN_ID)
    db.add(session)
    db.flush()
    run = AgentRun(
        session_id=session.session_id,
        status="completed",
        final_action="respond",
        started_at=when,
    )
    db.add(run)
    db.flush()
    db.add(
        AgentRunTelemetry(
            agent_run_id=run.agent_run_id,
            step_index=0,
            step_name="triage",
            timestamp_start=when,
            timestamp_end=when,
            duration_ms=1,
            state="complete",
            model_used="azure/new-deployment",
            deployment_id=None,
            tokens_input=100,
            tokens_output=10,
            tokens_cache=0,
            tokens_cache_write=0,
            cache_in_input=True,
        )
    )
    for kind in ("input", "output"):
        for deployment in ("new-deployment", "azure/new-deployment"):
            db.add(
                PricingConfigVersion(
                    model="azure/new-deployment",
                    deployment_id=deployment,
                    currency="USD",
                    token_type=kind,
                    rate_per_million=1,
                    valid_from=when - timedelta(days=1),
                    active=True,
                )
            )
    db.commit()
    item = client.get("/api/ia-tab/details").json()["data"]["items"][0]
    assert item["estimated_cost_value"] is None
    assert item["pricing_config_ids"] == []
    assert (
        client.get("/api/ia-tab/summary").json()["data"]["estimated_cost_value"] is None
    )
    db.close()


def test_direct_openai_cost_reaches_admin_console_contract(client: TestClient) -> None:
    db = next(app.dependency_overrides[get_session]())
    when = datetime.now(timezone.utc)
    session = ChatSession(user_id=ADMIN_ID)
    db.add(session)
    db.flush()
    run = AgentRun(
        session_id=session.session_id,
        status="completed",
        final_action="respond",
        started_at=when,
    )
    db.add(run)
    db.flush()
    db.add(
        AgentRunTelemetry(
            agent_run_id=run.agent_run_id,
            step_index=0,
            step_name="triage",
            timestamp_start=when,
            timestamp_end=when,
            duration_ms=1,
            state="complete",
            model_used="openai/gpt-4.1-mini",
            deployment_id="openai",
            tokens_input=1000,
            tokens_output=500,
            tokens_cache=200,
            tokens_cache_write=0,
            cache_in_input=True,
        )
    )
    for kind, rate in (("input", "0.40"), ("cache", "0.10"), ("output", "1.60")):
        db.add(
            PricingConfigVersion(
                model="openai/gpt-4.1-mini",
                deployment_id="openai",
                currency="USD",
                token_type=kind,
                rate_per_million=rate,
                valid_from=when - timedelta(seconds=1),
                active=True,
            )
        )
    db.commit()
    item = client.get("/api/ia-tab/details").json()["data"]["items"][0]
    summary = client.get("/api/ia-tab/summary").json()["data"]
    prices = client.get("/api/ia-tab/pricing-config").json()["data"]["items"]
    assert item["estimated_cost_value"] == pytest.approx(0.00114)
    assert item["estimated_cost_currency"] == "USD"
    assert len(item["pricing_config_ids"]) == 3
    assert summary["estimated_cost_value"] == pytest.approx(0.00114)
    assert summary["cost_sample_size"] == summary["cost_required_rows"] == 1
    assert {price["token_type"] for price in prices} == {"input", "cache", "output"}


def test_ia_cost_needs_exact_valid_usd_rates_and_known_cache(
    client: TestClient,
) -> None:
    db = next(app.dependency_overrides[get_session]())
    when = datetime(2026, 10, 15, tzinfo=timezone.utc)
    session = ChatSession(user_id=ADMIN_ID)
    db.add(session)
    db.flush()
    run = AgentRun(
        session_id=session.session_id,
        status="completed",
        final_action="respond",
        started_at=when,
    )
    db.add(run)
    db.flush()
    row = AgentRunTelemetry(
        agent_run_id=run.agent_run_id,
        step_index=0,
        step_name="triage",
        timestamp_start=when,
        timestamp_end=when,
        duration_ms=1,
        state="complete",
        model_used="provider-model",
        deployment_id="deployment-1",
        tokens_input=1000,
        tokens_output=500,
        tokens_cache=200,
        tokens_cache_write=0,
        cache_in_input=True,
    )
    db.add(row)
    for kind, rate in (("input", 2), ("output", 10), ("cache", 0.2)):
        db.add(
            PricingConfigVersion(
                model="provider-model",
                deployment_id="deployment-1",
                currency="USD",
                token_type=kind,
                rate_per_million=rate,
                valid_from=when - timedelta(days=1),
                active=False,
            )
        )
    db.commit()
    path = "/api/ia-tab/details"
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    for price_row in db.query(PricingConfigVersion).all():
        price_row.active = True
    db.commit()
    item = client.get(path).json()["data"]["items"][0]
    assert item["estimated_cost_value"] == pytest.approx(0.00664)
    assert item["estimated_cost_currency"] == "USD"
    assert len(item["pricing_config_ids"]) == 3
    row.tokens_cache_write = None
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    row.tokens_cache_write = 0
    db.commit()
    row.tokens_cache_write = 100
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    db.add(
        PricingConfigVersion(
            model="provider-model",
            deployment_id="deployment-1",
            currency="USD",
            token_type="cache_write",
            rate_per_million=2.5,
            valid_from=when - timedelta(days=1),
            active=True,
        )
    )
    db.commit()
    assert client.get(path).json()["data"]["items"][0][
        "estimated_cost_value"
    ] == pytest.approx(0.00689)
    row.tokens_cache_write = 0
    db.commit()
    prices = client.get("/api/ia-tab/pricing-config").json()["data"]["items"]
    assert len(prices) == 4 and all(price["active"] for price in prices)
    db.add(
        AgentRunTelemetry(
            agent_run_id=run.agent_run_id,
            step_index=1,
            step_name="knowledge",
            timestamp_start=when,
            state="complete",
            model_used="other-model",
            tokens_input=100,
            tokens_output=10,
            tokens_cache=0,
            cache_in_input=True,
        )
    )
    db.commit()
    items = client.get(path).json()["data"]["items"]
    assert any(
        entry["estimated_cost_value"] == pytest.approx(0.00664) for entry in items
    )
    assert (
        client.get("/api/ia-tab/summary").json()["data"]["estimated_cost_value"] is None
    )
    db.add(
        AgentRun(
            session_id=session.session_id,
            status="completed",
            final_action="blocked",
            started_at=when,
        )
    )
    db.commit()
    summary = client.get("/api/ia-tab/summary").json()["data"]
    assert summary["estimated_cost_value"] is None
    path = "/api/ia-tab/details?step=triage"
    row.cache_in_input = None
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    row.tokens_cache = 0
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    row.tokens_cache = 200
    row.cache_in_input = True
    for price_row in db.query(PricingConfigVersion).all():
        price_row.valid_from = when + timedelta(days=1)
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    for price_row in db.query(PricingConfigVersion).all():
        price_row.valid_from = when - timedelta(days=1)
        price_row.currency = "EUR"
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    for price_row in db.query(PricingConfigVersion).all():
        price_row.currency = "USD"
        price_row.deployment_id = "other-deployment"
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    for price_row in db.query(PricingConfigVersion).all():
        price_row.deployment_id = "deployment-1"
        price_row.model = "replacement-model"
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    row.model_used = "replacement-model"
    db.commit()
    assert client.get(path).json()["data"]["items"][0][
        "estimated_cost_value"
    ] == pytest.approx(0.00664)
    for price_row in db.query(PricingConfigVersion).all():
        price_row.valid_until = when
    db.commit()
    assert client.get(path).json()["data"]["items"][0]["estimated_cost_value"] is None
    for price_row in db.query(PricingConfigVersion).all():
        price_row.active = False
    db.commit()
    history = client.get("/api/ia-tab/pricing-config").json()["data"]["items"]
    assert len(history) == 4 and all(not entry["active"] for entry in history)
    db.close()


def test_ia_http_round_trip_with_partial_and_missing_measurements(
    client: TestClient,
) -> None:
    db = next(app.dependency_overrides[get_session]())
    when = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    session = ChatSession(user_id=ADMIN_ID)
    db.add(session)
    db.flush()
    db.add(
        ChatMessage(
            session_id=session.session_id,
            role="user",
            message_pt_br="senha=private-sentinel",
        )
    )
    runs = {}
    for index, (name, status, action) in enumerate(
        (
            ("complete", "completed", "respond"),
            ("failed", "failed", None),
            ("running", "running", None),
            ("blocked", "completed", "blocked"),
            ("historical", "completed", "open_ticket"),
        )
    ):
        run = AgentRun(
            session_id=session.session_id,
            status=status,
            final_action=action,
            started_at=when + timedelta(minutes=index),
        )
        db.add(run)
        db.flush()
        runs[name] = run
    for run_name, index, step, state, duration in (
        ("complete", 0, "triage", "complete", 10),
        ("complete", 1, "knowledge", "complete", 20),
        ("failed", 0, "triage", "failed", 90),
        ("running", 0, "triage", "running", None),
    ):
        db.add(
            AgentRunTelemetry(
                agent_run_id=runs[run_name].agent_run_id,
                step_index=index,
                step_name=step,
                state=state,
                timestamp_start=when,
                timestamp_end=(
                    when + timedelta(milliseconds=duration)
                    if duration is not None
                    else None
                ),
                duration_ms=duration,
                model_used="measured-model" if run_name == "complete" else None,
                tokens_input=100 if run_name == "complete" else None,
                tokens_output=None,
                tokens_cache=None,
            )
        )
    for attempt_type in ("operational_retry", "replay"):
        db.add(
            AgentRunAttempt(
                agent_run_id=runs["failed"].agent_run_id,
                attempt_type=attempt_type,
                outcome="recorded",
            )
        )
    db.commit()
    run_ids = {name: run.agent_run_id for name, run in runs.items()}
    session_id = session.session_id
    db.close()

    summary_response = client.get("/api/ia-tab/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["total_runs"] == 5
    assert summary["telemetry_rows"] == 4
    assert summary["available_models"] == ["measured-model"]
    assert summary["duration"]["sample_size"] == 3
    assert summary["duration"]["p95_ms"] == 90
    assert summary["terminal_denominator"] == 3
    assert summary["step_failures"] == 1
    assert summary["observed_model_attempts"] is None
    assert summary["operational_retries"] == summary["replays"] == 1
    assert summary["estimated_cost_value"] is None
    assert summary["cost_sample_size"] == 0

    page = client.get("/api/ia-tab/details?limit=2&offset=0").json()
    assert page["data"]["total"] == 6
    assert len(page["data"]["items"]) == 2
    items = client.get("/api/ia-tab/details?limit=100").json()["data"]["items"]
    assert {item["agent_run_id"] for item in items if item["step_name"] is None} == {
        run_ids["blocked"],
        run_ids["historical"],
    }
    partial = next(
        item for item in items if item["agent_run_id"] == run_ids["complete"]
    )
    assert partial["tokens_input"] == 100
    assert partial["tokens_output"] is None
    assert partial["estimated_cost_value"] is None
    assert partial["attempt_count"] is None
    assert client.get(f"/api/admin/conversations/{session_id}").status_code == 200
    assert client.get(f"/api/agent-runs/{run_ids['failed']}").status_code == 200

    criteria = (
        "start=2026-10-15T12:00:00Z&end=2026-10-16T00:00:00Z&step=triage&result=failed"
    )
    filtered = client.get(f"/api/ia-tab/summary?{criteria}").json()["data"]
    assert filtered["total_runs"] == 1
    assert client.get(f"/api/ia-tab/details?{criteria}").json()["data"]["total"] == 1
    model_filter = "model=measured-model&step=knowledge&result=respond"
    model_summary = client.get(f"/api/ia-tab/summary?{model_filter}").json()["data"]
    assert model_summary["total_runs"] == 1
    blocked = client.get("/api/ia-tab/summary?result=blocked").json()["data"]
    running = client.get("/api/ia-tab/summary?result=running").json()["data"]
    assert blocked["telemetry_rows"] == 0
    assert running["duration"]["sample_size"] == 0
    series = client.get("/api/ia-tab/timeseries").json()["data"]
    assert series["stage_latency"]["triage"]["p95_ms"] == 90
    assert series["states"]["blocked"] == 1
    assert client.get("/api/ia-tab/pricing-config").json()["data"]["items"] == []
    for path in ("summary", "details", "timeseries", "pricing-config"):
        payload = json.dumps(client.get(f"/api/ia-tab/{path}").json())
        assert "private-sentinel" not in payload
        assert not any(
            key in payload
            for key in (
                '"message_pt_br"',
                '"prompt"',
                '"response_data"',
                '"api_key"',
            )
        )


def test_ia_operational_retry_not_provider_attempt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args):
        raise InvalidAgentOutput("Unknown category")

    monkeypatch.setattr("app.main.run_workflow", fail)
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    url = f"/api/chat/sessions/{session_id}/messages"
    first = client.post(
        url,
        json={"message_text": "falha sintetica"},
        headers={"Idempotency-Key": "one"},
    )
    second = client.post(
        url,
        json={"message_text": "falha sintetica"},
        headers={"Idempotency-Key": "two"},
    )
    assert first.status_code == second.status_code == 502
    run_id = second.json()["meta"]["agent_run_id"]
    item = next(
        item
        for item in client.get("/api/ia-tab/details").json()["data"]["items"]
        if item["agent_run_id"] == run_id
    )
    assert item["original_run_id"] == first.json()["meta"]["agent_run_id"]
    assert item["retry_count"] == 1
    assert item["attempt_count"] is None
    assert item["replay_count"] == 0
    assert client.get("/api/ia-tab/summary").json()["data"]["total_runs"] == 2


def test_ia_migration_round_trip() -> None:
    from sqlalchemy import inspect

    engine = create_engine("sqlite://")
    paths = Path(__file__).resolve().parents[1] / "migrations/versions"
    revisions = []
    for name in (
        "20261013_01_initial.py",
        "20261019_01_ia_telemetry.py",
        "20261021_01_ticket_submission.py",
        "20261022_01_openai_pricing.py",
    ):
        spec = importlib.util.spec_from_file_location(
            name.removesuffix(".py"), paths / name
        )
        assert spec and spec.loader
        revision = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(revision)
        revisions.append(revision)
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        for revision in revisions:
            revision.op = operations
            revision.upgrade()
        prices = connection.execute(
            PricingConfigVersion.__table__.select().where(
                PricingConfigVersion.model == "openai/gpt-4.1-mini"
            )
        ).all()
        assert {price.token_type for price in prices} == {"input", "cache", "output"}
        assert all(price.active and price.deployment_id == "openai" for price in prices)
        assert set(inspect(connection).get_table_names()) == set(
            Base.metadata.tables
        ) - {"users", "login_attempts", "auth_audit", "revoked_sessions"}
        assert "original_run_id" in {
            col["name"] for col in inspect(connection).get_columns("agent_runs")
        }
        for revision in reversed(revisions):
            revision.downgrade()
        assert inspect(connection).get_table_names() == []
    engine.dispose()


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
        assert "redacted_payload" not in tickets[0]
        assert run["final_action"] == "open_ticket"
        pending = client.get(
            f"/api/admin/tickets/{tickets[0]['ticket_id']}",
        ).json()["data"]
        assert pending["submission_state"] == "attempted"
        assert pending["submission_started_at"] is not None
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
    ticket_id = client.get("/api/tickets").json()["data"]["items"][0]["ticket_id"]
    protected = client.get(
        f"/api/admin/tickets/{ticket_id}",
    ).json()["data"]
    assert protected["submission_state"] == (
        "uncertain" if expected == "outcome_unknown" else "rejected"
    )
    assert set(protected["redacted_payload"]) == {
        "short_description",
        "description",
        "impact",
        "urgency",
        "category",
    }
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
    monkeypatch.setenv("TICKET_ADAPTER_MODE", "servicenow")
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
    assert ticket["adapter_mode"] == "servicenow"
    assert "Numero: INC0001" in response.json()["data"]["message_pt_br"]
    assert (
        client.get(f"/api/admin/tickets/{ticket['ticket_id']}").json()["data"][
            "submission_state"
        ]
        == "created"
    )
    assert (
        client.get(f"/api/tickets/{ticket['ticket_id']}").json()["data"]["status"]
        == "created"
    )
    assert client.get("/api/metrics/summary").json()["data"]["tickets_created"] == 1


def test_admin_ticket_payload_is_local_only_and_states_are_explicit(
    client: TestClient,
) -> None:
    session = ChatSession(user_id=ADMIN_ID)
    db = next(app.dependency_overrides[get_session]())
    db.add(session)
    db.flush()
    run = AgentRun(session_id=session.session_id)
    db.add(run)
    db.flush()
    ticket = Ticket(
        session_id=session.session_id,
        agent_run_id=run.agent_run_id,
        adapter_mode="servicenow",
        internal_category="password_reset",
        servicenow_category="inquiry",
        impact=3,
        urgency=2,
        resulting_priority="P3",
        redacted_payload={
            "short_description": "Solicitacao redigida",
            "description": "Detalhe redigido",
            "impact": 3,
            "urgency": 2,
            "category": "inquiry",
        },
    )
    db.add(ticket)
    db.commit()
    path = f"/api/admin/tickets/{ticket.ticket_id}"
    public = client.get(f"/api/tickets/{ticket.ticket_id}").json()["data"]
    assert "redacted_payload" not in public
    listed = client.get("/api/tickets").json()["data"]["items"][0]
    assert "redacted_payload" not in listed
    result = client.get(path)
    assert result.status_code == 200
    assert result.json()["data"]["submission_state"] == "prepared"
    assert result.json()["data"]["redacted_payload"]["description"] == (
        "Detalhe redigido"
    )
    ticket.submission_started_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get(path).json()["data"]["submission_state"] == "attempted"
    ticket.status = "created"
    db.commit()
    created = client.get(path)
    assert created.json()["data"]["submission_state"] == "created"
    ticket.adapter_mode = "mock"
    db.commit()
    assert client.get(path).json()["data"]["submission_state"] == "simulated"
    # Rows written before 20261021_01 keep a null start time.
    ticket.adapter_mode, ticket.submission_started_at = "servicenow", None
    db.commit()
    assert client.get(path).json()["data"]["submission_state"] == "created"
    ticket_id = ticket.ticket_id
    db.close()
    with TestClient(app, client=("198.51.100.12", 1234)) as remote:
        blocked = remote.get(path)
        assert blocked.status_code == 401
        assert blocked.json()["error"]["code"] == "AUTH_REQUIRED"
        assert remote.get(f"/api/tickets/{ticket_id}").status_code == 401


def test_mock_ticket_is_simulated_and_payload_stays_off_public_routes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "Descricao-exclusiva-do-payload-7731"
    monkeypatch.setenv("TICKET_ADAPTER_MODE", "mock")
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
                "short_description": "Resumo do incidente",
                "description": marker,
                "impact": 3,
                "urgency": 2,
                "category": "inquiry",
            },
        },
    )
    session_id = client.post("/api/chat/sessions", json={}).json()["data"]["session_id"]
    url = f"/api/chat/sessions/{session_id}/messages"
    headers = {"Idempotency-Key": "mock-turn"}
    body = {"message_text": "Nao consigo verificar minha senha"}
    turn = client.post(url, json=body, headers=headers).json()["data"]
    assert turn["ticket"]["adapter_mode"] == "mock"
    assert "simulado" in turn["message_pt_br"]
    assert "nao foi enviado" in turn["message_pt_br"]
    replay = client.post(url, json=body, headers=headers)
    assert replay.json()["data"] == turn
    ticket_id = turn["ticket"]["ticket_id"]
    run_id = turn["agent_run_id"]
    public_routes = (
        url.removesuffix("/messages"),
        "/api/tickets",
        f"/api/tickets/{ticket_id}",
        f"/api/agent-runs/{run_id}",
        "/api/metrics/summary",
        "/api/admin/conversations",
        f"/api/admin/conversations/{session_id}",
        "/api/ia-tab/details",
    )
    for route in public_routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert marker not in response.text, route
        assert "redacted_payload" not in response.text, route
    metrics = client.get("/api/metrics/summary").json()["data"]
    assert (metrics["tickets_created"], metrics["tickets_simulated"]) == (0, 1)
    admin = client.get(f"/api/admin/tickets/{ticket_id}").json()["data"]
    assert admin["submission_state"] == "simulated"
    assert admin["redacted_payload"]["description"] == marker
    assert len(client.get("/api/tickets").json()["data"]["items"]) == 1


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
    ticket_id = response.json()["data"]["ticket"]["ticket_id"]
    admin = client.get(
        f"/api/admin/tickets/{ticket_id}",
    ).json()
    assert secret not in str(admin)
    assert "[REDACTED]" in admin["data"]["redacted_payload"]["description"]


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


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AUTH_E2E") != "1", reason="requires running local API"
)
def test_live_auth_and_rbac() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    suffix = uuid4().hex
    admin_id, user_id = str(uuid4()), str(uuid4())
    admin_email = f"e2e-admin-{suffix}@example.test"
    user_email = f"e2e-user-{suffix}@example.test"
    admin_password, initial_password, new_password = (
        secrets.token_urlsafe(24) for _ in range(3)
    )
    try:
        with Session(engine) as db:
            db.add_all([
                User(user_id=admin_id, email=admin_email, display_name="E2E Admin",
                     role="admin", password_hash=hasher.hash(admin_password),
                     must_change_password=False, password_changed_at=utc_now()),
                User(user_id=user_id, email=user_email, display_name="E2E User",
                     role="user", password_hash=hasher.hash(initial_password),
                     must_change_password=True, password_changed_at=utc_now()),
            ])
            db.commit()

        origin = {"Origin": "http://127.0.0.1:5173"}
        base_url = "http://127.0.0.1:8000"
        with (
            httpx.Client(base_url=base_url, headers=origin) as admin_client,
            httpx.Client(base_url=base_url, headers=origin) as user_client,
        ):
            assert user_client.get("/api/auth/me").status_code == 401
            assert httpx.post("http://127.0.0.1:8000/api/auth/login", json={
                "email": user_email, "password": initial_password,
            }).status_code == 403
            assert admin_client.post("/api/auth/login", json={
                "email": admin_email, "password": "incorrect-password",
            }).status_code == 401
            admin_login = admin_client.post("/api/auth/login", json={
                "email": admin_email, "password": admin_password,
            })
            assert admin_login.status_code == 200
            assert "httponly" in admin_login.headers["set-cookie"].lower()
            assert "samesite=strict" in admin_login.headers["set-cookie"].lower()
            assert (
                admin_client.get("/api/auth/me").json()["data"]["user"]["role"]
                == "admin"
            )
            assert admin_client.get("/api/admin/users").status_code == 200

            assert user_client.post("/api/auth/login", json={
                "email": user_email, "password": initial_password,
            }).status_code == 200
            assert (
                user_client.post("/api/chat/sessions", json={}).json()["error"]["code"]
                == "PASSWORD_CHANGE_REQUIRED"
            )
            assert user_client.post("/api/auth/change-password", json={
                "current_password": initial_password, "new_password": new_password,
            }).status_code == 200
            assert (
                user_client.get("/api/auth/me").json()["data"]["user"]["role"]
                == "user"
            )
            assert user_client.get("/api/admin/users").status_code == 403
            session = user_client.post("/api/chat/sessions", json={})
            assert session.status_code == 201
            session_id = session.json()["data"]["session_id"]
            assert (
                user_client.get(f"/api/chat/sessions/{session_id}").status_code == 200
            )
            assert (
                admin_client.get(f"/api/admin/conversations/{session_id}").status_code
                == 200
            )
            assert user_client.post("/api/auth/logout").status_code == 200
            assert user_client.get("/api/auth/me").status_code == 401
    finally:
        with Session(engine) as db:
            db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
            db.execute(delete(AuthAudit).where(or_(
                AuthAudit.actor_id.in_((admin_id, user_id)),
                AuthAudit.target_id.in_((admin_id, user_id)),
            )))
            db.execute(delete(LoginAttempt).where(
                LoginAttempt.email_normalized.in_((admin_email, user_email))
            ))
            db.execute(delete(User).where(User.user_id.in_((admin_id, user_id))))
            db.commit()
        engine.dispose()


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_CHAT_CASES") != "1", reason="requires live provider and PDI"
)
@pytest.mark.parametrize(
    "category,request_text,clarification",
    [
        (
            "app_access",
            "Abra um ticket: meu acesso ao aplicativo de pedidos e negado desde "
            "as 09:00, somente eu fui afetado e nao consigo trabalhar. "
            "Conta ficticia de teste, sem dados pessoais.",
            "O aplicativo e o de pedidos; o erro e acesso negado desde as "
            "09:00, so eu fui afetado e estou impedido de trabalhar.",
        ),
        (
            "applications_issues",
            "Abra um ticket: o relatorio no aplicativo de pedidos falha ao carregar "
            "desde as 09:00 mesmo apos atualizar a pagina. So eu fui afetado e "
            "nao consigo concluir meu trabalho. Caso ficticio.",
            "O aplicativo e o de pedidos; o relatorio falha ao carregar desde as "
            "09:00, so eu fui afetado e nao consigo concluir meu trabalho.",
        ),
        (
            "critical_incident",
            "Abra um ticket urgente: o sistema de vendas esta indisponivel desde "
            "as 08:00 para centenas de funcionarios, bloqueando toda a operacao. "
            "Caso ficticio de incidente critico.",
            "O sistema e o de vendas, indisponivel desde as 08:00 para centenas "
            "de funcionarios; a operacao inteira esta parada.",
        ),
        (
            "network_wifi",
            "Abra um ticket: o Wi-Fi corporativo esta indisponivel desde as 08:00 "
            "em todo o escritorio, afetando todos os funcionarios e impedindo o "
            "trabalho. Caso ficticio.",
            "E o Wi-Fi corporativo em todo o escritorio, indisponivel desde as "
            "08:00; todos estao impedidos de trabalhar.",
        ),
        (
            "password_reset",
            "Abra um ticket: minha senha corporativa expirou desde as 09:00 e nao "
            "tenho mais acesso ao metodo de verificacao; so eu fui afetado e nao "
            "consigo entrar no sistema. Conta ficticia, sem credenciais.",
            "Minha senha corporativa expirou as 09:00 e nao tenho metodo de "
            "verificacao; somente minha conta esta afetada e nao consigo trabalhar.",
        ),
        (
            "printer_label",
            "Abra um ticket: a impressora principal de etiquetas PRN-01 parou por "
            "atolamento desde as 09:00, afetando toda a expedicao; nao conseguimos "
            "emitir etiquetas. Caso ficticio.",
            "A PRN-01 esta atolada desde as 09:00, toda a expedicao foi afetada e "
            "nao consegue emitir etiquetas.",
        ),
        (
            "unknown",
            "Abra um ticket: meu computador esta com problema desde as 09:00 e nao "
            "consigo trabalhar. Nao sei qual servico esta envolvido. Caso ficticio.",
            "O dispositivo e o notebook corporativo; desde as 09:00 ele nao inicia "
            "o aplicativo de pedidos, somente eu fui afetado e nao consigo trabalhar.",
        ),
    ],
)
def test_live_first_turn_ticket_by_category(
    category: str, request_text: str, clarification: str
) -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    user_id = str(uuid4())
    email = f"qa-chat-{uuid4().hex}@example.test"
    password = secrets.token_urlsafe(24)
    with Session(engine) as db:
        db.add(
            User(
                user_id=user_id,
                email=email,
                display_name="QA Chat",
                role="user",
                password_hash=hasher.hash(password),
                must_change_password=False,
                password_changed_at=utc_now(),
            )
        )
        db.commit()
    try:
        with httpx.Client(
            base_url=os.getenv("LIVE_CHAT_BASE_URL", "http://127.0.0.1:5173"),
            timeout=180,
            headers={"Origin": "http://127.0.0.1:5173"},
        ) as http:
            assert (
                http.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            created = http.post("/api/chat/sessions", json={})
            assert created.status_code == 201
            session_id = created.json()["data"]["session_id"]
            assert (
                http.get(f"/api/chat/sessions/{session_id}").json()["data"]["messages"]
                == []
            )
            outcomes = []
            for message in (request_text, clarification):
                result = http.post(
                    f"/api/chat/sessions/{session_id}/messages",
                    headers={"Idempotency-Key": str(uuid4())},
                    json={"message_text": message},
                )
                body = result.json()
                data = body.get("data") or {}
                outcomes.append(
                    {
                        "status": result.status_code,
                        "run_id": body["meta"]["agent_run_id"],
                        "action": data.get("final_action"),
                        "message": data.get("message_pt_br"),
                        "category": (data.get("triage") or {}).get("internal_category"),
                        "sources": [
                            source["path"] for source in data.get("sources", [])
                        ],
                        "ticket": data.get("ticket"),
                        "error": (body.get("error") or {}).get("code"),
                    }
                )
                if data.get("final_action") != "ask_clarification":
                    break
            print({"case": category, "session_id": session_id, "outcomes": outcomes})
            if category in ("app_access", "applications_issues"):
                if outcomes[0]["action"] == "ask_clarification":
                    assert outcomes[0]["sources"] == []
                    assert outcomes[0]["message"] == (
                        "Qual servico ou equipamento apresenta o problema, o que "
                        "acontece e qual o impacto no seu trabalho?"
                    )
            assert outcomes[-1]["status"] == 200
            assert outcomes[-1]["action"] == "open_ticket"
    finally:
        with Session(engine) as db:
            db.get(User, user_id).is_active = False
            db.commit()
        engine.dispose()


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_CHAT_CASES") != "1", reason="requires live provider and PDI"
)
@pytest.mark.parametrize(
    "category,message,clarification",
    [
        (
            "app_access",
            "Recebo acesso negado ao abrir o aplicativo de pedidos desde as "
            "09:00. O que devo fazer?",
            "O aplicativo de pedidos mostra acesso negado desde as 09:00. So minha "
            "conta e afetada e nao consigo trabalhar.",
        ),
        (
            "applications_issues",
            "Ao consultar o historico de pedidos recebo erro de falha ao carregar "
            "dados. Como posso resolver?",
            "O aplicativo de pedidos falha ao carregar o historico desde as 09:00. "
            "So eu fui afetado e ainda consigo realizar outras tarefas.",
        ),
        (
            "critical_incident",
            "O sistema de vendas esta indisponivel para centenas de usuarios "
            "desde as 08:00. Como proceder?",
            "O sistema de vendas esta indisponivel desde as 08:00 para centenas "
            "de pessoas; a operacao inteira esta parada.",
        ),
        (
            "network_wifi",
            "Meu notebook perdeu conexao com o Wi-Fi corporativo hoje cedo. "
            "O que devo verificar?",
            "Somente meu notebook perdeu a conexao Wi-Fi hoje as 09:00; outros "
            "colegas seguem conectados.",
        ),
        (
            "password_reset",
            "Nao consigo redefinir minha senha corporativa porque ela expirou. "
            "Qual o procedimento?",
            "A senha da minha conta expirou hoje as 09:00. Tenho acesso ao meu "
            "metodo de verificacao e so eu fui afetado.",
        ),
        (
            "printer_label",
            "A impressora de etiquetas PRN-01 nao imprime e parece estar sem "
            "etiquetas. Como resolver?",
            "A PRN-01 nao imprime desde as 09:00 e parece sem etiquetas; somente "
            "este equipamento foi afetado.",
        ),
        (
            "unknown",
            "Meu computador esta com problema, mas nao sei qual servico esta "
            "envolvido. Pode ajudar?",
            "Meu notebook nao inicia o aplicativo de pedidos desde as 09:00; "
            "so eu fui afetado.",
        ),
        (
            "forced_clarification",
            "Estou com um problema no trabalho, mas ainda nao sei dizer qual "
            "servico ou equipamento. Pode me orientar? Caso ficticio.",
            "E minha conta corporativa no aplicativo de pedidos: aparece acesso "
            "negado desde as 09:00, somente eu fui afetado. Como verificar o acesso?",
        ),
    ],
)
def test_live_guidance_by_category(
    category: str, message: str, clarification: str
) -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    user_id = str(uuid4())
    email = f"qa-guidance-{uuid4().hex}@example.test"
    password = secrets.token_urlsafe(24)
    with Session(engine) as db:
        db.add(
            User(
                user_id=user_id,
                email=email,
                display_name="QA Guidance",
                role="user",
                password_hash=hasher.hash(password),
                must_change_password=False,
                password_changed_at=utc_now(),
            )
        )
        db.commit()
    try:
        with httpx.Client(
            base_url=os.getenv("LIVE_CHAT_BASE_URL", "http://127.0.0.1:5173"),
            timeout=180,
            headers={"Origin": "http://127.0.0.1:5173"},
        ) as http:
            assert (
                http.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            created = http.post("/api/chat/sessions", json={})
            assert created.status_code == 201
            session_id = created.json()["data"]["session_id"]
            outcomes = []
            for text in (message, clarification):
                result = http.post(
                    f"/api/chat/sessions/{session_id}/messages",
                    headers={"Idempotency-Key": str(uuid4())},
                    json={"message_text": text},
                )
                body = result.json()
                data = body.get("data") or {}
                outcomes.append(
                    {
                        "status": result.status_code,
                        "run_id": body["meta"]["agent_run_id"],
                        "action": data.get("final_action"),
                        "message": data.get("message_pt_br"),
                        "category": (data.get("triage") or {}).get("internal_category"),
                        "sources": [
                            source["path"] for source in data.get("sources", [])
                        ],
                        "ticket": data.get("ticket"),
                        "error": (body.get("error") or {}).get("code"),
                    }
                )
                if data.get("final_action") != "ask_clarification":
                    break
            print(
                {"guidance": category, "session_id": session_id, "outcomes": outcomes}
            )
            if category == "forced_clarification":
                assert outcomes[0]["action"] == "ask_clarification"
                assert len(outcomes) == 2
                assert outcomes[1]["status"] == 200
                assert outcomes[1]["action"] == "respond"
                assert outcomes[1]["sources"]
                return
            assert outcomes[-1]["status"] == 200
            assert outcomes[-1]["action"] in ("respond", "open_ticket")
    finally:
        with Session(engine) as db:
            db.get(User, user_id).is_active = False
            db.commit()
        engine.dispose()
