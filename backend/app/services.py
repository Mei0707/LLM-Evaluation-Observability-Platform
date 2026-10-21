import hashlib
import json
import random
import statistics
import time
from collections import Counter
from sqlalchemy import func, select
from fastapi import HTTPException
from .db import transaction
from .models import (
    Dataset,
    ApplicationTarget,
    Credential,
    DatasetVersion,
    Experiment,
    PromptVersion,
    Result,
    Run,
    Score,
    TestCase,
    uid,
)
from .evaluators import VERSIONS, percentile

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "CANCELED"}


def require(session, model, identity, project_id=None):
    item = session.get(model, identity)
    if not item or (project_id is not None and item.project_id != project_id):
        raise HTTPException(404, f"{model.__name__} not found")
    return item


def columns(item):
    return {
        column.name: getattr(item, column.name) for column in item.__table__.columns
    }


def create_version(session, dataset, cases):
    # Lock parent to serialize version numbering in PostgreSQL.
    session.execute(
        select(Dataset).where(Dataset.id == dataset.id).with_for_update()
    ).scalar_one()
    number = (
        session.scalar(
            select(func.max(DatasetVersion.number)).where(
                DatasetVersion.dataset_id == dataset.id
            )
        )
        or 0
    ) + 1
    data = [c.model_dump() if hasattr(c, "model_dump") else c for c in cases]
    version = DatasetVersion(
        id=uid(),
        dataset_id=dataset.id,
        number=number,
        fingerprint=hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest(),
        case_count=len(data),
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            TestCase(version_id=version.id, case_id=case["case_id"], data=case)
            for case in data
        ]
    )
    return version


def freeze_config(session, config, project_id):
    version = require(session, DatasetVersion, config["dataset_version_id"])
    require(session, Dataset, version.dataset_id, project_id)
    prompt = require(session, PromptVersion, config["prompt_version_id"], project_id)
    target = None
    if config.get("target_id"):
        target = require(session, ApplicationTarget, config["target_id"], project_id)
    if config.get("provider_credential_id"):
        credential = require(
            session, Credential, config["provider_credential_id"], project_id
        )
        if not credential.active:
            raise HTTPException(422, "Provider credential is disabled")
    if "retrieval" in config["evaluators"]:
        cases = session.scalars(
            select(TestCase).where(TestCase.version_id == version.id)
        ).all()
        if any(not case.data["relevant_document_ids"] for case in cases):
            raise HTTPException(
                422,
                "Every case requires relevant_document_ids for retrieval evaluation",
            )
    return {
        **config,
        "prompt_template": prompt.template,
        "prompt_name": prompt.name,
        "dataset_fingerprint": version.fingerprint,
        "evaluator_versions": {
            name: VERSIONS[name] for name in sorted(config["evaluators"])
        },
        "target_snapshot": (
            {
                "id": target.id,
                "name": target.name,
                "url": target.url,
                "protocol": target.protocol,
                "credential_id": target.credential_id,
            }
            if target
            else None
        ),
        "accounting_version": "ledger-v1",
    }


def start_run(session, experiment, name=None):
    version = require(session, DatasetVersion, experiment.config["dataset_version_id"])
    config = freeze_config(session, experiment.config, experiment.project_id)
    run = Run(
        id=uid(),
        project_id=experiment.project_id,
        experiment_id=experiment.id,
        dataset_version_id=version.id,
        name=name or experiment.name,
        config=config,
        total=version.case_count,
    )
    session.add(run)
    session.flush()
    cases = session.scalars(
        select(TestCase).where(TestCase.version_id == version.id)
    ).all()
    session.add_all(
        [
            Result(run_id=run.id, test_case_id=case.id, case_id=case.case_id)
            for case in cases
        ]
    )
    return run


def aggregate(results, total=None):
    total = len(results) if total is None else total
    completed = [r for r in results if r.status == "COMPLETED"]
    failed = sum(r.status == "FAILED" for r in results)
    scores = [r.score for r in completed if r.score is not None]
    latencies = [r.latency_ms for r in completed if r.latency_ms is not None]
    return {
        "total": total,
        "completed": len(completed),
        "failed": failed,
        "canceled": sum(r.status == "CANCELED" for r in results),
        "pending": sum(r.status == "PENDING" for r in results),
        "running": sum(r.status == "RUNNING" for r in results),
        "average_score": statistics.mean(scores) if scores else None,
        "pass_rate": sum(bool(r.passed) for r in completed) / total if total else 0,
        "coverage": len(completed) / total if total else 0,
        "error_rate": failed / total if total else 0,
        "p50_latency_ms": percentile(latencies, 0.5),
        "p95_latency_ms": percentile(latencies, 0.95),
        "input_tokens": sum(r.input_tokens for r in results),
        "output_tokens": sum(r.output_tokens for r in results),
        "estimated_cost": sum(r.cost for r in results),
        "retries": sum(max(0, r.attempts - 1) for r in results),
    }


def run_view(session, run):
    results = session.scalars(select(Result).where(Result.run_id == run.id)).all()
    from .usage import summary

    accounting = summary(session, [run.id])
    metrics = aggregate(results, run.total)
    if accounting["calls"]:
        metrics.update(
            input_tokens=accounting["input_tokens"],
            output_tokens=accounting["output_tokens"],
            estimated_cost=accounting["known_cost"],
        )
    return {**columns(run), "metrics": metrics, "usage": accounting}


def compare(session, baseline, candidate):
    if baseline.id == candidate.id:
        raise HTTPException(422, "Choose two different runs")
    if baseline.dataset_version_id != candidate.dataset_version_id:
        raise HTTPException(409, "Runs must use the same immutable dataset version")
    comparable_fields = [
        "evaluator_versions",
        "pass_threshold",
        "retrieval_k",
        "judge_model",
        "embedding_model",
    ]
    if any(
        baseline.config.get(key) != candidate.config.get(key)
        for key in comparable_fields
    ):
        raise HTTPException(
            409, "Incompatible evaluator configuration or pass threshold"
        )
    left = {
        r.case_id: r
        for r in session.scalars(select(Result).where(Result.run_id == baseline.id))
    }
    right = {
        r.case_id: r
        for r in session.scalars(select(Result).where(Result.run_id == candidate.id))
    }
    cases, differences = [], []
    counts = Counter()
    for case_id in sorted(left.keys() | right.keys()):
        a, b = left.get(case_id), right.get(case_id)
        valid = (
            a
            and b
            and a.status == b.status == "COMPLETED"
            and a.score is not None
            and b.score is not None
        )
        delta = b.score - a.score if valid else None
        change = (
            "missing"
            if delta is None
            else (
                "improved"
                if delta > 1e-9
                else "regressed" if delta < -1e-9 else "unchanged"
            )
        )
        counts[change] += 1
        if delta is not None:
            differences.append(delta)
        cases.append(
            {
                "case_id": case_id,
                "baseline_score": a.score if a else None,
                "candidate_score": b.score if b else None,
                "delta": delta,
                "change": change,
                "baseline_result_id": a.id if a else None,
                "candidate_result_id": b.id if b else None,
            }
        )
    interval = None
    if len(differences) >= 2:
        rng = random.Random(42)
        # Paired percentile bootstrap over case deltas, not independent run means.
        samples = [
            statistics.mean(rng.choices(differences, k=len(differences)))
            for _ in range(1000)
        ]
        interval = [percentile(samples, 0.025), percentile(samples, 0.975)]
    baseline_view, candidate_view = run_view(session, baseline), run_view(
        session, candidate
    )
    return {
        "baseline": baseline_view,
        "candidate": candidate_view,
        "cases": cases,
        "counts": {
            key: counts[key]
            for key in ["improved", "regressed", "unchanged", "missing"]
        },
        "paired_cases": len(differences),
        "cost_comparison_complete": baseline_view["usage"]["complete"]
        and candidate_view["usage"]["complete"],
        "mean_score_delta": statistics.mean(differences) if differences else None,
        "score_delta_95_ci": interval,
        "uncertainty_method": "paired percentile bootstrap, 1000 resamples, seed 42; descriptive, assumes independent cases",
    }


def check_gate(comparison, thresholds):
    baseline, candidate = comparison["baseline"], comparison["candidate"]
    a, b = baseline["metrics"], candidate["metrics"]
    insufficient = []
    if baseline["status"] not in TERMINAL or candidate["status"] not in TERMINAL:
        insufficient.append("Both runs must be terminal")
    if min(a["coverage"], b["coverage"]) < thresholds["minimum_coverage"]:
        insufficient.append("Completed-case coverage is below the required minimum")
    if comparison["paired_cases"] < thresholds["minimum_paired_cases"]:
        insufficient.append("Insufficient paired successful cases")
    checks = [
        {
            "name": "Minimum pass rate",
            "actual": b["pass_rate"],
            "limit": thresholds["minimum_pass_rate"],
            "passed": b["pass_rate"] >= thresholds["minimum_pass_rate"],
        },
        {
            "name": "Maximum pass-rate drop",
            "actual": a["pass_rate"] - b["pass_rate"],
            "limit": thresholds["maximum_pass_rate_drop"],
            "passed": a["pass_rate"] - b["pass_rate"]
            <= thresholds["maximum_pass_rate_drop"] + 1e-12,
        },
        {
            "name": "Maximum p95 latency (ms)",
            "actual": b["p95_latency_ms"],
            "limit": thresholds["maximum_p95_latency_ms"],
            "passed": b["p95_latency_ms"] is not None
            and b["p95_latency_ms"] <= thresholds["maximum_p95_latency_ms"],
        },
        {
            "name": "Maximum error rate",
            "actual": b["error_rate"],
            "limit": thresholds["maximum_error_rate"],
            "passed": b["error_rate"] <= thresholds["maximum_error_rate"],
        },
    ]
    decision = (
        "INCONCLUSIVE"
        if insufficient
        else "PASS" if all(check["passed"] for check in checks) else "FAIL"
    )
    return {
        "decision": decision,
        "checks": checks,
        "insufficient_reasons": insufficient,
        "thresholds": thresholds,
        "comparison": comparison,
    }
