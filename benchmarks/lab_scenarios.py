"""Runs inside the disposable Compose laboratory."""

import argparse
import json
import time
import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from backend.app.db import Base, engine, transaction
from backend.app.models import (
    Attempt,
    Dataset,
    Experiment,
    Project,
    PromptVersion,
    Result,
    Run,
    UsageEvent,
    uid,
)
from backend.app.schemas import CaseInput, RunConfig
from backend.app.seed import DEFAULT_PROJECT
from backend.app.services import create_version, start_run
from backend.app.usage import summary


def initialize():
    Base.metadata.create_all(engine)
    with transaction() as session:
        if not session.get(Project, DEFAULT_PROJECT):
            session.add(
                Project(id=DEFAULT_PROJECT, name="Disposable failure laboratory")
            )


def run(scenario, processes):
    count = 100 if scenario == "throughput" else 30
    with transaction() as session:
        dataset = Dataset(id=uid(), project_id=DEFAULT_PROJECT, name=scenario)
        prompt = PromptVersion(
            id=uid(), project_id=DEFAULT_PROJECT, name="lab", template="{input}"
        )
        session.add_all([dataset, prompt])
        session.flush()
        version = create_version(
            session,
            dataset,
            [
                CaseInput(
                    case_id=f"lab-{i}",
                    input=f"Question {i}",
                    reference_answer=f"Answer {i}",
                )
                for i in range(count)
            ],
        )
        config = RunConfig(
            dataset_version_id=version.id,
            prompt_version_id=prompt.id,
            model="lab-model" if scenario == "redis-outage" else "mock-precise",
            provider="openai_compatible" if scenario == "redis-outage" else "mock",
            mock_latency_ms=80 if scenario == "throughput" else 1500,
            concurrency=32,
            max_attempts=5,
            timeout_seconds=20,
            input_cost_per_million=0,
            output_cost_per_million=0,
        ).model_dump()
        experiment = Experiment(
            id=uid(), project_id=DEFAULT_PROJECT, name=scenario, config=config
        )
        session.add(experiment)
        session.flush()
        run_id = start_run(session, experiment).id
    started = time.monotonic()
    announced = False
    peak = 0
    while time.monotonic() - started < 100:
        try:
            with transaction() as session:
                record = session.get(Run, run_id)
                results = session.scalars(
                    select(Result).where(Result.run_id == run_id)
                ).all()
                active = sum(r.status == "RUNNING" for r in results)
                peak = max(peak, active)
                if active and not announced:
                    print("READY " + run_id, flush=True)
                    announced = True
                if record.status in {"COMPLETED", "FAILED", "PARTIAL", "CANCELED"}:
                    if record.status == "CANCELED":
                        # Allow already-accepted inference to return; late writes must stay fenced.
                        time.sleep(2)
                        session.expire_all()
                        results = session.scalars(
                            select(Result).where(Result.run_id == run_id)
                        ).all()
                    attempts = session.scalars(
                        select(Attempt)
                        .join(Result, Result.id == Attempt.result_id)
                        .where(Result.run_id == run_id)
                    ).all()
                    report = {
                        "scenario": scenario,
                        "processes": processes,
                        "slots_per_process": 5,
                        "lease_seconds": 5,
                        "cases": count,
                        "status": record.status,
                        "completed": sum(r.status == "COMPLETED" for r in results),
                        "canceled": sum(r.status == "CANCELED" for r in results),
                        "failed": sum(r.status == "FAILED" for r in results),
                        "duplicate_logical_results": len(results)
                        - len({r.test_case_id for r in results}),
                        "wall_seconds": time.monotonic() - started,
                        "peak_claimed_cases": peak,
                        "attempts": len(attempts),
                        "abandoned_attempts": sum(
                            a.status == "ABANDONED" for a in attempts
                        ),
                        "trace_references": sum(
                            a.trace_id is not None for a in attempts
                        ),
                        "usage": summary(session, [run_id]),
                    }
                    assert report["duplicate_logical_results"] == 0
                    if scenario == "cancel-in-flight":
                        assert (
                            report["canceled"] > 0
                            and report["completed"] + report["canceled"] == count
                        )
                    else:
                        assert (
                            report["status"] == "COMPLETED"
                            and report["completed"] == count
                        ), report
                    print("REPORT " + json.dumps(report), flush=True)
                    return
        except SQLAlchemyError:
            engine.dispose()
        time.sleep(0.1)
    raise RuntimeError(f"{scenario} did not recover in 100 seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--scenario", default="throughput")
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "cancel":
        response = httpx.post(
            f"http://api:8000/api/v1/runs/{args.run_id}/cancel", json={}
        )
        response.raise_for_status()
    else:
        run(args.scenario, args.processes)
