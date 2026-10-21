import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./evalscope.db")
    redis_url: str = os.getenv("REDIS_URL", "")
    api_token: str = os.getenv("EVALSCOPE_API_TOKEN", "")
    embedded_worker: bool = (
        os.getenv("EVALSCOPE_EMBEDDED_WORKER", "true").lower() == "true"
    )
    seed_demo: bool = os.getenv("EVALSCOPE_SEED_DEMO", "true").lower() == "true"
    provider_key: str = os.getenv("PROVIDER_API_KEY", "")
    provider_url: str = os.getenv(
        "PROVIDER_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    provider_concurrency: int = max(1, int(os.getenv("PROVIDER_CONCURRENCY", "5")))
    provider_rps: float = max(
        0.1, float(os.getenv("PROVIDER_REQUESTS_PER_SECOND", "5"))
    )
    lease_seconds: float = 30
    poll_seconds: float = 0.2
    worker_slots: int = 8


settings = Settings()
