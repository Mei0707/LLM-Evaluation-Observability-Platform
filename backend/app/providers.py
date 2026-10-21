import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
import httpx
from .config import settings
from .evaluators import JUDGE_RUBRIC


class ProviderError(Exception):
    def __init__(self, category, transient=False):
        super().__init__(category)
        self.category = category
        self.transient = transient


class ProviderLimiter:
    """Redis leases coordinate live requests across worker processes.

    Local fallback is single-process only. Redis outages fail closed for live calls.
    """

    def __init__(self, config=settings):
        self.settings = config
        self.semaphore = asyncio.Semaphore(config.provider_concurrency)
        self.lock = asyncio.Lock()
        self.last = 0.0
        self.redis = None
        if config.redis_url:
            from redis.asyncio import Redis

            self.redis = Redis.from_url(config.redis_url)

    @asynccontextmanager
    async def slot(self):
        async with self.semaphore:
            token = hashlib.sha256(f"{time.time_ns()}".encode()).hexdigest()
            acquired = False
            if self.redis:
                script = """
                local t = redis.call('TIME')
                local now = tonumber(t[1]) * 1000 + tonumber(t[2]) / 1000
                redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
                local last = tonumber(redis.call('GET', KEYS[2]) or '0')
                if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) or now-last < tonumber(ARGV[2]) then return 0 end
                redis.call('ZADD', KEYS[1], now+125000, ARGV[3])
                redis.call('PEXPIRE', KEYS[1], 130000)
                redis.call('SET', KEYS[2], now, 'PX', 130000)
                return 1
                """
                try:
                    while not acquired:
                        acquired = bool(
                            await self.redis.eval(
                                script,
                                2,
                                "evalscope:provider:slots",
                                "evalscope:provider:last",
                                self.settings.provider_concurrency,
                                1000 / self.settings.provider_rps,
                                token,
                            )
                        )
                        if not acquired:
                            await asyncio.sleep(0.1)
                except Exception as exc:
                    raise ProviderError("rate_limiter_unavailable", True) from exc
            else:
                async with self.lock:
                    await asyncio.sleep(
                        max(
                            0,
                            1 / self.settings.provider_rps
                            - (time.monotonic() - self.last),
                        )
                    )
                    self.last = time.monotonic()
            try:
                yield
            finally:
                if acquired:
                    try:
                        await self.redis.zrem("evalscope:provider:slots", token)
                    except Exception:
                        pass  # lease has a bounded expiry

    async def close(self):
        if self.redis:
            await self.redis.aclose()


class Provider:
    def __init__(self, limiter, config=settings):
        self.settings = config
        self.limiter = limiter
        self.client = httpx.AsyncClient(timeout=120)

    async def close(self):
        await self.client.aclose()
        await self.limiter.close()

    async def request(self, path, body):
        if not self.settings.provider_key:
            raise ProviderError("credentials_missing")
        async with self.limiter.slot():
            try:
                response = await self.client.post(
                    self.settings.provider_url + path,
                    json=body,
                    headers={"Authorization": f"Bearer {self.settings.provider_key}"},
                )
                if response.status_code >= 400:
                    code = response.status_code
                    raise ProviderError(
                        (
                            "rate_limit"
                            if code == 429
                            else (
                                "authentication"
                                if code in (401, 403)
                                else (
                                    "provider_server"
                                    if code >= 500
                                    else "invalid_request"
                                )
                            )
                        ),
                        code == 429 or code >= 500,
                    )
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError("network_timeout", True) from exc
            except (ValueError, KeyError, TypeError) as exc:
                raise ProviderError("malformed_response") from exc

    async def generate(self, config, case, prompt, attempt):
        if config["provider"] == "mock":
            digest = int(hashlib.sha256(case["case_id"].encode()).hexdigest()[:8], 16)
            await asyncio.sleep(
                config["mock_latency_ms"] / 1000 * (0.6 + digest % 80 / 100)
            )
            failure = case.get("mock_failure")
            if failure == "permanent":
                raise ProviderError("invalid_request")
            if failure in {"rate_limit", "timeout"} and attempt < 3:
                raise ProviderError(failure, True)
            if failure == "malformed":
                raise ProviderError("malformed_response")
            correct = config["model"] == "mock-precise" or digest % 100 >= (
                28 if config["model"] == "mock-regressed" else 8
            )
            output = (
                case.get("mock_output")
                if case.get("mock_output") is not None
                else (
                    case["reference_answer"]
                    if correct
                    else "I do not have enough information to answer this question."
                )
            )
            return output, max(1, len(prompt) // 4), max(1, len(output) // 4)
        response = await self.request(
            "/chat/completions",
            {
                "model": config["model"],
                "temperature": config["temperature"],
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        try:
            output = response["choices"][0]["message"]["content"]
            if not isinstance(output, str) or len(output) > 100_000:
                raise ValueError("Invalid content")
            usage = response.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (input_tokens, output_tokens)
            ):
                raise ValueError("Invalid usage")
            return output, input_tokens, output_tokens
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ProviderError("malformed_response") from exc

    async def embeddings(self, config, output, reference):
        response = await self.request(
            "/embeddings",
            {"model": config["embedding_model"], "input": [output, reference]},
        )
        try:
            data = sorted(response["data"], key=lambda item: item["index"])
            if len(data) != 2 or [item["index"] for item in data] != [0, 1]:
                raise ValueError("Expected two embeddings")
            return data[0]["embedding"], data[1]["embedding"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("malformed_embedding") from exc

    async def judge(self, config, output, case):
        data = {
            "question": case["input"],
            "answer": output,
            "reference": case["reference_answer"],
            "contexts": case["reference_contexts"],
        }
        response = await self.request(
            "/chat/completions",
            {
                "model": config["judge_model"],
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": JUDGE_RUBRIC},
                    {"role": "user", "content": json.dumps(data)},
                ],
            },
        )
        try:
            verdict = json.loads(response["choices"][0]["message"]["content"])
            score = verdict["score"]
            if (
                isinstance(score, bool)
                or not isinstance(score, int)
                or not 1 <= score <= 5
                or not isinstance(verdict["reason"], str)
            ):
                raise ValueError("Invalid verdict")
            return (
                (score - 1) / 4,
                verdict["reason"][:2000],
                {"raw_score": score, "max_score": 5, "rubric_version": "rubric-v1"},
            )
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            raise ProviderError("malformed_judge_response") from exc
