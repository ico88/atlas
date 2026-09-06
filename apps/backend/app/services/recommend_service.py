"""Model recommendation from detected hardware (guided setup).

Pure, testable logic: given a hardware snapshot (``scan_hardware``), suggest a
primary local model plus alternatives, each sized to fit and with a plain-language
note. Tuned for the local-first, Italian-speaking use case (qwen2.5 is strong in
Italian); the goal is that a normal user never has to guess a model name.
"""

from __future__ import annotations

from typing import Any

# Catalog, roughly ordered strongest -> lightest. min_ram_mb is a conservative
# floor for a Q4 quant on CPU; vram_mb is what a GPU needs to run it comfortably.
CATALOG: list[dict[str, Any]] = [
    {
        "model": "qwen2.5:7b",
        "label": "Qwen2.5 7B",
        "size_gb": 4.7,
        "min_ram_mb": 16000,
        "vram_mb": 8000,
        "note": "Qualità migliore, ottimo in italiano. Ideale con GPU o molta RAM.",
        "capabilities": ["CHAT", "REASONING", "CODING", "SUMMARIZATION", "TRANSLATION", "RAG"],
    },
    {
        "model": "qwen2.5:3b",
        "label": "Qwen2.5 3B",
        "size_gb": 2.0,
        "min_ram_mb": 8000,
        "vram_mb": 4000,
        "note": "Ottimo equilibrio qualità/velocità, molto buono in italiano. Consigliato.",
        "capabilities": ["CHAT", "REASONING", "SUMMARIZATION", "TRANSLATION", "RAG"],
    },
    {
        "model": "llama3.2:3b",
        "label": "Llama 3.2 3B",
        "size_gb": 2.0,
        "min_ram_mb": 8000,
        "vram_mb": 4000,
        "note": "Alternativa leggera e capace.",
        "capabilities": ["CHAT", "REASONING", "SUMMARIZATION"],
    },
    {
        "model": "gemma2:2b",
        "label": "Gemma2 2B",
        "size_gb": 1.6,
        "min_ram_mb": 6000,
        "vram_mb": 3000,
        "note": "Veloce, adatto a macchine modeste.",
        "capabilities": ["CHAT", "SUMMARIZATION"],
    },
    {
        "model": "llama3.2:1b",
        "label": "Llama 3.2 1B",
        "size_gb": 1.3,
        "min_ram_mb": 3000,
        "vram_mb": 2000,
        "note": "Minimo indispensabile: gira ovunque, qualità limitata.",
        "capabilities": ["CHAT"],
    },
]

_EMBEDDING = {
    "model": "nomic-embed-text",
    "label": "nomic-embed-text",
    "size_gb": 0.3,
    "note": "Piccolo modello per la memoria/RAG (ricerca semantica).",
    "capabilities": ["EMBEDDINGS"],
}


def _best_vram_mb(hw: dict) -> int:
    gpu = hw.get("gpu") or {}
    devices = gpu.get("devices") or []
    vrams = [d.get("vram_mb") or 0 for d in devices]
    return max(vrams) if vrams else 0


def recommend_models(hw: dict) -> dict[str, Any]:
    """Return {primary, alternatives, embedding, reason} for this hardware.

    A model fits if the GPU has enough VRAM, or (CPU path) there is enough RAM.
    The primary is the strongest model that fits; everything lighter that also
    fits is offered as an alternative.
    """

    ram = int(hw.get("ram_total_mb") or 0)
    vram = _best_vram_mb(hw)
    has_gpu = bool((hw.get("gpu") or {}).get("count"))

    def fits(entry: dict) -> bool:
        if vram > 0:
            return vram >= entry["vram_mb"]
        return ram >= entry["min_ram_mb"]

    fitting = [e for e in CATALOG if fits(e)]
    if not fitting:
        # Nothing "fits" our floors -> still offer the tiniest model.
        fitting = [CATALOG[-1]]

    primary = fitting[0]
    alternatives = fitting[1:]

    if vram > 0:
        reason = (
            f"GPU con ~{vram // 1000} GB di VRAM rilevata: puoi usare un modello più capace."
            if has_gpu
            else ""
        )
    elif ram:
        reason = f"~{ram // 1000} GB di RAM (CPU): scelto un modello che gira fluido senza GPU."
    else:
        reason = "Hardware non rilevato con certezza: scelta prudente."

    return {
        "primary": primary,
        "alternatives": alternatives,
        "embedding": _EMBEDDING,
        "reason": reason,
        "detected": {"ram_total_mb": ram, "best_vram_mb": vram, "has_gpu": has_gpu},
    }
