"""Kill a worker process mid-request and verify durable lease recovery."""

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix="evalscope-recovery-") as directory:
        os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(directory) / "recovery.db")
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        os.environ["REDIS_URL"] = ""
        from sqlalchemy import select
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
        from backend.app.services import create_version, start_run
        from backend.app.seed import DEFAULT_PROJECT

        Base.metadata.create_all(engine)
        with transaction() as session:
            session.add(Project(id=DEFAULT_PROJECT, name="Recovery benchmark"))
            session.flush()
            dataset = Dataset(id=uid(), project_id=DEFAULT_PROJECT, name="Recovery")
            prompt = PromptVersion(
                id=uid(), project_id=DEFAULT_PROJECT, name="v1", template="{input}"
            )
            session.add_all([dataset, prompt])
            session.flush()
            version = create_version(
                session,
                dataset,
                [
                    CaseInput(case_id=f"recovery-{i}", input="q", reference_answer="a")
                    for i in range(20)
                ],
            )
            config = RunConfig(
                dataset_version_id=version.id,
                prompt_version_id=prompt.id,
                model="mock-precise",
                mock_latency_ms=1000,
                concurrency=5,
            ).model_dump()
            experiment = Experiment(
                id=uid(), project_id=DEFAULT_PROJECT, name="Recovery", config=config
            )
            session.add(experiment)
            session.flush()
            run_id = start_run(session, experiment).id
        command = [sys.executable, "-m", "backend.app.worker"]
        worker = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        replacement = None
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with transaction() as session:
                    running = session.scalars(
                        select(Result).where(Result.status == "RUNNING")
                    ).all()
                    if running:
                        break
                time.sleep(0.02)
            else:
                raise RuntimeError("Worker never claimed a case")
            worker.kill()
            worker.wait()
            killed = time.monotonic()
            replacement = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            while time.monotonic() - killed < 60:
                with transaction() as session:
                    run = session.get(Run, run_id)
                    if run.status == "COMPLETED":
                        results = session.scalars(
                            select(Result).where(Result.run_id == run_id)
                        ).all()
                        abandoned = session.scalars(
                            select(Attempt).where(Attempt.status == "ABANDONED")
                        ).all()
                        report = {
                            "os": platform.platform(),
                            "database": "isolated SQLite WAL",
                            "failure": "SIGKILL during active inference",
                            "lease_seconds": 30,
                            "cases": 20,
                            "persisted": len(results),
                            "completed": sum(r.status == "COMPLETED" for r in results),
                            "recovered_abandoned_attempts": len(abandoned),
                            "duplicate_logical_results": len(results)
                            - len({r.test_case_id for r in results}),
                            "seconds_from_kill_to_complete": time.monotonic() - killed,
                        }
                        output = Path("benchmarks/results/recovery.json")
                        output.parent.mkdir(parents=True, exist_ok=True)
                        output.write_text(json.dumps(report, indent=2) + "\n")
                        print(json.dumps(report, indent=2))
                        assert (
                            report["completed"] == 20
                            and report["duplicate_logical_results"] == 0
                            and report["recovered_abandoned_attempts"] > 0
                        )
                        return
                time.sleep(0.1)
            raise RuntimeError("Recovery exceeded 60 seconds")
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait()
            if replacement and replacement.poll() is None:
                replacement.terminate()
                replacement.wait(timeout=5)


if __name__ == "__main__":
    main()
