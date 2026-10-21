from dataclasses import replace
import time
from backend.app import api as api_module


def test_optional_authentication_protects_api_and_metrics(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "settings",
        replace(api_module.settings, api_token="test-only-token"),
    )
    assert client.get("/api/v1/datasets").status_code == 401
    assert client.get("/metrics").status_code == 401
    assert client.get("/health").status_code == 200
    assert (
        client.get(
            "/api/v1/datasets", headers={"Authorization": "Bearer test-only-token"}
        ).status_code
        == 200
    )


def test_online_trace_ingestion_is_idempotent_and_content_free(client):
    now = time.time()
    body = {
        "trace_id": "a" * 32,
        "service": "test-app",
        "spans": [
            {
                "name": "generation",
                "span_id": "b" * 16,
                "started_at": now,
                "ended_at": now + 0.05,
                "attributes": {
                    "model": "configured-model",
                    "input_tokens": 5,
                    "output_tokens": 10,
                },
            }
        ],
    }
    response = client.post("/api/v1/traces", json=body)
    assert response.status_code == 201
    assert not response.json()["duplicate"]
    assert client.post("/api/v1/traces", json=body).json()["duplicate"]
    trace = client.get("/api/v1/traces/" + "a" * 32).json()
    assert not trace["content_captured"]
    assert len(client.get("/api/v1/traces").json()) == 1
    body["spans"][0]["attributes"]["prompt"] = "This must never enter traces"
    assert client.post("/api/v1/traces", json=body).status_code == 422


def test_online_trace_rejects_cycles_and_negative_durations(client):
    now = time.time()
    span = {
        "name": "request",
        "span_id": "b" * 16,
        "parent_span_id": "b" * 16,
        "started_at": now,
        "ended_at": now + 0.01,
    }
    body = {"trace_id": "a" * 32, "service": "test-app", "spans": [span]}
    assert client.post("/api/v1/traces", json=body).status_code == 422
    span["parent_span_id"] = None
    span["ended_at"] = now - 1
    assert client.post("/api/v1/traces", json=body).status_code == 422


def test_request_size_limit(client):
    assert (
        client.post(
            "/api/v1/datasets/import", content=b"x" * (6 * 1024 * 1024 + 1)
        ).status_code
        == 413
    )
