"""
GPU/Docker Readiness Detection

Simple startup probe to detect GPU availability and provide fallback hints.
Never throws — all failures are captured in hints.

Queries the Ollama REST API (/api/ps) directly instead of relying on CLI
tools that may not be available inside containers.
"""

import os
import shutil
import urllib.request
import urllib.error
import json as json_mod
from typing import Dict, Any


def detect_gpu() -> Dict[str, Any]:
    """
    Detect GPU availability and Ollama GPU usage.

    Returns:
        dict with keys:
        - nvidia_smi_available: bool — True if nvidia-smi is executable in PATH
        - ollama_uses_gpu: bool|None — True if Ollama reports VRAM usage,
                                       False if running but no VRAM,
                                       None if not reachable
        - hints: list[str] — human-readable diagnostic messages
    """
    result = {
        "nvidia_smi_available": False,
        "ollama_uses_gpu": None,
        "hints": []
    }

    # 1. Check nvidia-smi availability (best-effort, container may lack it)
    try:
        if shutil.which("nvidia-smi"):
            result["nvidia_smi_available"] = True
    except Exception as e:
        result["hints"].append(f"Error checking nvidia-smi: {e}")

    # 2. Query Ollama REST API for GPU usage
    # Ollama /api/ps returns "size_vram" per loaded model — the most reliable
    # GPU signal without needing nvidia-smi or ollama CLI in the container.
    #
    # Derive the Ollama base URL with the same logic as _get_ollama_status()
    # in api/status.py: strip /v1 from LLM_BASE_URL, fall back to OLLAMA_BASE_URL.
    from ..config import Config
    ollama_base = (Config.LLM_BASE_URL or '').rstrip('/')
    if ollama_base.endswith('/v1'):
        ollama_base = ollama_base[:-3]
    if not ollama_base:
        ollama_base = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    ps_url = f"{ollama_base}/api/ps"

    try:
        req = urllib.request.Request(ps_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json_mod.loads(resp.read().decode('utf-8'))
        models = data.get("models", [])
        total_vram = sum(m.get("size_vram", 0) for m in models)
        if total_vram > 0:
            result["ollama_uses_gpu"] = True
            vram_gb = total_vram / (1024**3)
            result["hints"].append(f"Ollama GPU aktiv — {vram_gb:.1f} GB VRAM belegt ({len(models)} Modell(e) geladen)")
        elif models:
            result["ollama_uses_gpu"] = False
            result["hints"].append("Ollama läuft, aber keine Modelle mit GPU geladen (size_vram=0)")
        else:
            result["ollama_uses_gpu"] = False
            result["hints"].append("Ollama erreichbar, aber keine Modelle geladen")
    except urllib.error.URLError as e:
        result["hints"].append(f"Ollama-API nicht erreichbar ({ps_url}): {e}")
    except Exception as e:
        result["hints"].append(f"Fehler bei Ollama-GPU-Abfrage: {e}")

    # 3. Consolidate hints
    if not result["nvidia_smi_available"] and result["ollama_uses_gpu"] is None:
        result["hints"].append("Ollama nicht erreichbar — GPU-Status unbekannt. Läuft Ollama?")

    return result
