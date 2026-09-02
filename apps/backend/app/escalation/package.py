"""Build the self-sufficient escalation package (spec §10).

The package is plain text the user copies into ChatGPT Plus / Claude Pro. The
platform never automates the browser/session — it only prepares text. Secrets
must never be included (§13); callers are responsible for passing redacted
context.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_CONSTRAINTS = (
    "Do not include secrets or credentials. Prefer a minimal, targeted change. "
    "Follow existing code style. Include a regression test."
)
_DEFAULT_OUTPUT = (
    "1) A unified diff (patch). 2) A short explanation. 3) Risk assessment. "
    "4) Any tests to run."
)
_DEFAULT_REQUEST = "Provide a minimal patch and analysis for the objective above."


@dataclass
class EscalationContext:
    project_context: str = ""
    environment: str = ""
    source_excerpts: str = ""
    logs: str = ""
    tests_executed: str = ""
    hypothesis: str = ""
    constraints: str = ""
    expected_output: str = ""
    request: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip() if body and body.strip() else '(none provided)'}\n"


def build_package(
    *, objective: str, target: str, correlation_id: str, context: EscalationContext | None = None
) -> str:
    ctx = context or EscalationContext()
    target_label = "ChatGPT Plus" if target == "chatgpt" else "Claude Pro"
    parts = [
        "EXTERNAL ESCALATION PACKAGE",
        f"Correlation ID: {correlation_id}",
        f"Target: {target_label}",
        "",
        _section("Task objective", objective),
        _section("Relevant project context", ctx.project_context),
        _section("Environment", ctx.environment),
        _section("Relevant source files or excerpts", ctx.source_excerpts),
        _section("Logs / stack trace", ctx.logs),
        _section("Tests already executed", ctx.tests_executed),
        _section("Current hypothesis", ctx.hypothesis),
        _section("Constraints", ctx.constraints or _DEFAULT_CONSTRAINTS),
        _section("Expected output format", ctx.expected_output or _DEFAULT_OUTPUT),
        _section("Request for patch / analysis", ctx.request or _DEFAULT_REQUEST),
    ]
    return "\n".join(parts).strip() + "\n"
