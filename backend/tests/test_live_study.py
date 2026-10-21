"""Offline study protocol checks; these are not real-model or human evidence."""

from dataclasses import replace
import asyncio
import json

import httpx
import pytest

from backend.app.config import settings
from backend.app.providers import Provider, ProviderLimiter
from backend.app.schemas import RunConfig
from cli.study import ROOT, collect, execute, load_prepared, prepare, summarize


def prepared_study(tmp_path):
    return prepare(
        ROOT / "studies/live-workflow/plan.yaml",
        ROOT / "datasets/review/corpus.jsonl",
        tmp_path,
        model="test-generation-model",
        judge_model="test-judge-model",
    )


def test_prepare_is_offline_frozen_and_excludes_fixture_outputs(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Preparation must not access the network")

    monkeypatch.setattr(httpx.Client, "request", no_network)
    prepared = prepared_study(tmp_path)
    assert len(prepared["cases"]) == 100
    assert prepared["planned_generation_requests"] == 200
    assert prepared["planned_judge_requests"] == 200
    assert prepared["maximum_generated_tokens"] == 153600
    for case in prepared["cases"]:
        assert (
            not {"mock_output", "mock_failure", "retrieved_document_ids"} & case.keys()
        )
    for variant in prepared["variants"]:
        assert variant["config"]["max_attempts"] == 1
        assert variant["config"]["capture_content"]
        assert "reference_answer" not in variant["template"]
    assert load_prepared(tmp_path) == prepared
    prepared["variants"][0]["config"]["model"] = "changed-model"
    (tmp_path / "prepared.json").write_text(json.dumps(prepared))
    with pytest.raises(ValueError, match="changed"):
        load_prepared(tmp_path)


def test_launch_requires_opt_in_and_never_retries_an_ambiguous_post(tmp_path):
    prepared = prepared_study(tmp_path)

    class TestAPI:
        url, project = "http://localhost:8000", "test-project"
        launches = 0

        def request(self, method, path, body):
            if path == "/datasets":
                return {"versions": [{"id": "dataset-version"}]}
            if path == "/runs":
                self.launches += 1
                raise httpx.ReadTimeout("Ambiguous: server may have accepted the run")
            return {"id": path.rsplit("/", 1)[-1]}

    api = TestAPI()
    with pytest.raises(ValueError, match="allow-paid"):
        execute(prepared, tmp_path, api)
    assert not (tmp_path / "state.json").exists()
    with pytest.raises(httpx.ReadTimeout):
        execute(prepared, tmp_path, api, allow_paid=True)
    with pytest.raises(ValueError, match="state exists"):
        execute(prepared, tmp_path, api, allow_paid=True)
    assert api.launches == 1
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["runs"]["baseline"]["launch_attempted"]
    assert state["runs"]["baseline"]["run_id"] is None
    assert not state["runs"]["candidate"]["launch_attempted"]


async def test_live_requests_forward_separate_generation_and_judge_caps():
    cfg = replace(settings, provider_key="offline-test", provider_rps=100000)
    provider = Provider(ProviderLimiter(cfg), cfg)
    await provider.client.aclose()
    captured = []

    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                json.dumps({"score": 5, "reason": "Offline fixture"})
                                if body["model"] == "test-judge"
                                else "answer"
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = RunConfig(
        dataset_version_id="v",
        prompt_version_id="p",
        provider="openai_compatible",
        model="test-generation",
        judge_model="test-judge",
        evaluators=["llm_judge"],
        max_completion_tokens=512,
        judge_max_completion_tokens=256,
    ).model_dump()
    try:
        await provider.generate(config, {}, "Question and evidence only", 1)
        await provider.judge(
            config,
            "answer",
            {"input": "q", "reference_answer": "gold", "reference_contexts": []},
        )
        assert [body["max_completion_tokens"] for body in captured] == [512, 256]
        assert "gold" not in json.dumps(captured[0])
        assert "gold" in json.dumps(captured[1])
    finally:
        await provider.close()


def test_study_report_preserves_errors_unknown_usage_and_tag_denominators(tmp_path):
    prepared = prepared_study(tmp_path)
    case = prepared["cases"][0]
    exports = {
        "baseline": {
            "run": {"id": "r", "status": "PARTIAL", "metrics": {"coverage": 0.5}},
            "results": [
                {
                    "case_id": case["case_id"],
                    "status": "COMPLETED",
                    "output": case["reference_answer"],
                    "scores": [{"evaluator": "llm_judge", "value": 0.75}],
                },
                {
                    "case_id": prepared["cases"][1]["case_id"],
                    "status": "FAILED",
                    "error": "rate_limit",
                    "scores": [],
                },
            ],
            "usage": {
                "summary": {"complete": False, "unpriced_calls": 1},
                "events": [
                    {"scope": "generation", "created_at": 10, "finished_at": 10.5},
                    {"scope": "judge", "created_at": 11, "finished_at": None},
                ],
            },
        }
    }
    result = summarize(prepared, exports)["baseline"]
    assert result["errors"] == {"rate_limit": 1}
    assert result["usage"]["complete"] is False
    assert result["judge_score_by_tag"]["arithmetic"] == {"count": 1, "mean": 0.75}
    assert result["request_latency_by_stage"]["generation"]["p50_ms"] == 500
    assert result["request_latency_by_stage"]["judge"]["p50_ms"] is None


def test_prepared_study_runs_through_platform_and_exports_without_live_calls(
    client, tmp_path, monkeypatch
):
    from backend.app import api as api_module
    from backend.app.worker import claim, execute as execute_job

    cfg = replace(settings, provider_key="offline-fixture", provider_rps=100000)
    monkeypatch.setattr(api_module, "settings", cfg)
    prepared = prepared_study(tmp_path)

    class LocalAPI:
        url = "http://localhost:8000"
        project = "00000000-0000-4000-8000-000000000001"

        def request(self, method, path, body=None):
            response = client.request(method, "/api/v1" + path, json=body)
            response.raise_for_status()
            return response.json()

    api = LocalAPI()
    state = execute(prepared, tmp_path, api, allow_paid=True)
    assert set(state["runs"]) == {"baseline", "candidate"}

    async def drain_offline():
        provider = Provider(ProviderLimiter(cfg), cfg)
        await provider.client.aclose()

        def handler(request):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                headers={"x-request-id": "offline-test-only"},
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    json.dumps(
                                        {"score": 4, "reason": "Offline judge fixture"}
                                    )
                                    if body["model"] == "test-judge-model"
                                    else "Offline response fixture"
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                },
            )

        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            while job := claim():
                await execute_job(job, provider)
        finally:
            await provider.close()

    asyncio.run(drain_offline())
    report = collect(prepared, tmp_path, api)
    assert report["comparison"]["paired_cases"] == 100
    assert report["human_review_status"] == "PENDING_INDEPENDENT_REVIEWERS"
    for label in ("baseline", "candidate"):
        summary = report["summaries"][label]
        assert summary["status"] == "COMPLETED"
        assert summary["usage"]["calls"] == 200
        assert summary["usage"]["input_tokens"] == 4000
        assert summary["usage"]["unpriced_calls"] == 200
        assert summary["usage"]["complete"] is False
        assert len(report["exports"][label]["results"]) == 100
