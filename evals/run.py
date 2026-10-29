"""Offline contract evaluation and optional grading of observed provider turns."""

import argparse
import importlib
import json
import math
import os
import secrets
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

from evals.checks import grade_case

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(__file__).resolve().parent / "dataset"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def evaluate(observations: dict[str, dict]) -> dict:
    cases = [
        case for path in sorted(DATASET.glob("*.jsonl")) for case in load_jsonl(path)
    ]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate dataset IDs")
    if set(observations) - set(ids):
        raise ValueError("Unknown observation IDs")
    categories: dict[str, list[dict]] = defaultdict(list)
    latencies: list[float] = []
    for case in cases:
        observed = observations.get(case["id"], {})
        grades = grade_case(case, observed)
        categories[case["category"]].append(grades)
        if grades["latency"] is True:
            latencies.append(observed["latency_ms"])
    breakdown = {
        name: {
            dimension: dict(
                Counter(
                    "unmeasured"
                    if value is None
                    else "not_applicable"
                    if value == "n/a"
                    else "pass"
                    if value
                    else "fail"
                    for value in (grade[dimension] for grade in grades)
                )
            )
            for dimension in (
                "accuracy",
                "safety",
                "security",
                "ticket",
                "source",
                "latency",
                "cost",
            )
        }
        for name, grades in sorted(categories.items())
    }
    p95 = sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1] if latencies else None
    dimensions = ("accuracy", "safety", "security", "ticket", "source", "cost")
    gates = {}
    for dimension in dimensions:
        counts = Counter(
            value
            for category in breakdown.values()
            for value, count in category[dimension].items()
            for _ in range(count)
        )
        gates[dimension] = (
            "fail"
            if counts["fail"]
            else "unmeasured"
            if counts["unmeasured"] or not counts["pass"]
            else "pass"
        )
    gates["latency"] = (
        "unmeasured"
        if len(latencies) != len(cases)
        else "pass"
        if p95 <= 30000
        else "fail"
    )
    return {
        "total_cases": len(cases),
        "categories": breakdown,
        "latency_p95_ms": p95,
        "latency_p95_pass": p95 <= 30000 if len(latencies) == len(cases) else None,
        "latency_samples": len(latencies),
        "gates": gates,
    }


def run_live(base_url: str, output: Path | None = None) -> list[dict]:
    import httpx
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    load_dotenv(ROOT / ".env")
    if os.getenv("TICKET_ADAPTER_MODE") != "servicenow":
        raise RuntimeError("Live evaluation requires TICKET_ADAPTER_MODE=servicenow")
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("Live evaluation requires DATABASE_URL")
    if not base_url.startswith("http://127.0.0.1:"):
        raise RuntimeError("Live evaluation only accepts a local HTTP API")
    sys.path.insert(0, str(ROOT / "src/backend"))
    hasher = importlib.import_module("app.auth").hasher
    price = importlib.import_module("app.ia_tab").price
    models = importlib.import_module("app.persistence.models")
    AgentEvent, AgentRunTelemetry, Ticket, User, utc_now = (
        models.AgentEvent,
        models.AgentRunTelemetry,
        models.Ticket,
        models.User,
        models.utc_now,
    )

    cases = [
        case for path in sorted(DATASET.glob("*.jsonl")) for case in load_jsonl(path)
    ]
    markers = {marker for case in cases for marker in case.get("sentinels", [])}
    engine = create_engine(
        os.environ["DATABASE_URL"], connect_args={"connect_timeout": 5}
    )
    user_id, email, password = (
        str(uuid4()),
        f"eval-{uuid4().hex}@example.test",
        secrets.token_urlsafe(24),
    )
    observations = []
    try:
        with httpx.Client(
            base_url=base_url, timeout=180, headers={"Origin": "http://127.0.0.1:5173"}
        ) as http:
            if http.get("/health").status_code != 200:
                raise RuntimeError("Local API is not healthy")
            with Session(engine) as db:
                db.add(
                    User(
                        user_id=user_id,
                        email=email,
                        display_name="Eval Synthetic",
                        role="user",
                        password_hash=hasher.hash(password),
                        must_change_password=False,
                        password_changed_at=utc_now(),
                    )
                )
                db.commit()
            if (
                http.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                != 200
            ):
                raise RuntimeError("Synthetic user login failed")
            for case in cases:
                session = http.post("/api/chat/sessions", json={})
                if session.status_code != 201:
                    raise RuntimeError(f"Session creation failed for {case['id']}")
                session_id = session.json()["data"]["session_id"]
                started = time.monotonic()
                try:
                    response = http.post(
                        f"/api/chat/sessions/{session_id}/messages",
                        headers={"Idempotency-Key": str(uuid4())},
                        json={"message_text": case["input"]},
                    )
                except httpx.RequestError as exc:
                    raise RuntimeError(
                        f"Submission outcome unknown for {case['id']}; stop without retry"
                    ) from exc
                elapsed = round((time.monotonic() - started) * 1000, 2)
                body = response.json()
                turn = body.get("data") if response.status_code == 200 else None
                run_id = (body.get("meta") or {}).get("agent_run_id")
                row = {
                    "id": case["id"],
                    "session_id": session_id,
                    "run_id": run_id,
                    "http_status": response.status_code,
                    "error_code": (body.get("error") or {}).get("code"),
                    "latency_ms": elapsed,
                }
                if turn:
                    triage = turn.get("triage") or {}
                    row["turn"] = {
                        "final_action": turn.get("final_action"),
                        "triage": {
                            field: triage.get(field)
                            for field in ("internal_category", "impact", "urgency")
                        },
                        "sources": [
                            {
                                "title": source.get("title"),
                                "path": source.get("path"),
                                "snippet": bool(source.get("snippet")),
                            }
                            for source in turn.get("sources", [])
                        ],
                        "ticket": {
                            "status": turn["ticket"]["status"],
                            "adapter_mode": turn["ticket"]["adapter_mode"],
                        }
                        if turn.get("ticket")
                        else None,
                    }
                leaked = any(
                    marker in json.dumps(body, ensure_ascii=False) for marker in markers
                )
                with Session(engine) as db:
                    if run_id:
                        telemetry = db.scalars(
                            select(AgentRunTelemetry).where(
                                AgentRunTelemetry.agent_run_id == run_id
                            )
                        ).all()
                        costs = [price(db, step)[0] for step in telemetry]
                        if telemetry and all(cost is not None for cost in costs):
                            row["estimated_cost_usd"] = float(sum(costs))
                        events = db.scalars(
                            select(AgentEvent).where(AgentEvent.agent_run_id == run_id)
                        ).all()
                        leaked = leaked or any(
                            marker
                            in json.dumps(event.payload_redacted, ensure_ascii=False)
                            or marker
                            in json.dumps(
                                event.validation_errors_redacted, ensure_ascii=False
                            )
                            for event in events
                            for marker in markers
                        )
                        ticket = db.scalar(
                            select(Ticket).where(Ticket.agent_run_id == run_id)
                        )
                        if ticket and turn and ticket.adapter_mode == "servicenow":
                            row["outbound_payload"] = {
                                field: bool(ticket.redacted_payload.get(field))
                                for field in (
                                    "short_description",
                                    "description",
                                    "impact",
                                    "urgency",
                                    "category",
                                )
                            }
                row["redacted_trace"] = "EVAL_SECRET_LEAK" if leaked else ""
                observations.append(row)
                if output:
                    with output.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(
                    f"{case['id']}: HTTP {response.status_code}, action={row.get('turn', {}).get('final_action')}, latency_ms={elapsed}",
                    file=sys.stderr,
                )
                if row["error_code"] == "TICKET_OUTCOME_UNKNOWN":
                    raise RuntimeError(
                        f"Ticket outcome unknown for {case['id']}; stop without retry"
                    )
    finally:
        with Session(engine) as db:
            user = db.get(User, user_id)
            if user:
                user.is_active = False
                db.commit()
        engine.dispose()
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observations",
        type=Path,
        help="JSONL with id, turn, latency_ms, estimated_cost_usd, redacted_trace and optional outbound_payload",
    )
    parser.add_argument(
        "--contract",
        action="store_true",
        help="Run the existing injected HTTP contract tests (no provider or remote POST)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run golden cases through the real local API and provider",
    )
    parser.add_argument(
        "--allow-pdi-post",
        action="store_true",
        help="Explicitly permit real incident creation during --live",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output", type=Path, help="Write redacted live observations as JSONL"
    )
    args = parser.parse_args()
    if args.live and not args.allow_pdi_post:
        parser.error("--live requires --allow-pdi-post (real incidents may be created)")
    if args.live and args.observations:
        parser.error("--live and --observations are mutually exclusive")
    if args.output and not args.live:
        parser.error("--output requires --live")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            parser.error("--output must not already exist")
    observations = (
        run_live(args.base_url, args.output)
        if args.live
        else load_jsonl(args.observations)
        if args.observations
        else []
    )
    if any(not isinstance(row, dict) or "id" not in row for row in observations):
        parser.error("Each observation needs an id")
    if len({row["id"] for row in observations}) != len(observations):
        parser.error("Duplicate observation IDs")
    result = evaluate({row["id"]: row for row in observations})
    if args.contract:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py",
            "-q",
            "-k",
            "test_dataset_",
            "--disable-warnings",
        ]
        run = subprocess.run(command, cwd=ROOT / "src/backend", check=False)
        result["injected_http_contract"] = "pass" if run.returncode == 0 else "fail"
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return (
        1
        if result.get("injected_http_contract") == "fail"
        or "fail" in result["gates"].values()
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
