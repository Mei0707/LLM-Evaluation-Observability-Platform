import asyncio
from dataclasses import replace
import json
import time
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select
from backend.app import api as api_module, security, usage
from backend.app.api import app
from backend.app.config import settings
from backend.app.db import transaction
from backend.app.models import (
    Attempt,
    Credential,
    HumanLabel,
    Result,
    Run,
    Score,
    UsageEvent,
    User,
)
from backend.app.providers import Provider, ProviderLimiter
from backend.app.worker import claim, execute


@pytest.fixture
def secure_client(monkeypatch):
    config = replace(
        settings,
        auth_mode="users",
        bootstrap_token="a" * 40,
        master_key=Fernet.generate_key().decode(),
        target_allowed_hosts=("application.test",),
    )
    monkeypatch.setattr(api_module, "settings", config)
    monkeypatch.setattr(security, "settings", config)
    with TestClient(
        app, headers={"Authorization": "Bearer " + config.bootstrap_token}
    ) as client:
        yield client


def create_run(client, n=2, **overrides):
    dataset = client.post(
        "/api/v1/datasets",
        json={
            "name": "Corpus",
            "cases": [
                {
                    "case_id": f"c-{i}",
                    "input": f"Question {i}",
                    "reference_answer": f"Answer {i}",
                    "relevant_document_ids": ["actual-doc"],
                    "retrieved_document_ids": ["gold-must-not-leak"],
                }
                for i in range(n)
            ],
        },
    ).json()
    prompt = client.post(
        "/api/v1/prompts", json={"name": "v1", "template": "{input}"}
    ).json()
    config = {
        "dataset_version_id": dataset["versions"][0]["id"],
        "prompt_version_id": prompt["id"],
        "model": "mock-precise",
        "mock_latency_ms": 0,
        "capture_content": True,
        **overrides,
    }
    experiment = client.post(
        "/api/v1/experiments", json={"name": "Evaluation", "config": config}
    )
    assert experiment.status_code == 201, experiment.text
    return client.post(
        "/api/v1/runs", json={"experiment_id": experiment.json()["id"]}
    ).json()


async def drain(provider=None):
    provider = provider or Provider(ProviderLimiter())
    try:
        while job := claim():
            await execute(job, provider)
    finally:
        await provider.close()


def person(client, name, role):
    user = client.post("/api/v1/users", json={"name": name}).json()
    assert (
        client.put(
            "/api/v1/members", json={"user_id": user["id"], "role": role}
        ).status_code
        == 200
    )
    return {"Authorization": "Bearer " + user["token"]}, user


def test_personal_tokens_roles_and_project_isolation(secure_client):
    client = secure_client
    headers, reader = person(client, "Reader", "reader")
    assert client.get("/api/v1/datasets", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/v1/prompts",
            headers=headers,
            json={"name": "bad", "template": "{input}"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    assert client.get("/metrics", headers=headers).status_code == 403
    other = client.post("/api/v1/projects", json={"name": "Private project"}).json()
    assert (
        client.get(
            "/api/v1/datasets", headers={**headers, "X-Project-ID": other["id"]}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/datasets", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    assert (
        client.patch(
            "/api/v1/users/" + reader["id"], json={"active": False}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/datasets", headers=headers).status_code == 401


def test_token_rotation_revokes_old_token_and_does_not_leak_hash(secure_client):
    client = secure_client
    headers, user = person(client, "Editor", "editor")
    rotated = client.post(f"/api/v1/users/{user['id']}/token", headers=headers).json()
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert (
        client.get(
            "/api/v1/me", headers={"Authorization": "Bearer " + rotated["token"]}
        ).status_code
        == 200
    )
    assert "token_hash" not in client.get("/api/v1/users").text


def test_credentials_are_encrypted_scoped_rotatable_and_not_returned(secure_client):
    client = secure_client
    credential = client.post(
        "/api/v1/credentials",
        json={"name": "Application token", "value": "private-value"},
    ).json()
    assert "ciphertext" not in credential and "private-value" not in json.dumps(
        credential
    )
    with transaction() as session:
        value = session.get(Credential, credential["id"])
        assert value.ciphertext != "private-value"
        project_id = value.project_id
    assert security.decrypt_credential(credential["id"], project_id) == "private-value"
    assert (
        client.put(
            "/api/v1/credentials/" + credential["id"],
            json={"name": "rotated", "value": "new-private"},
        ).json()["version"]
        == 2
    )
    assert security.decrypt_credential(credential["id"], project_id) == "new-private"
    client.delete("/api/v1/credentials/" + credential["id"])
    with pytest.raises(ValueError):
        security.decrypt_credential(credential["id"], project_id)
    assert "private-value" not in client.get("/api/v1/audit").text


def test_target_allowlist_and_admin_only_registration(secure_client):
    client = secure_client
    assert (
        client.post(
            "/api/v1/targets",
            json={"name": "Bad", "url": "http://unapproved.test/evaluate"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/targets",
            json={
                "name": "Bad",
                "url": "http://secret:password@application.test/evaluate",
            },
        ).status_code
        == 422
    )
    headers, _ = person(client, "Editor", "editor")
    assert (
        client.post(
            "/api/v1/targets",
            headers=headers,
            json={"name": "No", "url": "http://application.test/evaluate"},
        ).status_code
        == 403
    )


def test_validation_errors_do_not_echo_secret_values(secure_client):
    secret = "private-secret-" * 1000
    response = secure_client.post(
        "/api/v1/credentials", json={"name": "Credential", "value": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text and "private-secret" not in response.text


def test_real_application_adapter_uses_actual_retrieval_and_keeps_reference_private(
    secure_client,
):
    client = secure_client
    target = client.post(
        "/api/v1/targets",
        json={"name": "Application", "url": "http://application.test/evaluate"},
    ).json()
    run = create_run(
        client,
        n=1,
        target_id=target["id"],
        evaluators=["exact_match", "retrieval"],
        application_prices={
            "app-model": {"input_cost_per_million": 2, "output_cost_per_million": 4}
        },
    )

    async def execute_app():
        provider = Provider(ProviderLimiter())
        await provider.client.aclose()

        def handler(request):
            body = json.loads(request.content)
            assert set(body) == {"input", "configuration"}
            assert (
                "reference_answer" not in request.content.decode()
                and "gold-must-not-leak" not in request.content.decode()
            )
            assert request.headers["traceparent"].startswith("00-")
            return httpx.Response(
                200,
                json={
                    "output": "Answer 0",
                    "retrieved_document_ids": ["actual-doc"],
                    "contexts": ["retrieved evidence"],
                    "usage": [
                        {
                            "scope": "generation",
                            "model": "app-model",
                            "input_tokens": 10,
                            "output_tokens": 5,
                        }
                    ],
                },
            )

        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await drain(provider)

    asyncio.run(execute_app())
    assert (
        client.get(f"/api/v1/runs/{run['id']}").json()["metrics"]["average_score"] == 1
    )
    result = client.get(f"/api/v1/runs/{run['id']}/results").json()["items"][0]
    assert result["evidence"] == {
        "contexts": ["retrieved evidence"],
        "retrieved_document_ids": ["actual-doc"],
    }
    ledger = client.get(f"/api/v1/runs/{run['id']}/usage").json()
    assert ledger["summary"]["known_cost"] == pytest.approx(0.00004)
    assert ledger["summary"]["complete"]


def test_usage_records_generation_embedding_judge_even_when_judge_is_malformed(
    client, monkeypatch
):
    monkeypatch.setattr(api_module, "settings", replace(settings, provider_key="test"))
    run = create_run(
        client,
        n=1,
        provider="openai_compatible",
        model="generation",
        judge_model="judge",
        embedding_model="embedding",
        evaluators=["semantic_similarity", "llm_judge"],
        input_cost_per_million=2,
        output_cost_per_million=4,
        judge_input_cost_per_million=5,
        judge_output_cost_per_million=10,
        embedding_cost_per_million=1,
        max_attempts=1,
    )

    async def calls():
        cfg = replace(settings, provider_key="test", provider_rps=100000)
        provider = Provider(ProviderLimiter(cfg), cfg)
        await provider.client.aclose()

        def handler(request):
            body = json.loads(request.content)
            if body["model"] == "embedding":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 0, "embedding": [1, 0]},
                            {"index": 1, "embedding": [1, 0]},
                        ],
                        "usage": {"total_tokens": 7},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "Answer 0"
                                    if body["model"] == "generation"
                                    else "malformed judge output"
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )

        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await drain(provider)

    asyncio.run(calls())
    ledger = client.get(f"/api/v1/runs/{run['id']}/usage").json()
    assert len(ledger["events"]) == 3
    assert set(ledger["summary"]["by_scope"]) == {"generation", "embedding", "judge"}
    assert ledger["summary"]["known_cost"] == pytest.approx(0.000147)
    assert 'llm_tokens_total{direction="input"} 27' in client.get("/metrics").text
    assert client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "FAILED"


def test_uncertain_provider_requests_survive_lease_recovery(client):
    create_run(client, n=1)
    job = claim()
    with usage.accounting(job):
        identity = usage.begin("generation", "provider-model", job["config"])
    with transaction() as session:
        session.get(Result, job["result_id"]).lease_until = time.time() - 1
    replacement = claim()
    assert replacement["attempt"] == 2
    with transaction() as session:
        assert session.get(UsageEvent, identity).state == "UNCERTAIN"
    # Late billing evidence remains useful even though late logical results are fenced.
    usage.finish(identity, "REPORTED", 100, 20)
    with transaction() as session:
        assert session.get(UsageEvent, identity).state == "REPORTED"


def test_each_retry_retains_a_complete_trace_and_actual_persistence_span(client):
    run = create_run(client, n=1)
    job = claim()
    with transaction() as session:
        session.get(Result, job["result_id"]).lease_until = time.time() - 1
    replacement = claim()
    asyncio.run(drain())  # nothing claimable until the replacement is executed

    async def finish():
        provider = Provider(ProviderLimiter())
        try:
            await execute(replacement, provider)
        finally:
            await provider.close()

    asyncio.run(finish())
    result = client.get(f"/api/v1/runs/{run['id']}/results").json()["items"][0]
    trace = client.get("/api/v1/traces/" + result["trace_id"]).json()
    root = trace["spans"][0]
    persisted = next(s for s in trace["spans"] if s["name"] == "results.persist")
    assert persisted["duration_ms"] > 0
    assert root["ended_at"] >= persisted["ended_at"]
    assert trace["attempt"] == 2 and trace["trace_complete"]


def test_blind_review_enforces_distinct_reviewers_and_reports_disagreement(
    secure_client,
):
    client = secure_client
    run = create_run(client, n=1)
    asyncio.run(drain())
    a, _ = person(client, "Reviewer A", "reviewer")
    b, _ = person(client, "Reviewer B", "reviewer")
    campaign = client.post(
        "/api/v1/review-campaigns",
        json={"name": "Independent review", "run_ids": [run["id"]]},
    ).json()
    path = "/api/v1/review-campaigns/" + campaign["id"]
    queue = client.get(path + "/queue", headers=a).json()
    item = queue["items"][0]
    assert set(item) == {
        "id",
        "input",
        "reference_answer",
        "reference_contexts",
        "retrieved_contexts",
        "retrieved_document_ids",
        "output",
    }
    assert client.get(f"/api/v1/runs/{run['id']}", headers=a).status_code == 403
    assert client.get(path + "/calibration", headers=a).status_code == 403
    labelpath = path + "/items/" + item["id"] + "/labels"
    assert (
        client.post(
            labelpath,
            headers=a,
            json={
                "score": 1,
                "category": "correct",
                "rationale": "All conditions present.",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            labelpath,
            headers=a,
            json={"score": 0, "category": "irrelevant", "rationale": "Duplicate."},
        ).status_code
        == 409
    )
    assert (
        client.post(
            labelpath,
            headers=b,
            json={
                "score": 0.5,
                "category": "incomplete",
                "rationale": "A condition is missing.",
            },
        ).status_code
        == 201
    )
    report = client.get(path + "/calibration").json()
    assert (
        report["independent_reviewer_count"] == 2
        and report["consensus_case_count"] == 1
    )
    assert not report["human_corpus_target_met"]
    assert report["reviewer_mean_absolute_difference"] == 0.5
    assert report["disagreements"][0]["category"] == "disputed"


def test_retention_is_dry_run_by_default_preserves_scores_and_purges_content(client):
    run = create_run(client, n=1)
    asyncio.run(drain())
    with transaction() as session:
        session.get(Run, run["id"]).finished_at = time.time() - 100 * 86400
    assert (
        client.put(
            "/api/v1/retention",
            json={"enabled": True, "content_days": 30, "trace_days": 90},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/retention/sweep", json={}).json()["results"] == 1
    result = client.get(f"/api/v1/runs/{run['id']}/results").json()["items"][0]
    assert result["output"] is not None
    assert (
        client.post("/api/v1/retention/sweep", json={"dry_run": False}).json()[
            "results"
        ]
        == 1
    )
    result = client.get("/api/v1/results/" + result["id"]).json()
    assert result["output"] is None and result["scores"][0]["value"] == 1
    assert client.get("/api/v1/traces/" + result["trace_id"]).json()["expired"]
    assert (
        client.post("/api/v1/retention/sweep", json={"dry_run": False}).json()[
            "results"
        ]
        == 0
    )
