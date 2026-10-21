import asyncio
from dataclasses import replace
import os
import time

import pytest

from backend.app.config import settings
from backend.app.providers import ProviderLimiter


@pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"), reason="Requires isolated TEST_REDIS_URL"
)
async def test_redis_limits_coordinate_distinct_worker_instances():
    config = replace(
        settings,
        redis_url=os.environ["TEST_REDIS_URL"],
        provider_concurrency=2,
        provider_rps=1000,
    )
    first, second = ProviderLimiter(config), ProviderLimiter(config)
    await first.redis.delete("evalscope:provider:slots", "evalscope:provider:last")
    active = peak = 0

    async def call(limiter):
        nonlocal active, peak
        async with limiter.slot():
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.04)
            active -= 1

    try:
        await asyncio.gather(*(call(first if i % 2 else second) for i in range(8)))
        assert peak == 2
        assert await first.redis.zcard("evalscope:provider:slots") == 0
    finally:
        await first.redis.delete("evalscope:provider:slots", "evalscope:provider:last")
        await first.close()
        await second.close()
