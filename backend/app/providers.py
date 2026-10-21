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
        self.pending_releases = set()
        if config.redis_url:
            from redis.asyncio import Redis

            self.redis = Redis.from_url(
                config.redis_url, socket_connect_timeout=1, socket_timeout=1
            )

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
                        if self.pending_releases:
                            pending = set(self.pending_releases)
                            await self.redis.zrem("evalscope:provider:slots", *pending)
                            self.pending_releases.difference_update(pending)
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
                        self.pending_releases.add(token)

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

    async def request(self, path, body, *, scope=None, config=None):
        from . import usage
        from .security import decrypt_credential

        key = self.settings.provider_key
        job = usage.current_job.get()
        if job and job["config"].get("provider_credential_id"):
            try:
                key = decrypt_credential(
                    job["config"]["provider_credential_id"], job["project_id"]
                )
            except ValueError:
                raise ProviderError("credential_unavailable") from None
        if not key:
            raise ProviderError("credentials_missing")
        async with self.limiter.slot():
            identity = usage.begin(scope, body["model"], config) if scope else None
            try:
                response = await self.client.post(
                    self.settings.provider_url + path,
                    json=body,
                    headers={"Authorization": f"Bearer {key}"},
                )
                if response.status_code >= 400:
                    code = response.status_code
                    category = (
                        "rate_limit"
                        if code == 429
                        else (
                            "authentication"
                            if code in (401, 403)
                            else "provider_server" if code >= 500 else "invalid_request"
                        )
                    )
                    usage.finish(
                        identity,
                        "REJECTED" if code < 500 else "UNCERTAIN",
                        error=category,
                        billable=code >= 500,
                    )
                    raise ProviderError(category, code == 429 or code >= 500)
                payload = response.json()
                reported = payload.get("usage", {})
                incoming = reported.get(
                    "prompt_tokens",
                    reported.get("total_tokens") if scope == "embedding" else None,
                )
                outgoing = (
                    0 if scope == "embedding" else reported.get("completion_tokens")
                )
                valid = all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                    for value in (incoming, outgoing)
                )
                usage.finish(
                    identity,
                    "REPORTED" if valid else "UNREPORTED",
                    incoming if valid else None,
                    outgoing if valid else None,
                    request_id=response.headers.get("x-request-id"),
                )
                return payload
            except (httpx.TimeoutException, httpx.NetworkError):
                usage.finish(identity, "UNCERTAIN", error="network_timeout")
                raise ProviderError("network_timeout", True) from None
            except (ValueError, KeyError, TypeError, AttributeError):
                usage.finish(identity, "UNCERTAIN", error="malformed_response")
                raise ProviderError("malformed_response") from None
            except BaseException:
                usage.finish(identity, "UNCERTAIN", error="request_interrupted")
                raise

    async def generate(self, config, case, prompt, attempt):
        if config["provider"] == "mock":
            return await self.mock_generate(config, case, prompt, attempt)
        response = await self.request(
            "/chat/completions",
            {
                "model": config["model"],
                "temperature": config["temperature"],
                "messages": [{"role": "user", "content": prompt}],
                **(
                    {"max_completion_tokens": config["max_completion_tokens"]}
                    if config.get("max_completion_tokens") is not None
                    else {}
                ),
            },
            scope="generation",
            config=config,
        )
        try:
            output = response["choices"][0]["message"]["content"]
            if not isinstance(output, str) or len(output) > 100_000:
                raise ValueError("Invalid content")
            reported = response.get("usage", {})
            values = (
                reported.get("prompt_tokens", 0),
                reported.get("completion_tokens", 0),
            )
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values
            ):
                raise ValueError("Invalid usage")
            return output, *values
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise ProviderError("malformed_response") from None

    async def mock_generate(self, config, case, prompt, attempt):
        from . import usage

        identity = usage.begin(
            "generation", config["model"], config, source="simulated", rates=(0, 0)
        )
        try:
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
            tokens = max(1, len(prompt) // 4), max(1, len(output) // 4)
            usage.finish(identity, "REPORTED", *tokens)
            return output, *tokens
        except BaseException as exc:
            usage.finish(
                identity,
                "REJECTED",
                error=getattr(exc, "category", "interrupted"),
                billable=False,
            )
            raise

    async def embeddings(self, config, output, reference):
        response = await self.request(
            "/embeddings",
            {"model": config["embedding_model"], "input": [output, reference]},
            scope="embedding",
            config=config,
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
                **(
                    {"max_completion_tokens": config["judge_max_completion_tokens"]}
                    if config.get("judge_max_completion_tokens") is not None
                    else {}
                ),
                "messages": [
                    {"role": "system", "content": JUDGE_RUBRIC},
                    {"role": "user", "content": json.dumps(data)},
                ],
            },
            scope="judge",
            config=config,
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
