"""Application configuration.

Settings are loaded from environment variables (prefixed with ``ATLAS_``) so the
same image can run locally, in Docker Compose and in CI without code changes.
No secret has a meaningful default: production values must come from the
environment / secret store, never from the repository.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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

    # Node federation (spec §8). A shared join token authenticates nodes against
    # the control plane (least privilege, §13). Empty => open (development only).
    node_join_token: str = ""
    node_offline_after_seconds: int = 60  # a node is "online" if seen within this

    # Authentication (spec §15). JWT secret MUST be set in production; when empty
    # an ephemeral per-process secret is generated (tokens reset on restart).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # Optional bootstrap admin, seeded on startup if it does not exist.
    admin_email: str = ""
    admin_password: str = ""

    @property
    def is_test(self) -> bool:
        return self.env.lower() in {"test", "testing"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    settings = Settings()
    if not settings.jwt_secret:
        # Ephemeral dev secret: keeps auth working without a committed secret,
        # but tokens are invalidated on restart. Set ATLAS_JWT_SECRET in prod.
        settings.jwt_secret = secrets.token_hex(32)
        logger.warning(
            "ATLAS_JWT_SECRET is not set; using an ephemeral secret. "
            "Set it in production so tokens survive restarts.",
            extra={"event": "jwt_secret_ephemeral"},
        )
    return settings
