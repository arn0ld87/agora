"""
GPU/Docker Readiness Detection

Simple startup probe to detect GPU availability and provide fallback hints.
Never throws — all failures are captured in hints.
"""

import shutil
import subprocess
from typing import Dict, Any


def detect_gpu() -> Dict[str, Any]:
    """
    Detect GPU availability and Ollama GPU usage.

    Returns:
        dict with keys:
        - nvidia_smi_available: bool — True if nvidia-smi is executable in PATH
        - ollama_uses_gpu: bool|None — True if Ollama appears to use GPU,
                                       False if CPU-only detected,
                                       None if not determinable
        - hints: list[str] — human-readable diagnostic messages
    """
    result = {
        "nvidia_smi_available": False,
        "ollama_uses_gpu": None,
        "hints": []
    }

    # 1. Check nvidia-smi availability
    try:
        if shutil.which("nvidia-smi"):
            result["nvidia_smi_available"] = True
        else:
            result["hints"].append("nvidia-smi not found in PATH — GPU acceleration unavailable")
    except Exception as e:
        result["hints"].append(f"Error checking nvidia-smi: {e}")

    # 2. Try to detect Ollama GPU usage
    # Heuristic: call `ollama ps` to see if models are loaded; if they exist, assume GPU attempt
    try:
        # Ollama CLI endpoint for process listing
        proc = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0 and proc.stdout.strip():
            # Non-empty output suggests Ollama is running
            # We assume if it's running with models loaded, it's attempting GPU use if available
            if "NAME" in proc.stdout:
                result["ollama_uses_gpu"] = True
                result["hints"].append("Ollama process(es) detected — may use GPU if CUDA available")
            else:
                result["ollama_uses_gpu"] = False
                result["hints"].append("Ollama running but no models loaded")
        else:
            result["ollama_uses_gpu"] = False
            result["hints"].append("Ollama not running or no models loaded")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        result["hints"].append(f"Cannot determine Ollama GPU state: {e}")
    except Exception as e:
        result["hints"].append(f"Unexpected error probing Ollama: {e}")

    # 3. Consolidate hints
    if not result["nvidia_smi_available"] and result["ollama_uses_gpu"] is None:
        result["hints"].append("Running in CPU-only mode — consider installing NVIDIA Container Toolkit for GPU acceleration")

    return result
