import asyncio
import time
from dataclasses import replace
import pytest
from sqlalchemy import select
from backend.app.config import settings
from backend.app.db import transaction
from backend.app.models import Attempt, Project, Result, Run, Score, uid
from backend.app.providers import Provider, ProviderLimiter
from backend.app.seed import DEFAULT_PROJECT
from backend.app.worker import claim, execute, persist
from backend.app.telemetry import Recorder


async def drain():
    provider = Provider(ProviderLimiter())
    try:
        for _ in range(100):
            job = claim()
            if not job:
                break
            await execute(job, provider)
    finally:
        await provider.close()


def start(client, configured):
    response = client.post(
        "/api/v1/runs", json={"experiment_id": configured["experiment"]["id"]}
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_complete_lifecycle_and_trace(client, configured):
    run = start(client, configured)
    asyncio.run(drain())
    status = client.get(f"/api/v1/runs/{run['id']}").json()
    assert status["status"] == "COMPLETED"
    assert status["metrics"]["pass_rate"] == 1
    results = client.get(f"/api/v1/runs/{run['id']}/results").json()
    assert results["total"] == 10
    trace = client.get(f"/api/v1/traces/{results['items'][0]['trace_id']}").json()
    assert {s["name"] for s in trace["spans"]} >= {
        "llm.generate",
        "evaluation.score",
        "prompt.construct",
    }
    assert all("input" not in s["attributes"] for s in trace["spans"])
    assert client.get("/metrics").status_code == 200


def test_version_snapshot_survives_new_version(client, configured):
    run = start(client, configured)
    response = client.post(
        f"/api/v1/datasets/{configured['dataset']['id']}/versions",
        json={
            "cases": [
                {
                    "case_id": "replacement",
                    "input": "new question",
                    "reference_answer": "new answer",
                }
            ]
        },
    )
    assert response.status_code == 201
    asyncio.run(drain())
    results = client.get(f"/api/v1/runs/{run['id']}/results").json()
    assert results["total"] == 10
    assert "replacement" not in [r["case_id"] for r in results["items"]]


def test_duplicate_delivery_and_stale_attempt_are_fenced(client, configured):
    run = start(client, configured)
    job = claim()
    with transaction() as session:
        session.get(Result, job["result_id"]).lease_until = time.time() - 1
    replacement = claim()
    assert replacement["result_id"] == job["result_id"]
    assert replacement["attempt"] == 2
    recorder = Recorder()
    assert not persist(job, recorder, "late", [("exact_match", 1, "ok", {})], 1, (1, 1))
    assert persist(
        replacement, recorder, "current", [("exact_match", 1, "ok", {})], 1, (1, 1)
    )
    assert not persist(
        replacement, recorder, "duplicate", [("exact_match", 1, "ok", {})], 1, (1, 1)
    )
    with transaction() as session:
        assert (
            len(
                session.scalars(
                    select(Score).where(Score.result_id == job["result_id"])
                ).all()
            )
            == 1
        )
        assert (
            session.scalar(
                select(Attempt).where(
                    Attempt.result_id == job["result_id"], Attempt.number == 1
                )
            ).status
            == "ABANDONED"
        )


def test_cancel_pending_and_inflight_prevents_late_write(client, configured):
    run = start(client, configured)
    job = claim()
    response = client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["metrics"]["canceled"] == 10
    assert not persist(
        job, Recorder(), "late", [("exact_match", 1, "ok", {})], 1, (1, 1)
    )
    assert claim() is None


@pytest.mark.parametrize(
    "failure,final,attempts",
    [
        ("permanent", "FAILED", 1),
        ("malformed", "FAILED", 1),
        ("rate_limit", "COMPLETED", 3),
        ("timeout", "COMPLETED", 3),
    ],
)
def test_provider_failures_retry_only_transient(
    client, configured, failure, final, attempts
):
    dataset = client.post(
        "/api/v1/datasets",
        json={
            "name": "Failures",
            "cases": [
                {
                    "case_id": "fail",
                    "input": "q",
                    "reference_answer": "a",
                    "mock_failure": failure,
                }
            ],
        },
    ).json()
    config = {
        **configured["config"],
        "dataset_version_id": dataset["versions"][0]["id"],
    }
    experiment = client.post(
        "/api/v1/experiments", json={"name": "Failure test", "config": config}
    ).json()
    run = client.post("/api/v1/runs", json={"experiment_id": experiment["id"]}).json()
    for _ in range(attempts):
        asyncio.run(drain())
        with transaction() as session:
            for result in session.scalars(
                select(Result).where(Result.run_id == run["id"])
            ):
                result.available_at = 0
    result = client.get(f"/api/v1/runs/{run['id']}/results").json()["items"][0]
    assert result["status"] == final
    assert result["attempts"] == attempts


def test_comparison_and_ci_gate_identify_regressions(client, configured):
    baseline = start(client, configured)
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Regressed",
            "config": {**configured["config"], "model": "mock-regressed"},
        },
    ).json()
    candidate = client.post(
        "/api/v1/runs", json={"experiment_id": experiment["id"]}
    ).json()
    asyncio.run(drain())
    report = client.post(
        "/api/v1/quality-gates/check",
        json={"baseline_id": baseline["id"], "candidate_id": candidate["id"]},
    ).json()
    assert report["decision"] == "FAIL"
    assert report["comparison"]["counts"]["regressed"] > 0
    assert len(report["comparison"]["score_delta_95_ci"]) == 2


def test_gate_inconclusive_for_unfinished_data(client, configured):
    a, b = start(client, configured), start(client, configured)
    report = client.post(
        "/api/v1/quality-gates/check",
        json={"baseline_id": a["id"], "candidate_id": b["id"]},
    ).json()
    assert report["decision"] == "INCONCLUSIVE"


def test_incompatible_comparison_rejected(client, configured):
    a = start(client, configured)
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Different threshold",
            "config": {**configured["config"], "pass_threshold": 0.9},
        },
    ).json()
    b = client.post("/api/v1/runs", json={"experiment_id": experiment["id"]}).json()
    assert (
        client.post(
            "/api/v1/comparisons",
            json={"baseline_id": a["id"], "candidate_id": b["id"]},
        ).status_code
        == 409
    )


def test_cross_project_access_rejected(client, configured):
    with transaction() as session:
        other = uid()
        session.add(Project(id=other, name="Other project"))
    assert (
        client.get(
            f"/api/v1/datasets/{configured['dataset']['id']}",
            headers={"X-Project-ID": other},
        ).status_code
        == 404
    )
    response = client.post(
        "/api/v1/experiments",
        headers={"X-Project-ID": other},
        json={"name": "Forbidden", "config": configured["config"]},
    )
    assert response.status_code == 404


def test_content_capture_off_and_human_review(client, configured):
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Private",
            "config": {**configured["config"], "capture_content": False},
        },
    ).json()
    run = client.post("/api/v1/runs", json={"experiment_id": experiment["id"]}).json()
    asyncio.run(drain())
    result = client.get(f"/api/v1/runs/{run['id']}/results").json()["items"][0]
    assert result["output"] is None
    assert (
        client.put(
            f"/api/v1/results/{result['id']}/review", json={"score": 1}
        ).status_code
        == 409
    )


def test_jsonl_and_csv_import_validation(client):
    response = client.post(
        "/api/v1/datasets/import",
        json={
            "name": "Imported",
            "format": "csv",
            "content": 'case_id,input,reference_answer,tags\na,Question,Answer,"[""policy""]"\n',
        },
    )
    assert response.status_code == 201, response.text
    assert (
        client.post(
            "/api/v1/datasets/import",
            json={
                "name": "Bad",
                "format": "jsonl",
                "content": '{"input": "missing fields"}',
            },
        ).status_code
        == 422
    )


def test_run_concurrency_limit(client, configured):
    start(client, configured)
    jobs = [claim() for _ in range(6)]
    assert sum(job is not None for job in jobs) == 5


def test_case_deadline_records_failure_without_hanging(client, configured):
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Deadline",
            "config": {
                **configured["config"],
                "timeout_seconds": 0.01,
                "mock_latency_ms": 100,
                "max_attempts": 1,
            },
        },
    ).json()
    run = client.post("/api/v1/runs", json={"experiment_id": experiment["id"]}).json()
    asyncio.run(drain())
    results = client.get(f"/api/v1/runs/{run['id']}/results").json()["items"]
    assert all(
        result["status"] == "FAILED"
        and result["error"] == "timeout"
        and result["attempts"] == 1
        for result in results
    )
    assert client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "FAILED"
