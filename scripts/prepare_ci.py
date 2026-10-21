"""Create a shared snapshot and write deterministic CLI configurations."""

import json
from pathlib import Path
import httpx
import yaml

with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=30) as client:

    def post(path, body):
        response = client.post(path, json=body)
        response.raise_for_status()
        return response.json()

    cases = [
        json.loads(line)
        for line in Path("datasets/examples/support.jsonl").read_text().splitlines()
        if line
    ]
    dataset = post("/datasets", {"name": "Deterministic CI suite", "cases": cases})
    prompt = post(
        "/prompts",
        {
            "name": "CI prompt v1",
            "template": "Use the context: {contexts}\nQuestion: {input}",
        },
    )
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    for label, model in [
        ("baseline", "mock-precise"),
        ("candidate", "mock-precise"),
        ("regressed", "mock-regressed"),
    ]:
        data = {
            "name": f"CI {label}",
            "config": {
                "dataset_version_id": dataset["versions"][0]["id"],
                "prompt_version_id": prompt["id"],
                "provider": "mock",
                "model": model,
                "evaluators": ["exact_match"],
                "mock_latency_ms": 0,
                "concurrency": 5,
            },
            "quality_gate": {
                "minimum_pass_rate": 0.9,
                "maximum_pass_rate_drop": 0.03,
                "maximum_p95_latency_ms": 2500,
                "maximum_error_rate": 0.02,
            },
        }
        (output / f"{label}.yaml").write_text(yaml.safe_dump(data))
