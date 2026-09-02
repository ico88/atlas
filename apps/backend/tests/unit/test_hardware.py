"""Unit tests for the multi-vendor GPU scanner (ROADMAP PR 1)."""

from __future__ import annotations

from app.core.hardware import (
    GpuDevice,
    parse_lspci,
    parse_nvidia_smi,
    parse_vulkaninfo_summary,
    recommended_backend,
    scan_hardware,
)

VULKANINFO_AMD = """
Devices:
========
GPU0:
    apiVersion     = 1.3.255
    driverVersion  = 23.1.0
    vendorID       = 0x1002
    deviceID       = 0x6810
    deviceType     = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
    deviceName     = AMD Radeon R9 200 Series (RADV PITCAIRN)
    driverID       = DRIVER_ID_MESA_RADV
GPU1:
    vendorID       = 0x10005
    deviceType     = PHYSICAL_DEVICE_TYPE_CPU
    deviceName     = llvmpipe (LLVM 15.0.0, 256 bits)
    driverID       = DRIVER_ID_MESA_LLVMPIPE
"""


def test_vulkaninfo_excludes_llvmpipe_and_cpu():
    devices = parse_vulkaninfo_summary(VULKANINFO_AMD)
    assert len(devices) == 1
    d = devices[0]
    assert d.vendor == "amd"
    assert "RADV PITCAIRN" in d.name
    assert d.driver == "radv"
    assert d.vulkan is True


def test_nvidia_smi_parsing():
    devices = parse_nvidia_smi("NVIDIA GeForce RTX 3090, 24576\n")
    assert len(devices) == 1
    assert devices[0].vendor == "nvidia"
    assert devices[0].vram_mb == 24576
    assert devices[0].vulkan is True


def test_lspci_amd_parsing():
    text = (
        "01:00.0 VGA compatible controller [0300]: "
        "Advanced Micro Devices, Inc. [AMD/ATI] Pitcairn [Radeon R9 270X] [1002:6810]\n"
    )
    devices = parse_lspci(text)
    assert len(devices) == 1
    assert devices[0].vendor == "amd"


def test_lspci_skips_software_renderer():
    assert parse_lspci("00:02.0 VGA compatible controller: llvmpipe\n") == []


def test_recommended_backend_priority():
    nvidia = [GpuDevice(vendor="nvidia", name="RTX", vulkan=True)]
    amd_vk = [GpuDevice(vendor="amd", name="Radeon", vulkan=True)]
    assert recommended_backend(nvidia, rocm_available=False) == "nvidia"
    assert recommended_backend(amd_vk, rocm_available=True) == "rocm"
    assert recommended_backend(amd_vk, rocm_available=False) == "vulkan"
    assert recommended_backend([], rocm_available=False) == "cpu"


def test_scan_hardware_shape_no_crash():
    hw = scan_hardware()
    assert "cpu_cores" in hw
    assert "recommended_ollama_backend" in hw
    gpu = hw["gpu"]
    assert {"count", "devices", "render_devices", "rocm_available"} <= set(gpu)
    # On CI/dev without a GPU: count 0 and cpu backend, but never an exception.
    assert isinstance(gpu["count"], int)
