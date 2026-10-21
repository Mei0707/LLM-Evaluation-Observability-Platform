"""Measure the real database-backed pipeline in an isolated temporary database."""

import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import statistics
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--latency-ms", type=float, default=5)
    parser.add_argument("--output", default="benchmarks/results/latest.json")
    args = parser.parse_args()
    if any(n < 1 or n > 5000 for n in args.sizes) or any(
        n < 1 or n > 32 for n in args.concurrency
    ):
        parser.error("sizes: 1..5000; concurrency: 1..32")
    with tempfile.TemporaryDirectory(prefix="evalscope-benchmark-") as directory:
        os.environ["DATABASE_URL"] = "sqlite:///" + str(
            Path(directory) / "benchmark.db"
        )
        os.environ["REDIS_URL"] = ""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        from sqlalchemy import func, select
        from backend.app.config import settings
        from backend.app.db import Base, engine, transaction
        from backend.app.models import (
            Attempt,
            Dataset,
            Experiment,
            Project,
            PromptVersion,
            Result,
            Run,
            uid,
        )
        from backend.app.schemas import CaseInput, RunConfig
        from backend.app.services import aggregate, create_version, start_run
        from backend.app.worker import claim, execute
        from backend.app.providers import Provider, ProviderLimiter
        from backend.app.seed import DEFAULT_PROJECT

        async def experiment(size, concurrency):
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
            with transaction() as session:
                session.add(Project(id=DEFAULT_PROJECT, name="Benchmark"))
                session.flush()
                dataset = Dataset(
                    id=uid(), project_id=DEFAULT_PROJECT, name="Synthetic benchmark"
                )
                prompt = PromptVersion(
                    id=uid(),
                    project_id=DEFAULT_PROJECT,
                    name="Benchmark prompt",
                    template="{input}",
                )
                session.add_all([dataset, prompt])
                session.flush()
                version = create_version(
                    session,
                    dataset,
                    [
                        CaseInput(
                            case_id=f"bench-{i}",
                            input=f"Question {i}",
                            reference_answer=f"Answer {i}",
                        )
                        for i in range(size)
                    ],
                )
                config = RunConfig(
                    dataset_version_id=version.id,
                    prompt_version_id=prompt.id,
                    concurrency=concurrency,
                    model="mock-precise",
                    mock_latency_ms=args.latency_ms,
                ).model_dump()
                experiment = Experiment(
                    id=uid(),
                    project_id=DEFAULT_PROJECT,
                    name="Benchmark",
                    config=config,
                )
                session.add(experiment)
                session.flush()
                run = start_run(session, experiment)
                run_id = run.id
            provider = Provider(ProviderLimiter())
            pending, completed = set(), 0
            start = time.perf_counter()
            try:
                while completed < size:
                    while len(pending) < concurrency:
                        job = claim()
                        if not job:
                            break
                        pending.add(asyncio.create_task(execute(job, provider)))
                    if not pending:
                        raise RuntimeError(
                            "Pipeline stopped before completing all cases"
                        )
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
                    completed += len(done)
            finally:
                await provider.close()
            elapsed = time.perf_counter() - start
            with transaction() as session:
                results = session.scalars(
                    select(Result).where(Result.run_id == run_id)
                ).all()
                metrics = aggregate(results)
                logical_count = len({r.test_case_id for r in results})
                waits = session.execute(
                    select(Attempt.created_at, Run.created_at)
                    .join(Result, Attempt.result_id == Result.id)
                    .join(Run, Result.run_id == Run.id)
                ).all()
                return {
                    "cases": size,
                    "concurrency": concurrency,
                    "processes": 1,
                    "controlled_mock_latency_ms": args.latency_ms,
                    "wall_seconds": elapsed,
                    "cases_per_second": size / elapsed,
                    "duplicate_logical_results": len(results) - logical_count,
                    "persistence_coverage": metrics["coverage"],
                    "queue_wait_mean_ms": statistics.mean(
                        (a - b) * 1000 for a, b in waits
                    ),
                    "metrics": metrics,
                }

        report = {
            "environment": {
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "os": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
                "python": platform.python_version(),
                "database": "SQLite WAL on local filesystem",
                "notes": "One asyncio worker process; concurrency means in-flight cases, not worker processes. No external LLM calls. Includes database orchestration, scoring, and local OTel span recording; excludes dataset creation and network export.",
            },
            "measurements": [],
        }
        for size in args.sizes:
            for concurrency in args.concurrency:
                measurement = asyncio.run(experiment(size, concurrency))
                report["measurements"].append(measurement)
                print(
                    f"{size} cases / {concurrency} slots: {measurement['cases_per_second']:.1f} cases/s; coverage {measurement['persistence_coverage']:.0%}",
                    flush=True,
                )
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
