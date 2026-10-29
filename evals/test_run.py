"""Regression checks for evaluation gating and golden-set integrity."""

import json
import subprocess
import sys
from pathlib import Path

from evals.checks import grade_case
from evals.run import DATASET, evaluate


def test_existing_golden_cases_match_prd_cases():
    original = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "project-context/1.define/support-cases.json"
        ).read_text(encoding="utf-8")
    )
    dataset = {
        case["id"]: case
        for path in DATASET.glob("*.jsonl")
        for case in (
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        )
    }
    for case in original:
        actual = dataset[case["id"]]
        for field in (
            "input",
            "expected_action",
            "expected_category",
            "expected_source",
            "expected_impact",
            "expected_urgency",
        ):
            if field in case:
                assert actual[field] == case[field]


def test_missing_observations_do_not_pass_gates():
    result = evaluate({})
    assert result["total_cases"] == 17
    assert all(value == "unmeasured" for value in result["gates"].values())
    assert result["latency_samples"] == 0


def test_sentinel_leak_fails_security_and_blocked_ticket():
    case = {"expected_action": "blocked", "expected_category": None}
    observation = {
        "turn": {"final_action": "blocked", "ticket": {"status": "created"}},
        "redacted_trace": "EVAL_SECRET_TESTE",
    }
    grades = grade_case(case, observation)
    assert grades["accuracy"] is True
    assert grades["security"] is False
    assert grades["safety"] is False


def test_unmeasured_cost_and_ticket_payload_are_not_passes():
    case = {"expected_action": "open_ticket", "expected_category": "app_access"}
    grades = grade_case(
        case,
        {
            "turn": {
                "final_action": "open_ticket",
                "triage": {"internal_category": "app_access"},
                "ticket": {"status": "created"},
            }
        },
    )
    assert grades["ticket"] is None
    assert grades["cost"] is None
    assert grade_case(case, {"turn": {}, "estimated_cost_usd": 0.03})["cost"] is False


def test_empty_trace_without_sentinel_is_unmeasured():
    case = {"expected_action": "respond", "expected_category": "password_reset"}
    assert grade_case(case, {"turn": {}, "redacted_trace": ""})["security"] is None
    assert (
        grade_case(
            {**case, "sentinels": ["EVAL_PII_TESTE"]},
            {"turn": {}, "redacted_trace": ""},
        )["security"]
        is True
    )


def test_applicability_and_p95_gate():
    cases = {
        json.loads(line)["id"]: json.loads(line)
        for path in DATASET.glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    }
    observations = {
        case_id: {
            "turn": {
                "final_action": case["expected_action"],
                "triage": {"internal_category": case["expected_category"]},
                "ticket": None,
                "sources": [],
            },
            "latency_ms": 30001,
        }
        for case_id, case in cases.items()
    }
    assert grade_case(cases["TC001"], observations["TC001"])["ticket"] == "n/a"
    result = evaluate(observations)
    assert result["latency_p95_ms"] == 30001
    assert result["gates"]["latency"] == "fail"


def test_source_basename_and_independent_request_metrics():
    case = {"expected_action": "respond", "expected_source": "password_reset.md"}
    assert (
        grade_case(
            case,
            {
                "turn": {
                    "final_action": "respond",
                    "sources": [
                        {
                            "title": "Senha",
                            "path": "password_reset.md",
                            "snippet": "Passos",
                        }
                    ],
                }
            },
        )["source"]
        is True
    )
    grades = grade_case(case, {"latency_ms": 1200, "estimated_cost_usd": 0.01})
    assert grades["accuracy"] is None
    assert grades["latency"] is True
    assert grades["cost"] is True
    assert grade_case(case, {"redacted_trace": "EVAL_PII_TESTE"})["security"] is False


def test_live_requires_explicit_pdi_authorization():
    command = subprocess.run(
        [sys.executable, "-m", "evals.run", "--live"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert command.returncode != 0
    assert "--live requires --allow-pdi-post" in command.stderr
