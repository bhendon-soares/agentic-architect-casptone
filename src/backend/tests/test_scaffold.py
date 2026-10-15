"""Checks limited to the importable scaffold, not application behavior."""

from crewai import Process
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.crew import (
    AGENTS_CONFIG,
    ALLOW_DELEGATION,
    MAX_ITER,
    MEMORY_ENABLED,
    PROCESS,
    TASKS_CONFIG,
)


def test_entry_points_and_health() -> None:
    assert isinstance(app, FastAPI)
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}
    assert response.json()["error"] is None
    assert PROCESS is Process.sequential
    assert AGENTS_CONFIG.is_file()
    assert TASKS_CONFIG.is_file()
    assert ALLOW_DELEGATION is False
    assert MEMORY_ENABLED is False
    assert MAX_ITER <= 12
