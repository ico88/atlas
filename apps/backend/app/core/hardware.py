"""Host hardware scan (spec §16 M2; ROADMAP PR 1 — multi-vendor GPU discovery).

Standard-library only; degrades gracefully. Detects GPUs across vendors and
backends so ATLAS can pick an Ollama backend even on hardware not covered by
NVIDIA's ``nvidia-smi``:

- NVIDIA  via ``nvidia-smi``
- AMD/ATI via ``lspci`` and Linux sysfs (vendor id 0x1002)
- Vulkan  via ``vulkaninfo --summary`` (physical devices only; software
  renderers such as ``llvmpipe``/``lavapipe`` are excluded, never counted as GPUs)
- ROCm    via ``rocminfo`` / ``rocm-smi`` when present
- DRM     by enumerating ``/dev/dri/renderD*``

Every external command has a timeout, bounded handling and tolerant parsing; a
missing optional command must never fail the health endpoint. Parsing functions
are pure (take text) so they are unit-testable without the tools installed.
"""

from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass

_SOFTWARE_RENDERERS = ("llvmpipe", "lavapipe", "softpipe", "swrast", "software")

_VENDOR_BY_ID = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


@dataclass
class GpuDevice:
    vendor: str
    name: str
    driver: str | None = None
    vulkan: bool = False
    rocm: bool = False
    vram_mb: int | None = None
    render_device: str | None = None


# --------------------------------------------------------------------------- #
# command runner
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], timeout: float = 5.0) -> str | None:
    """Run an external command, returning stdout or None (never raises)."""

    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return proc.stdout or ""


# --------------------------------------------------------------------------- #
# CPU / RAM
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# pure parsers (unit-testable)
# --------------------------------------------------------------------------- #
def parse_nvidia_smi(text: str) -> list[GpuDevice]:
    """Parse ``nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits``."""

    devices: list[GpuDevice] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts else "NVIDIA GPU"
        vram = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        devices.append(
            GpuDevice(vendor="nvidia", name=name, driver="nvidia", vulkan=True, vram_mb=vram)
        )
    return devices


def parse_vulkaninfo_summary(text: str) -> list[GpuDevice]:
    """Parse ``vulkaninfo --summary``; return only physical GPUs (no software)."""

    devices: list[GpuDevice] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if not current:
            return
        name = current.get("deviceName", "").strip()
        dtype = current.get("deviceType", "")
        driver_id = current.get("driverID", "") or current.get("driverName", "")
        vendor_id = current.get("vendorID", "").lower()
        if name and "CPU" not in dtype and not _is_software(name):
            devices.append(
                GpuDevice(
                    vendor=_vendor_from(vendor_id, name),
                    name=name,
                    driver=_driver_label(driver_id),
                    vulkan=True,
                )
            )

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^GPU\d+\s*:", stripped) or stripped in ("Devices:", "Devices :"):
            flush()
            current = {}
            continue
        m = re.match(r"([A-Za-z]+)\s*=\s*(.+)", stripped)
        if m:
            current[m.group(1)] = m.group(2).strip()
    flush()
    return devices


def parse_lspci(text: str) -> list[GpuDevice]:
    """Parse ``lspci -nn`` display controllers into devices."""

    devices: list[GpuDevice] = []
    for line in text.splitlines():
        if not re.search(r"(VGA compatible controller|3D controller|Display controller)", line):
            continue
        if _is_software(line):
            continue
        vendor = "unknown"
        for vid, vname in _VENDOR_BY_ID.items():
            if f"[{vid[2:]}:" in line.lower():
                vendor = vname
                break
        if vendor == "unknown":
            low = line.lower()
            if "nvidia" in low:
                vendor = "nvidia"
            elif "amd" in low or "ati" in low or "radeon" in low:
                vendor = "amd"
            elif "intel" in low:
                vendor = "intel"
        name = line.split(":", 2)[-1].strip() if ":" in line else line.strip()
        devices.append(GpuDevice(vendor=vendor, name=name[:200]))
    return devices


def _is_software(text: str) -> bool:
    low = text.lower()
    return any(sw in low for sw in _SOFTWARE_RENDERERS)


def _vendor_from(vendor_id: str, name: str) -> str:
    if vendor_id in _VENDOR_BY_ID:
        return _VENDOR_BY_ID[vendor_id]
    low = name.lower()
    if "nvidia" in low:
        return "nvidia"
    if "amd" in low or "radeon" in low or "ati" in low or "radv" in low:
        return "amd"
    if "intel" in low:
        return "intel"
    return "unknown"


def _driver_label(driver_id: str) -> str | None:
    if not driver_id:
        return None
    low = driver_id.lower()
    if "radv" in low:
        return "radv"
    if "amdvlk" in low:
        return "amdvlk"
    if "nvidia" in low:
        return "nvidia"
    if "intel" in low or "anv" in low:
        return "intel"
    return driver_id


def recommended_backend(devices: list[GpuDevice], rocm_available: bool) -> str:
    """Pick the Ollama backend: nvidia > rocm > vulkan > cpu."""

    if any(d.vendor == "nvidia" for d in devices):
        return "nvidia"
    if rocm_available and any(d.vendor == "amd" for d in devices):
        return "rocm"
    if any(d.vulkan for d in devices):
        return "vulkan"
    return "cpu"


# --------------------------------------------------------------------------- #
# detectors + merge
# --------------------------------------------------------------------------- #
def enumerate_render_devices() -> list[str]:
    return sorted(glob.glob("/dev/dri/renderD*"))


def detect_rocm() -> bool:
    out = _run(["rocminfo"]) or _run(["rocm-smi"])
    if out is None:
        return False
    return "gfx" in out.lower() or "GPU ID" in out


def scan_gpus() -> tuple[list[GpuDevice], bool]:
    """Merge all detectors into a de-duplicated device list; also return rocm flag."""

    nvidia = parse_nvidia_smi(
        _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        or ""
    )
    vulkan = parse_vulkaninfo_summary(_run(["vulkaninfo", "--summary"]) or "")
    rocm = detect_rocm()

    devices: list[GpuDevice] = list(nvidia)

    # Fold Vulkan info in: NVIDIA already covered by nvidia-smi (mark vulkan),
    # non-NVIDIA physical Vulkan devices (AMD/Intel) are added.
    for vk in vulkan:
        if vk.vendor == "nvidia":
            for d in devices:
                if d.vendor == "nvidia":
                    d.vulkan = True
            continue
        devices.append(vk)

    # If nothing yet, fall back to lspci so we at least report the GPU exists.
    if not devices:
        devices = parse_lspci(_run(["lspci", "-nn"]) or "")

    # Annotate AMD devices with ROCm availability and attach a render node.
    renders = enumerate_render_devices()
    for d in devices:
        if d.vendor == "amd":
            d.rocm = rocm
    if len(devices) == 1 and renders:
        devices[0].render_device = renders[0]

    return devices, rocm


def scan_hardware() -> dict[str, object]:
    """Full host hardware snapshot with structured GPU info."""

    mem = _read_meminfo()
    devices, rocm = scan_gpus()
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
        "gpu": {
            "count": len(devices),
            "devices": [asdict(d) for d in devices],
            "render_devices": enumerate_render_devices(),
            "rocm_available": rocm,
        },
        "recommended_ollama_backend": recommended_backend(devices, rocm),
    }
