"""Host hardware scan (spec §16 M2: hardware scan).

Standard-library only; degrades gracefully on non-Linux hosts. Used to inform
local model selection and shown in the UI.
"""

from __future__ import annotations

import os
import platform


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts and parts[0].isdigit():
                    values[key.strip()] = int(parts[0])
    except OSError:
        pass
    return values


def scan_hardware() -> dict[str, object]:
    mem = _read_meminfo()
    gpu = _detect_nvidia_gpu()
    return {
        "platform": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_cores": os.cpu_count(),
        "ram_total_mb": round(mem["MemTotal"] / 1024) if "MemTotal" in mem else None,
        "ram_available_mb": (
            round(mem["MemAvailable"] / 1024) if "MemAvailable" in mem else None
        ),
        "gpu": gpu,
    }


def _detect_nvidia_gpu() -> dict[str, object] | None:
    """Best-effort NVIDIA detection without adding dependencies."""

    import shutil
    import subprocess

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        out = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    gpus = []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2:
            name, vram = parts
            gpus.append({"name": name, "vram_mb": int(vram) if vram.isdigit() else None})
    return {"count": len(gpus), "devices": gpus} if gpus else None
