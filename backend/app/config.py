import os
from pathlib import Path
from dataclasses import dataclass


def secret(name):
    filename = os.getenv(name + "_FILE")
    return Path(filename).read_text().strip() if filename else os.getenv(name, "")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./evalscope.db")
    redis_url: str = os.getenv("REDIS_URL", "")
    api_token: str = os.getenv("EVALSCOPE_API_TOKEN", "")
    embedded_worker: bool = (
        os.getenv("EVALSCOPE_EMBEDDED_WORKER", "true").lower() == "true"
    )
    seed_demo: bool = os.getenv("EVALSCOPE_SEED_DEMO", "true").lower() == "true"
    provider_key: str = secret("PROVIDER_API_KEY")
    provider_url: str = os.getenv(
        "PROVIDER_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    provider_concurrency: int = max(1, int(os.getenv("PROVIDER_CONCURRENCY", "5")))
    provider_rps: float = max(
        0.1, float(os.getenv("PROVIDER_REQUESTS_PER_SECOND", "5"))
    )
    auth_mode: str = os.getenv("EVALSCOPE_AUTH_MODE", "local")
    bootstrap_token: str = secret("EVALSCOPE_BOOTSTRAP_TOKEN")
    master_key: str = secret("EVALSCOPE_MASTER_KEY")
    target_allowed_hosts: tuple = tuple(
        filter(None, os.getenv("EVALSCOPE_TARGET_HOSTS", "").split(","))
    )
    require_https: bool = (
        os.getenv("EVALSCOPE_REQUIRE_HTTPS", "false").lower() == "true"
    )
    lease_seconds: float = float(os.getenv("EVALSCOPE_LEASE_SECONDS", "30"))
    poll_seconds: float = 0.2
    worker_slots: int = int(os.getenv("EVALSCOPE_WORKER_SLOTS", "8"))


settings = Settings()
