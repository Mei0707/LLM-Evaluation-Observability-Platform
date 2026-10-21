import os
import tempfile
from pathlib import Path

# Configure before application imports; never touch the developer's database.
_directory = tempfile.TemporaryDirectory(prefix="evalscope-tests-")
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", f"sqlite:///{Path(_directory.name) / 'test.db'}"
)
os.environ["EVALSCOPE_SEED_DEMO"] = "false"
os.environ["EVALSCOPE_EMBEDDED_WORKER"] = "false"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
os.environ["REDIS_URL"] = ""

import pytest
from fastapi.testclient import TestClient
from backend.app.api import app
from backend.app.db import Base, engine


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def configured(client):
    dataset = client.post(
        "/api/v1/datasets",
        json={
            "name": "Test dataset",
            "cases": [
                {
                    "case_id": f"case-{i}",
                    "input": f"Question {i}",
                    "reference_answer": f"Answer {i}",
                }
                for i in range(10)
            ],
        },
    ).json()
    prompt = client.post(
        "/api/v1/prompts",
        json={"name": "v1", "template": "Question: {input}\n{contexts}"},
    ).json()
    config = {
        "dataset_version_id": dataset["versions"][0]["id"],
        "prompt_version_id": prompt["id"],
        "model": "mock-precise",
        "mock_latency_ms": 0,
        "capture_content": True,
    }
    experiment = client.post(
        "/api/v1/experiments", json={"name": "Test experiment", "config": config}
    ).json()
    return {
        "dataset": dataset,
        "prompt": prompt,
        "experiment": experiment,
        "config": config,
    }
