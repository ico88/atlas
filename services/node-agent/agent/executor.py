"""Task executor for the node agent (spec §8, remote execution).

Sprint-scope executor: it simulates the unit of work for the task's capability
and returns a result payload. The one real capability wired here is
``model_pull`` — the control plane can tell a node to download a model into its
local Ollama (one-click model distribution from the ATLAS setup UI). Other
capability-specific executors (build, test, llm, …) plug in the same way.
Honors ``payload.fail`` so failures can be tested.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger("node-agent")

ProgressCb = Callable[[int, str], Awaitable[None]]


def pull_percent(chunk: dict[str, Any]) -> int | None:
    """Pure: derive a 0..100 percent from one Ollama pull chunk, or None."""

    total = chunk.get("total")
    completed = chunk.get("completed")
    if isinstance(total, int | float) and total and isinstance(completed, int | float):
        return max(0, min(100, int(completed / total * 100)))
    return None


async def pull_model(
    ollama_url: str,
    model: str,
    timeout: float = 1800.0,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Download a model into the node's local Ollama. Streams to completion,
    reporting progress (throttled to ~5% steps) via ``on_progress`` if given."""

    url = ollama_url.rstrip("/") + "/api/pull"
    last_pct = -5
    try:
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", url, json={"model": model, "stream": True}) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    return {"status": "failed", "error": chunk["error"]}
                if on_progress is not None:
                    pct = pull_percent(chunk)
                    status = str(chunk.get("status") or "")
                    if pct is not None and pct - last_pct >= 5:
                        last_pct = pct
                        await on_progress(pct, status)
        if on_progress is not None:
            await on_progress(100, "done")
        return {"status": "completed", "result": {"pulled": model}}
    except (httpx.HTTPError, OSError) as exc:
        return {"status": "failed", "error": f"ollama pull failed: {exc}"}


async def execute_task(
    task: dict[str, Any],
    work_seconds: float = 0.05,
    ollama_url: str = "http://localhost:11434",
    progress_cb: ProgressCb | None = None,
) -> dict[str, Any]:
    payload = task.get("payload") or {}
    if payload.get("fail"):
        return {"status": "failed", "error": "forced failure (payload.fail)"}

    if task.get("type") == "model_pull":
        model = str(payload.get("model") or "").strip()
        if not model:
            return {"status": "failed", "error": "model_pull: no model in payload"}
        endpoint = str(payload.get("ollama_url") or ollama_url)
        logger.info("pulling model %s via %s", model, endpoint)
        return await pull_model(endpoint, model, on_progress=progress_cb)

    await asyncio.sleep(work_seconds)
    return {
        "status": "completed",
        "result": {
            "executed_by": "node-agent",
            "capability": task.get("required_capability"),
            "echo": payload,
        },
    }
