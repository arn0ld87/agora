"""LLM runtime settings resolution for simulation runners."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from app.config import Config


def _parse_model_context_limits() -> Dict[str, int]:
    raw = os.environ.get("LLM_MODEL_CONTEXT_LIMITS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[LLM config] Ignoring invalid LLM_MODEL_CONTEXT_LIMITS_JSON: {exc}", flush=True)
        return {}
    if not isinstance(parsed, dict):
        print("[LLM config] Ignoring non-object LLM_MODEL_CONTEXT_LIMITS_JSON", flush=True)
        return {}

    result: Dict[str, int] = {}
    for model_name, value in parsed.items():
        try:
            limit = int(value)
        except (TypeError, ValueError):
            print(f"[LLM config] Ignoring invalid context limit for {model_name!r}: {value!r}", flush=True)
            continue
        if limit > 0:
            result[str(model_name)] = limit
    return result


def resolve_model_runtime_settings(model_name: str) -> Dict[str, Any]:
    """Resolve completion, CAMEL memory budget and local Ollama num_ctx hints."""
    completion_max_tokens = int(
        os.environ.get("LLM_MAX_OUTPUT_TOKENS", str(Config.LLM_MAX_OUTPUT_TOKENS))
    )
    default_memory_limit = int(
        os.environ.get("LLM_CONTEXT_LIMIT", str(Config.LLM_CONTEXT_LIMIT))
    )
    context_overrides = dict(getattr(Config, "LLM_MODEL_CONTEXT_LIMITS", {}) or {})
    context_overrides.update(_parse_model_context_limits())
    if model_name in context_overrides:
        memory_token_limit = int(context_overrides[model_name])
    else:
        # Frontend-Modellauswahl: Modell-String steht oft nicht in der env-Map.
        # Fallback ueber dieselbe Substring-Heuristik wie agent_tools, damit
        # z. B. ein vom UI gewaehltes "gemini-3-pro:cloud" nicht auf 256 k
        # gekappt wird, obwohl das Modell 1 M kann.
        try:
            from agent_tools import _heuristic_context_limit
            heuristic = _heuristic_context_limit(str(model_name))
        except Exception:
            heuristic = None
        memory_token_limit = (
            max(int(heuristic), default_memory_limit) if heuristic else default_memory_limit
        )
    is_cloud_model = str(model_name).endswith(":cloud")

    return {
        "completion_max_tokens": completion_max_tokens,
        "memory_token_limit": memory_token_limit,
        # Ollama Cloud runs at the server-side max context; keep per-request
        # num_ctx overrides for local Ollama models only.
        "ollama_num_ctx": None if is_cloud_model else memory_token_limit,
        "is_cloud_model": is_cloud_model,
    }
