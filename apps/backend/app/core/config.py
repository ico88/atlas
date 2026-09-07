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

    # Self-healing (ROADMAP PR 17). The maintenance agent validates a proposed
    # fix in a real, isolated sandbox before asking for approval, and only after
    # a human approves does it (optionally) open a real PR — never touching the
    # working repo, never pushing to a protected branch, never merging.
    maintenance_sandbox_enabled: bool = True  # run the real patch+test sandbox
    maintenance_sandbox_timeout: float = 120.0  # seconds per validation command
    # Operator-configured validation command run inside the sandbox (never taken
    # from an API request). Empty => apply-only check (patch must apply cleanly).
    maintenance_check_command: str = ""
    # Real GitHub-backed git actions. OFF by default: the loop stays dry-run and
    # never mutates a real repository until an operator opts in AND a human
    # approves the specific fix. Guardrails (no push_main/merge/force_push) apply
    # to the real provider exactly as they do to the dry-run one.
    maintenance_github_enabled: bool = False
    maintenance_github_token: str = ""
    maintenance_github_repo: str = ""  # "owner/repo" for the opened PR
    maintenance_github_api: str = "https://api.github.com"

    # Semi-automatic loops (ROADMAP PR 17/18 UX). When enabled, the analysis /
    # experiment phases run by themselves in the background so a human is left
    # with only the approve/apply decision. Irreversible steps (open PR, change
    # the default model) still require explicit human approval — governance is
    # never bypassed.
    maintenance_auto_fix_enabled: bool = True  # ingest -> analyze -> sandbox fix
    improvement_auto_experiment_enabled: bool = True  # create -> run experiment
    # Fully autonomous proposer: ATLAS generates improvement proposals by itself
    # (e.g. try each available model as the default) on a timer, then the
    # auto-experiment runs them to a verdict + approval gate. Only the final
    # apply stays human-gated. The loop is a no-op until there is an eval suite
    # and at least one alternative model, so it is safe to leave on.
    improvement_auto_propose_enabled: bool = True
    improvement_auto_propose_interval: float = 3600.0  # seconds between sweeps

    # Critical review (ROADMAP PR 19). A proposer/critic/verifier/judge pipeline
    # runs up to N rounds and stops early once a candidate clears the accept
    # threshold (adaptive consensus).
    review_max_rounds: int = 3  # candidates to try before picking the best
    review_accept_threshold: float = 0.8  # score >= this => accept (stop early)
    review_revise_threshold: float = 0.5  # score >= this => revise, else reject
    review_min_answer_chars: int = 40  # shorter candidates are flagged as thin

    # Control-plane HA (ROADMAP PR 9). When enabled, instances elect a leader via
    # a Redis lease; only the leader runs singleton background work (e.g. the
    # autonomous proposer). Off => single-node: this instance is always leader.
    ha_enabled: bool = False
    instance_id: str = ""  # stable id for this instance (defaults to host+pid)
    ha_lease_ttl: int = 30  # seconds; leader renews within this, failover after it

    # ZeroTier controller (ROADMAP PR 7). OFF by default: the overlay works via
    # the installer's join flow without the control plane touching ZeroTier
    # Central. Enable to let ATLAS list/authorize members of a network through the
    # ZeroTier Central API (member authorization is audited).
    zerotier_controller_enabled: bool = False
    zerotier_api_token: str = ""
    zerotier_network_id: str = ""
    zerotier_api: str = "https://api.zerotier.com/api/v1"
    # When true, a member joining the network is auto-authorized by the controller
    # (convenience); when false, an operator authorizes each member explicitly.
    zerotier_auto_authorize: bool = False

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
    # Secret manager master key (ROADMAP R5): a urlsafe-base64 32-byte Fernet key
    # (openssl rand -base64 32). Empty => derived from jwt_secret (dev/test).
    secret_key: str = ""
    access_token_expire_minutes: int = 60 * 12
    # RBAC enforcement (ROADMAP PR 27). Off by default keeps the local-first,
    # single-operator experience (endpoints open, everyone treated as admin).
    # Turn on for multi-user: management endpoints then require an admin token
    # and roles are enforced (admin manages everything, user just uses the app).
    auth_enforce: bool = False

    # Optional bootstrap admin, seeded on startup if it does not exist.
    admin_email: str = ""
    admin_password: str = ""

    # Local AI (spec §4, §9, M2). Empty ollama_url disables Ollama (echo only).
    ollama_url: str = "http://ollama:11434"
    default_model: str = ""  # empty => auto-pick the first available model
    chat_stream_delay: float = 0.02  # seconds between echo tokens (0 in tests)
    # Responsiveness tuning (keeps the model hot and bounds the work per turn).
    ollama_keep_alive: str = "30m"  # keep the model resident between turns
    ollama_num_ctx: int = 4096  # context window sent to Ollama (0 = server default)
    # Max tokens per reply. -1 = unlimited (never truncate long answers); set a
    # positive cap only if you want to bound latency at the cost of completeness.
    ollama_num_predict: int = -1
    chat_history_limit: int = 20  # max prior messages sent as context (0 = all)
    ai_available_cache_seconds: float = 30.0  # cache Ollama reachability probe
    # Automatic memory: capture durable facts from chat and recall them as context.
    chat_memory_enabled: bool = True
    chat_memory_top_k: int = 5  # how many known facts to inject per turn

    # Multi-runtime routing (Fase 1). When runtimes + deployments are registered,
    # the Model Gateway scores candidates and picks model×runtime×node. Absent any
    # deployment, chat keeps the classic Ollama-or-echo behaviour (no regression).
    # Prefer local deployments over cloud when both qualify.
    routing_local_first: bool = True
    # Global default: are cloud runtimes (OpenAI/Anthropic) eligible at all?
    # Privacy LOCAL_ONLY on a request always overrides this to False.
    routing_cloud_allowed: bool = False
    # Runtime-type preference, most-preferred first (a soft bias, not absolute).
    runtime_priority: list[str] = ["llama_cpp", "ollama", "openai_compat", "vllm"]
    # Circuit breaker (Fase 2): after N consecutive failures a runtime is skipped
    # for a cooldown, then probed to recover — a repeatedly-failing engine is
    # routed around instead of retried forever.
    runtime_circuit_threshold: int = 5
    runtime_circuit_cooldown: float = 30.0
    # Best-effort retries against transient runtime errors (0 = none).
    runtime_max_retries: int = 1
    # Benchmark probe: max tokens to generate when measuring tokens/sec.
    runtime_benchmark_max_tokens: int = 64

    # Service-level objectives (ROADMAP R5). Targets the SLO report checks; a value
    # below target raises an advisory alert on the Admin page.
    slo_task_success_target: float = 0.95  # completed / (completed + failed)
    slo_nodes_online_target: float = 0.90  # online / total (when nodes exist)

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
