"""Durable request intents survive worker death and uncertain provider outcomes."""

from contextlib import contextmanager
from contextvars import ContextVar
import time
from sqlalchemy import select, update
from .db import transaction
from .models import Attempt, Result, Run, UsageEvent, uid

current_job = ContextVar("usage_job", default=None)


@contextmanager
def accounting(job):
    token = current_job.set(job)
    try:
        yield
    finally:
        current_job.reset(token)


def prices(scope, model, config):
    if scope == "generation":
        return config.get("input_cost_per_million"), config.get(
            "output_cost_per_million"
        )
    if scope == "judge":
        return config.get("judge_input_cost_per_million"), config.get(
            "judge_output_cost_per_million"
        )
    if scope == "embedding":
        return config.get("embedding_cost_per_million"), 0
    item = config.get("application_prices", {}).get(model, {})
    return item.get("input_cost_per_million"), item.get("output_cost_per_million")


def begin(scope, model, config, source="provider", parent_id=None, rates=None):
    job = current_job.get()
    if not job:
        return None
    identity = uid()
    input_rate, output_rate = rates or prices(scope, model, config)
    with transaction() as session:
        session.add(
            UsageEvent(
                id=identity,
                project_id=job["project_id"],
                run_id=job["run_id"],
                attempt_id=job["attempt_id"],
                parent_id=parent_id,
                scope=scope,
                model=model,
                source=source,
                input_rate=input_rate,
                output_rate=output_rate,
            )
        )
    return identity


def finish(
    identity,
    state,
    input_tokens=None,
    output_tokens=None,
    request_id=None,
    error=None,
    billable=True,
):
    if not identity:
        return
    with transaction() as session:
        event = session.scalar(
            select(UsageEvent).where(UsageEvent.id == identity).with_for_update()
        )
        if not event or event.state not in {"STARTED", "UNCERTAIN"}:
            return
        event.state, event.input_tokens, event.output_tokens = (
            state,
            input_tokens,
            output_tokens,
        )
        event.finished_at, event.error, event.billable = time.time(), error, billable
        event.request_id = request_id[:200] if isinstance(request_id, str) else None
        if not billable:
            event.estimated_cost = 0
        elif (
            input_tokens is not None
            and output_tokens is not None
            and event.input_rate is not None
            and event.output_rate is not None
        ):
            event.estimated_cost = (
                input_tokens * event.input_rate + output_tokens * event.output_rate
            ) / 1_000_000


def uncertain_attempt(session, attempt_id, category="lease_expired"):
    session.execute(
        update(UsageEvent)
        .where(UsageEvent.attempt_id == attempt_id, UsageEvent.state == "STARTED")
        .values(state="UNCERTAIN", error=category, finished_at=time.time())
    )


def summary(session, run_ids):
    events = session.scalars(
        select(UsageEvent).where(UsageEvent.run_id.in_(run_ids))
    ).all()
    by_scope = {}
    for event in events:
        item = by_scope.setdefault(
            event.scope,
            {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "known_cost": 0.0,
                "uncertain_calls": 0,
                "unpriced_calls": 0,
            },
        )
        item["calls"] += 1
        item["input_tokens"] += event.input_tokens or 0
        item["output_tokens"] += event.output_tokens or 0
        item["known_cost"] += event.estimated_cost or 0
        item["uncertain_calls"] += event.billable and event.state in {
            "STARTED",
            "UNCERTAIN",
            "UNREPORTED",
        }
        item["unpriced_calls"] += (
            event.billable
            and event.state == "REPORTED"
            and event.estimated_cost is None
        )
    tracked_results = select(Attempt.result_id).join(
        UsageEvent, UsageEvent.attempt_id == Attempt.id
    )
    legacy_pairs = session.execute(
        select(Result, Run.config)
        .join(Run, Run.id == Result.run_id)
        .where(
            Result.run_id.in_(run_ids),
            Result.attempts > 0,
            Result.id.not_in(tracked_results),
        )
    ).all()
    # Completed pre-ledger data keeps its old generation estimate; completeness is unknown.
    legacy = [
        r
        for r, config in legacy_pairs
        if config.get("accounting_version") != "ledger-v1"
    ]
    unknown = sum(
        v["uncertain_calls"] + v["unpriced_calls"] for v in by_scope.values()
    ) + len(legacy)
    return {
        "calls": len(events),
        "by_scope": by_scope,
        "known_cost": sum(e.estimated_cost or 0 for e in events)
        + sum(r.cost for r in legacy),
        "input_tokens": sum(e.input_tokens or 0 for e in events)
        + sum(r.input_tokens for r in legacy),
        "output_tokens": sum(e.output_tokens or 0 for e in events)
        + sum(r.output_tokens for r in legacy),
        "uncertain_calls": sum(v["uncertain_calls"] for v in by_scope.values()),
        "unpriced_calls": sum(v["unpriced_calls"] for v in by_scope.values()),
        "legacy_results": len(legacy),
        "complete": unknown == 0,
        "note": "Known cost is a lower bound when calls are pending, uncertain, unreported, unpriced, or predate the ledger. Estimates are not provider invoices.",
    }
