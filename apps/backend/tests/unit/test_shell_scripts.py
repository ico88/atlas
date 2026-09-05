"""Shell-script checks for the atlas CLI + libs (ROADMAP PR 3 / PR 20).

Runs from Python so it's covered by the normal test run/CI. Verifies syntax,
the pure helper logic (model prune selection, name validation, GPU config
detection), and that the CLI advertises the new commands.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
ATLAS = REPO / "atlas"
LIB = REPO / "infrastructure" / "scripts" / "lib"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not ATLAS.exists(),
    reason="bash or atlas CLI not available",
)


def _bash(script: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_all_shell_scripts_have_valid_syntax():
    files = [ATLAS, *sorted(LIB.glob("*.sh")), REPO / "infrastructure/scripts/install.sh"]
    for f in files:
        r = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"syntax error in {f}: {r.stderr}"


def test_models_to_prune_keeps_protected():
    r = _bash(
        "source infrastructure/scripts/lib/ollama.sh; "
        'models_to_prune "qwen2.5:3b" "nomic-embed-text"',
        stdin="qwen2.5:3b\nnomic-embed-text\nmistral:7b\nllama3.2:1b\n",
    )
    assert r.returncode == 0
    removed = set(r.stdout.split())
    assert removed == {"mistral:7b", "llama3.2:1b"}


def test_validate_model_name_blocks_injection():
    r = _bash(
        "source infrastructure/scripts/lib/ollama.sh; "
        'validate_model_name "qwen2.5:3b" && echo ok; '
        "validate_model_name 'evil; rm -rf /' || echo blocked",
    )
    assert "ok" in r.stdout and "blocked" in r.stdout


def test_gpu_backend_configured(tmp_path):
    # No override -> cpu.
    r = _bash(
        "source infrastructure/scripts/lib/atlas-lib.sh; "
        "source infrastructure/scripts/lib/gpu.sh; "
        f"gpu_backend_configured {tmp_path}",
    )
    assert r.stdout.strip() == "cpu"
    # nvidia override -> nvidia.
    atlas_dir = tmp_path / ".atlas"
    atlas_dir.mkdir()
    (atlas_dir / "docker-compose.gpu.yml").write_text(
        "services:\n  ollama:\n    deploy:\n      resources:\n"
        "        reservations:\n          devices:\n            - driver: nvidia\n"
    )
    r = _bash(
        "source infrastructure/scripts/lib/atlas-lib.sh; "
        "source infrastructure/scripts/lib/gpu.sh; "
        f"gpu_backend_configured {tmp_path}",
    )
    assert r.stdout.strip() == "nvidia"


def test_cli_help_lists_new_commands():
    r = _bash("./atlas help")
    for token in ("model-prune", "gpu-status", "update --resume"):
        assert token in r.stdout, f"'{token}' missing from atlas help"


# --------------------------------------------------------------------------- #
# AMD acceleration proof (ROADMAP PR 26 — Quality).
# The AMD path is real, not a stub: generate_gpu_override writes a working Ollama
# device mapping for Vulkan and ROCm, and gpu_backend_configured reads it back.
# --------------------------------------------------------------------------- #
def _gpu(tmp_path, cmd):
    return _bash(
        "source infrastructure/scripts/lib/atlas-lib.sh 2>/dev/null; "
        "source infrastructure/scripts/lib/gpu.sh; " + cmd
    )


def test_amd_vulkan_override_is_generated_and_detected(tmp_path):
    r = _gpu(tmp_path, f"generate_gpu_override {tmp_path} vulkan")
    assert r.returncode == 0, r.stderr
    out = (tmp_path / ".atlas" / "docker-compose.gpu.yml").read_text()
    # A real Ollama GPU mapping: the render device is passed through and Vulkan on.
    assert "/dev/dri:/dev/dri" in out
    assert 'OLLAMA_VULKAN: "1"' in out
    # And it round-trips back to the same backend.
    r = _gpu(tmp_path, f"gpu_backend_configured {tmp_path}")
    assert r.stdout.strip() == "vulkan"


def test_amd_rocm_override_maps_kfd_when_present(tmp_path):
    r = _gpu(tmp_path, f"generate_gpu_override {tmp_path} rocm")
    assert r.returncode == 0, r.stderr
    out = (tmp_path / ".atlas" / "docker-compose.gpu.yml").read_text()
    assert "/dev/dri:/dev/dri" in out
    # ROCm needs /dev/kfd; it is mapped only when the host actually exposes it.
    if Path("/dev/kfd").exists():
        assert "/dev/kfd:/dev/kfd" in out
        r = _gpu(tmp_path, f"gpu_backend_configured {tmp_path}")
        assert r.stdout.strip() == "rocm"


def test_cpu_backend_removes_override(tmp_path):
    _gpu(tmp_path, f"generate_gpu_override {tmp_path} nvidia")
    assert (tmp_path / ".atlas" / "docker-compose.gpu.yml").exists()
    _gpu(tmp_path, f"generate_gpu_override {tmp_path} cpu")
    assert not (tmp_path / ".atlas" / "docker-compose.gpu.yml").exists()
    r = _gpu(tmp_path, f"gpu_backend_configured {tmp_path}")
    assert r.stdout.strip() == "cpu"
