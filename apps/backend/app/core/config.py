"""Application configuration.

Settings are loaded from environment variables (prefixed with ``ATLAS_``) so the
same image can run locally, in Docker Compose and in CI without code changes.
No secret has a meaningful default: production values must come from the
environment / secret store, never from the repository.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the ATLAS control plane."""

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    env: str = "development"
    log_level: str = "INFO"
    app_name: str = "ATLAS Control Plane"

    # Storage / infrastructure
    database_url: str = "postgresql+asyncpg://atlas:atlas@postgres:5432/atlas"
    redis_url: str = "redis://redis:6379/0"

    # Task engine
    task_queue_key: str = "atlas:queue:tasks"
    worker_poll_timeout: int = 5  # seconds for blocking pop
    worker_dummy_duration: float = 0.2  # simulated work time for dummy tasks

    @property
    def is_test(self) -> bool:
        return self.env.lower() in {"test", "testing"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()
