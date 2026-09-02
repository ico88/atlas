"""Task executor for the node agent (spec §8, remote execution).

Sprint-scope executor: it simulates the unit of work for the task's capability
and returns a result payload. Real capability-specific executors (build, test,
llm, …) plug in here later. Honors ``payload.fail`` so failures can be tested.
"""

from __future__ import annotations

import asyncio
from typing import Any


async def execute_task(task: dict[str, Any], work_seconds: float = 0.05) -> dict[str, Any]:
    payload = task.get("payload") or {}
    await asyncio.sleep(work_seconds)
    if payload.get("fail"):
        return {"status": "failed", "error": "forced failure (payload.fail)"}
    return {
        "status": "completed",
        "result": {
            "executed_by": "node-agent",
            "capability": task.get("required_capability"),
            "echo": payload,
        },
    }
