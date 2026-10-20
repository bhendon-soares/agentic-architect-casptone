"""Local-only IA reporting over trusted stage measurements."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.database import get_session
from app.persistence.models import (
    AgentRun,
    AgentRunAttempt,
    AgentRunTelemetry,
    PricingConfigVersion,
)

router = APIRouter(prefix="/api/ia-tab")
RESULTS = (
    "respond",
    "open_ticket",
    "blocked",
    "ask_clarification",
    "failed",
    "running",
)
STEPS = ("triage", "knowledge", "response", "policy", "ticketing")


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (
        value.replace(tzinfo=timezone.utc).isoformat()
        if value.tzinfo is None
        else value.astimezone(timezone.utc).isoformat()
    )


def aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def filters(
    start: datetime | None = None,
    end: datetime | None = None,
    model: str | None = None,
    step: str | None = None,
    result: str | None = None,
) -> dict:
    if (
        (start and start.utcoffset() is None)
        or (end and end.utcoffset() is None)
        or (start and end and start >= end)
        or (step and step not in STEPS)
        or (result and result not in RESULTS)
    ):
        raise HTTPException(422, "INVALID_REQUEST")
    return {"start": start, "end": end, "model": model, "step": step, "result": result}


def outcome(run: AgentRun) -> str:
    if run.status == "running":
        return "running"
    if run.status != "completed":
        return "failed"
    return run.final_action if run.final_action in RESULTS else "failed"


def selected(
    db: Session, criteria: dict
) -> tuple[list[AgentRun], list[AgentRunTelemetry]]:
    stmt = select(AgentRun)
    if criteria["start"]:
        stmt = stmt.where(AgentRun.started_at >= criteria["start"])
    if criteria["end"]:
        stmt = stmt.where(AgentRun.started_at < criteria["end"])
    runs = [
        run
        for run in db.scalars(stmt).all()
        if not criteria["result"] or outcome(run) == criteria["result"]
    ]
    if not runs:
        return [], []
    rows = db.scalars(
        select(AgentRunTelemetry).where(
            AgentRunTelemetry.agent_run_id.in_([run.agent_run_id for run in runs])
        )
    ).all()
    rows = [
        row
        for row in rows
        if (not criteria["step"] or row.step_name == criteria["step"])
        and (not criteria["model"] or row.model_used == criteria["model"])
    ]
    if criteria["step"] or criteria["model"]:
        ids = {row.agent_run_id for row in rows}
        runs = [run for run in runs if run.agent_run_id in ids]
    return runs, rows


def price(
    db: Session, row: AgentRunTelemetry
) -> tuple[Decimal | None, list[PricingConfigVersion]]:
    if (
        not row.model_used
        or not row.deployment_id
        or row.tokens_input is None
        or row.tokens_output is None
        or row.tokens_cache is None
        or row.cache_in_input is None
        or row.state != "complete"
        or row.tokens_cache > row.tokens_input
        or min(row.tokens_input, row.tokens_output, row.tokens_cache) < 0
    ):
        return None, []
    configs = db.scalars(
        select(PricingConfigVersion).where(
            PricingConfigVersion.model == row.model_used,
            PricingConfigVersion.deployment_id == row.deployment_id,
            PricingConfigVersion.currency == "USD",
            PricingConfigVersion.active.is_(True),
        )
    ).all()
    when = aware(row.timestamp_start)
    applicable = [
        item
        for item in configs
        if aware(item.valid_from) <= when
        and (item.valid_until is None or when < aware(item.valid_until))
    ]
    by_type = defaultdict(list)
    for item in applicable:
        by_type[item.token_type].append(item)
    required = ("input", "output", "cache") if row.tokens_cache else ("input", "output")
    if any(len(by_type[kind]) != 1 for kind in required):
        return None, []
    if row.tokens_cache and not row.cache_in_input:
        return None, []
    tokens = {
        "input": row.tokens_input - row.tokens_cache,
        "output": row.tokens_output,
        "cache": row.tokens_cache,
    }
    chosen = [by_type[kind][0] for kind in required]
    return sum(
        (
            Decimal(tokens[item.token_type])
            * item.rate_per_million
            / Decimal(1_000_000)
            for item in chosen
        ),
        Decimal(0),
    ), chosen


def detail(
    db: Session,
    run: AgentRun,
    row: AgentRunTelemetry | None,
    attempts: list[AgentRunAttempt],
) -> dict:
    cost, configs = price(db, row) if row else (None, [])
    relevant = [
        item
        for item in attempts
        if item.agent_run_id == run.agent_run_id
        and (row is None or item.step_index in (None, row.step_index))
    ]
    observed = [item for item in relevant if item.attempt_type == "provider"]
    return {
        "agent_run_id": run.agent_run_id,
        "session_id": run.session_id,
        "original_run_id": run.original_run_id,
        "result": outcome(run),
        "step_index": row.step_index if row else None,
        "step_name": row.step_name if row else None,
        "model_used": row.model_used if row else None,
        "deployment_id": row.deployment_id if row else None,
        "start_time": iso(row.timestamp_start) if row else None,
        "end_time": iso(row.timestamp_end) if row else None,
        "duration_ms": row.duration_ms if row and row.state != "running" else None,
        "tokens_input": row.tokens_input if row else None,
        "tokens_output": row.tokens_output if row else None,
        "tokens_cache": row.tokens_cache if row else None,
        "estimated_cost_value": float(cost) if cost is not None else None,
        "estimated_cost_currency": "USD" if cost is not None else None,
        "estimated_cost_validity_start": iso(max(item.valid_from for item in configs))
        if configs
        else None,
        "estimated_cost_validity_end": iso(
            min(
                (item.valid_until for item in configs if item.valid_until), default=None
            )
        )
        if configs
        else None,
        "pricing_config_ids": [item.pricing_config_id for item in configs],
        "attempt_count": len(observed) if observed else None,
        "retry_count": sum(
            item.attempt_type == "operational_retry" for item in relevant
        ),
        "replay_count": sum(item.attempt_type == "replay" for item in relevant),
        "state": row.state
        if row
        else (
            "running"
            if run.status == "running"
            else "failed"
            if outcome(run) == "failed"
            else "complete"
        ),
    }


def records(db: Session, criteria: dict) -> tuple[list[AgentRun], list[dict]]:
    runs, rows = selected(db, criteria)
    by_run = defaultdict(list)
    for row in rows:
        by_run[row.agent_run_id].append(row)
    if not runs:
        return [], []
    attempts = db.scalars(
        select(AgentRunAttempt).where(
            AgentRunAttempt.agent_run_id.in_([run.agent_run_id for run in runs])
        )
    ).all()
    items = [
        detail(db, run, row, attempts)
        for run in runs
        for row in (
            by_run[run.agent_run_id]
            or ([None] if not criteria["step"] and not criteria["model"] else [])
        )
    ]
    return runs, items


def stats(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "sample_size": len(ordered),
        "average_ms": sum(ordered) / len(ordered) if ordered else None,
        "max_ms": ordered[-1] if ordered else None,
        "p95_ms": ordered[ceil(0.95 * len(ordered)) - 1] if ordered else None,
        "p95_method": "nearest-rank",
    }


@router.get("/summary")
def summary(
    request: Request,
    criteria: dict = Depends(filters),
    db: Session = Depends(get_session),
) -> dict:
    from app.main import envelope

    runs, items = records(db, criteria)
    counts = Counter(outcome(run) for run in runs)
    denominator = sum(counts[name] for name in RESULTS[:3])
    measured = [
        item["duration_ms"] for item in items if item["duration_ms"] is not None
    ]
    costs = [
        item["estimated_cost_value"]
        for item in items
        if item["estimated_cost_value"] is not None
    ]
    stage_items = [item for item in items if item["step_name"] is not None]
    complete_cost_coverage = (
        bool(stage_items)
        and len(costs) == len(stage_items)
        and len({item["agent_run_id"] for item in stage_items}) == len(runs)
    )
    return envelope(
        {
            "total_runs": len(runs),
            "telemetry_rows": len(stage_items),
            "results": {
                name: {
                    "count": counts[name],
                    "percentage": 100 * counts[name] / denominator
                    if denominator
                    else None,
                }
                if name in RESULTS[:3]
                else {"count": counts[name], "percentage": None}
                for name in RESULTS
            },
            "terminal_denominator": denominator,
            "duration": stats(measured),
            "estimated_cost_value": sum(costs) if complete_cost_coverage else None,
            "estimated_cost_currency": "USD" if complete_cost_coverage else None,
            "cost_sample_size": len(costs),
            "cost_required_rows": len(stage_items),
            "period": {"start": iso(criteria["start"]), "end": iso(criteria["end"])},
            "duration_unit": "ms",
        },
        request,
    )


@router.get("/details")
def details(
    request: Request,
    criteria: dict = Depends(filters),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
) -> dict:
    from app.main import envelope

    runs, items = records(db, criteria)
    order = {run.agent_run_id: run.started_at for run in runs}
    items.sort(
        key=lambda item: (
            order[item["agent_run_id"]],
            item["agent_run_id"],
            item["step_index"] or -1,
        ),
        reverse=True,
    )
    return envelope(
        {"items": items[offset : offset + limit], "total": len(items)},
        request,
        limit=limit,
        offset=offset,
    )


@router.get("/timeseries")
def timeseries(
    request: Request,
    criteria: dict = Depends(filters),
    db: Session = Depends(get_session),
) -> dict:
    from app.main import envelope

    runs, items = records(db, criteria)
    days = defaultdict(Counter)
    for run in runs:
        days[aware(run.started_at).date().isoformat()][outcome(run)] += 1
    stages = {
        step: stats(
            [
                item["duration_ms"]
                for item in items
                if item["step_name"] == step and item["duration_ms"] is not None
            ]
        )
        for step in STEPS
    }
    return envelope(
        {
            "granularity": "day",
            "days": [
                {"date": day, "results": {name: counts[name] for name in RESULTS}}
                for day, counts in sorted(days.items())
            ],
            "states": {
                name: sum(outcome(run) == name for run in runs) for name in RESULTS
            },
            "stage_latency": stages,
            "duration_unit": "ms",
            "period": {"start": iso(criteria["start"]), "end": iso(criteria["end"])},
        },
        request,
    )


@router.get("/pricing-config")
def pricing_config(request: Request, db: Session = Depends(get_session)) -> dict:
    from app.main import envelope

    rows = db.scalars(
        select(PricingConfigVersion)
        .where(PricingConfigVersion.active.is_(True))
        .order_by(
            PricingConfigVersion.model,
            PricingConfigVersion.deployment_id,
            PricingConfigVersion.token_type,
            PricingConfigVersion.valid_from,
        )
    ).all()
    return envelope(
        {
            "items": [
                {
                    "pricing_config_id": row.pricing_config_id,
                    "model": row.model,
                    "deployment_id": row.deployment_id,
                    "currency": row.currency,
                    "token_type": row.token_type,
                    "rate_per_million": float(row.rate_per_million),
                    "valid_from": iso(row.valid_from),
                    "valid_until": iso(row.valid_until),
                }
                for row in rows
            ]
        },
        request,
    )
