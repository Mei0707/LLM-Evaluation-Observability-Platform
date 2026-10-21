import asyncio
from dataclasses import replace
import httpx
import pytest
from backend.app.config import settings
from backend.app.providers import Provider, ProviderError, ProviderLimiter


@pytest.mark.parametrize(
    "status,category,transient",
    [
        (401, "authentication", False),
        (429, "rate_limit", True),
        (500, "provider_server", True),
        (400, "invalid_request", False),
    ],
)
async def test_live_http_errors_are_redacted_and_classified(
    status, category, transient
):
    config = replace(settings, provider_key="test-never-networked", provider_rps=100000)
    provider = Provider(ProviderLimiter(config), config)
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                json={"private": "provider response must not reach stored error"},
            )
        )
    )
    try:
        with pytest.raises(ProviderError) as error:
            await provider.request("/chat/completions", {})
        assert error.value.category == category
        assert error.value.transient == transient
        assert "private" not in str(error.value)
    finally:
        await provider.close()


async def test_judge_rejects_invalid_scores_and_accepts_valid_json():
    cfg = replace(settings, provider_key="test", provider_rps=100000)
    provider = Provider(ProviderLimiter(cfg), cfg)
    await provider.client.aclose()
    value = {"score": True, "reason": "bad boolean"}
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": __import__("json").dumps(value)}}
                    ]
                },
            )
        )
    )
    config = {"judge_model": "test-model"}
    case = {"input": "q", "reference_answer": "a", "reference_contexts": []}
    try:
        with pytest.raises(ProviderError, match="malformed_judge_response"):
            await provider.judge(config, "a", case)
        value["score"] = 4
        score, _, details = await provider.judge(config, "a", case)
        assert score == 0.75
        assert details["rubric_version"] == "rubric-v1"
    finally:
        await provider.close()


async def test_network_timeouts_are_transient():
    cfg = replace(settings, provider_key="test", provider_rps=100000)
    provider = Provider(ProviderLimiter(cfg), cfg)
    await provider.client.aclose()

    def timeout(request):
        raise httpx.ReadTimeout("contains no persisted provider text")

    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(timeout))
    try:
        with pytest.raises(ProviderError) as error:
            await provider.request("/embeddings", {})
        assert error.value.category == "network_timeout"
        assert error.value.transient
    finally:
        await provider.close()


async def test_live_generation_rejects_negative_usage():
    cfg = replace(settings, provider_key="test", provider_rps=100000)
    provider = Provider(ProviderLimiter(cfg), cfg)
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "answer"}}],
                    "usage": {"prompt_tokens": -1, "completion_tokens": 10},
                },
            )
        )
    )
    try:
        with pytest.raises(ProviderError, match="malformed_response"):
            await provider.generate(
                {"provider": "openai_compatible", "model": "test", "temperature": 0},
                {},
                "prompt",
                1,
            )
    finally:
        await provider.close()
