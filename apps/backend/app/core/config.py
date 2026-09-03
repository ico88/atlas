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
    delayed_queue_key: str = "atlas:queue:delayed"
    worker_poll_timeout: int = 5  # seconds for blocking pop
    worker_dummy_duration: float = 0.2  # simulated work time for dummy tasks

    # Concurrency limits (spec §7). 0 == unlimited for that scope.
    max_concurrent_global: int = 0
    max_concurrent_per_user: int = 0
    max_concurrent_per_type: int = 0
    concurrency_retry_delay: float = 0.5  # requeue delay when a slot is unavailable

    # Conversation queue (ROADMAP PR 11). Each conversation processes one turn at
    # a time; this caps how many *different* conversations run in parallel.
    conversation_max_parallel: int = 4  # 0 == unlimited

    # Retry policy (spec §7: exponential backoff + jitter, no infinite loops).
    task_max_retries: int = 3
    retry_backoff_base: float = 0.5  # seconds; delay = base * 2**(attempt-1) + jitter
    retry_backoff_max: float = 30.0
    retry_jitter: float = 0.2

    # Resilient scheduler (ROADMAP PR 8). A RUNNING task holds a lease for this
    # many seconds; if it is not renewed (worker/node crash) the scheduler
    # reclaims and re-queues it. 0 disables reclaiming.
    task_lease_seconds: float = 60.0
    scheduler_reclaim_enabled: bool = True

    # Resource telemetry (ROADMAP PR 12). Samples per node kept before pruning.
    metrics_history_limit: int = 500

    # Node federation (spec §8). A shared join token authenticates nodes against
    # the control plane (least privilege, §13). Empty => open (development only).
    node_join_token: str = ""
    node_offline_after_seconds: int = 60  # a node is "online" if seen within this
    # Per-node enrollment with an approval gate (ROADMAP PR 6). When True, nodes
    # must present a valid enrollment token and be APPROVED before claiming work.
    # Off by default so the shared-join-token flow keeps working unchanged.
    node_enrollment_required: bool = False

    # Authentication (spec §15). JWT secret MUST be set in production; when empty
    # an ephemeral per-process secret is generated (tokens reset on restart).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # Optional bootstrap admin, seeded on startup if it does not exist.
    admin_email: str = ""
    admin_password: str = ""

    # Local AI (spec §4, §9, M2). Empty ollama_url disables Ollama (echo only).
    ollama_url: str = "http://ollama:11434"
    default_model: str = ""  # empty => auto-pick the first available model
    chat_stream_delay: float = 0.02  # seconds between echo tokens (0 in tests)

    # RAG / Memory (spec §6, §8, M8).
    embedding_dim: int = 256  # dimension of the local hashing embedder
    embedding_model: str = "nomic-embed-text"  # Ollama model when available
    use_ollama_embeddings: bool = False  # opt-in; default = deterministic local
    rag_chunk_size: int = 800  # characters per chunk
    rag_chunk_overlap: int = 100
    rag_top_k: int = 5
    # Memory lifecycle (ROADMAP PR 14). Default TTL for new memories in seconds
    # (0 = never expire); pinned memories ignore it.
    memory_default_ttl_seconds: int = 0

    # Web tools (spec §6 web; ROADMAP PR 15). Disabled by default: the platform
    # is local-first and must not reach the internet unless the operator opts in.
    web_tools_enabled: bool = False
    web_search_provider: str = "none"  # none | searxng | json
    web_search_url: str = ""  # e.g. http://searxng:8080/search
    web_search_api_key: str = ""
    web_max_results: int = 5
    web_fetch_timeout: float = 10.0  # seconds per request
    web_fetch_max_bytes: int = 2_000_000  # hard cap on a fetched body (SSRF/DoS guard)
    web_allow_private_ips: bool = False  # allow RFC1918/loopback targets (dev only)
    # Comma-separated host suffixes. Allowlist (if set) wins; denylist always blocks.
    web_domain_allowlist: str = ""
    web_domain_denylist: str = ""
    web_user_agent: str = "ATLAS-WebTools/1.0 (+local-first)"

    @property
    def web_allowlist(self) -> list[str]:
        return [h.strip().lower() for h in self.web_domain_allowlist.split(",") if h.strip()]

    @property
    def web_denylist(self) -> list[str]:
        return [h.strip().lower() for h in self.web_domain_denylist.split(",") if h.strip()]

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
