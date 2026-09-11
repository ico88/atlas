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
import os
import shutil
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


def count_records(training_data: str) -> int:
    """Pure: number of non-blank JSONL training records."""

    return sum(1 for line in (training_data or "").splitlines() if line.strip())


def simulated_metrics(n: int, epochs: int) -> dict[str, Any]:
    """Deterministic training metrics for a dry-run/simulated LoRA.

    Loss decays with the amount of data and epochs seen; purely illustrative so
    the pipeline is exercisable end-to-end without a GPU. Real training replaces
    this with metrics reported by the trainer.
    """

    steps = max(1, n * max(1, epochs))
    final_loss = round(2.0 / (1.0 + steps / 8.0), 4)
    return {"examples": n, "epochs": epochs, "steps": steps, "final_loss": final_loss}


def gpu_available() -> bool:
    """Best-effort: is a GPU trainer plausibly present on this node?"""

    if os.environ.get("ATLAS_TRAIN_CMD"):
        return True
    return bool(shutil.which("nvidia-smi") or shutil.which("rocminfo"))


async def run_fine_tune(
    payload: dict[str, Any], on_progress: ProgressCb | None = None
) -> dict[str, Any]:
    """Train a LoRA adapter from the task payload's JSONL training data.

    Honest by design: real training needs a GPU + a trainer, so unless the node
    is explicitly asked to ``simulate`` (dry-run / tests) or has a configured
    trainer, this reports failure instead of pretending. When a trainer command
    is configured via ``ATLAS_TRAIN_CMD`` the real path is taken.
    """

    base_model = str(payload.get("base_model") or "").strip()
    adapter_name = str(payload.get("adapter_name") or "").strip()
    training_data = str(payload.get("training_data") or "")
    if not base_model or not adapter_name:
        return {"status": "failed", "error": "fine_tune: base_model and adapter_name required"}
    n = count_records(training_data)
    if n == 0:
        return {"status": "failed", "error": "fine_tune: no training records"}
    hyper = payload.get("hyperparams") or {}
    epochs = int(hyper.get("epochs", 3))

    if payload.get("simulate"):
        for pct in (10, 40, 70, 100):
            if on_progress is not None:
                await on_progress(pct, "training" if pct < 100 else "done")
        return {
            "status": "completed",
            "result": {
                "model": adapter_name,
                "base_model": base_model,
                "adapter": f"{adapter_name}.lora",
                "metrics": simulated_metrics(n, epochs),
                "simulated": True,
            },
        }

    cmd = os.environ.get("ATLAS_TRAIN_CMD")
    if not cmd:
        return {
            "status": "failed",
            "error": (
                "fine_tune: no local training backend. Fine-tuning requires a GPU "
                "and a trainer; set ATLAS_TRAIN_CMD on the node, or dispatch with "
                "simulate=true for a dry run."
            ),
        }
    return await _run_trainer(cmd, payload, n, epochs, on_progress)


async def _run_trainer(
    cmd: str,
    payload: dict[str, Any],
    n: int,
    epochs: int,
    on_progress: ProgressCb | None,
) -> dict[str, Any]:
    """Invoke the configured trainer command, passing the JSONL on stdin.

    The trainer is expected to print a final JSON line with at least ``model``
    (the registered adapter tag) and optional ``metrics``.
    """

    if on_progress is not None:
        await on_progress(5, "starting trainer")
    env = {
        **os.environ,
        "ATLAS_FT_BASE_MODEL": str(payload.get("base_model") or ""),
        "ATLAS_FT_ADAPTER_NAME": str(payload.get("adapter_name") or ""),
        "ATLAS_FT_EPOCHS": str(epochs),
    }
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        out, _ = await proc.communicate(str(payload.get("training_data") or "").encode())
    except OSError as exc:
        return {"status": "failed", "error": f"fine_tune: trainer failed to start: {exc}"}
    if proc.returncode != 0:
        tail = out.decode(errors="replace")[-500:]
        return {"status": "failed", "error": f"fine_tune: trainer exited {proc.returncode}: {tail}"}
    result: dict[str, Any] = {"model": payload.get("adapter_name"), "metrics": {"examples": n}}
    for line in reversed(out.decode(errors="replace").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                result = {**result, **json.loads(line)}
                break
            except json.JSONDecodeError:
                continue
    if on_progress is not None:
        await on_progress(100, "done")
    return {"status": "completed", "result": result}


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

    if task.get("type") == "fine_tune":
        logger.info("fine-tuning %s from %s", payload.get("adapter_name"), payload.get("base_model"))
        return await run_fine_tune(payload, on_progress=progress_cb)

    await asyncio.sleep(work_seconds)
    return {
        "status": "completed",
        "result": {
            "executed_by": "node-agent",
            "capability": task.get("required_capability"),
            "echo": payload,
        },
    }
