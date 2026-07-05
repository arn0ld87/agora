"""
Ollama num_ctx heuristics + resolution.

Extracted verbatim from ``app/utils/llm_client.py`` as part of issue #582
(mechanical split — no behavior change).
"""

import json
import os
from functools import lru_cache
from typing import Optional, Any

from ..utils.logger import get_logger

logger = get_logger("agora.llm_client")

# Provider error messages that indicate strict json_schema is not supported.
# Sub-Slice 05.5 — Cloud-aware num_ctx-Heuristik.
#
# Frontend wählt Cloud-Modelle wie qwen3-coder-next:cloud (256 k) oder
# gemini-3-pro:cloud (1 M). Der bisherige hardcoded Default
# OLLAMA_NUM_CTX=8192 kappte diese Context-Windows in chat()/describe_image()/
# _chat_with_tools()/_ollama_chat_with_schema().
#
# Tabelle SYNCED mit backend/scripts/agent_tools.py::_MODEL_CONTEXT_HEURISTICS
# (TODO: in shared module extrahieren — heute Zirkular-Import-Sperre durch
# scripts → app.config). Bei Änderungen beide Stellen anfassen.
_MODEL_CONTEXT_HEURISTICS: tuple[tuple[str, int], ...] = (
    ("gemini-3", 1_048_576),       # Gemini 3 Pro / Flash: ~1M Tokens
    ("gemini-2.5", 1_048_576),
    ("gemini-2", 1_048_576),
    ("deepseek-v3", 131_072),      # DeepSeek-V3 / V3.1 / V3.2: 128k
    ("deepseek-v4", 1_048_576),    # DeepSeek-V4 (laut Vendor-Stand 2026)
    ("deepseek-r1", 131_072),
    ("qwen3-coder", 262_144),      # Qwen3-Coder / -Coder-Next: 256k
    ("qwen3", 131_072),
    ("qwen2.5", 131_072),
    ("llama-3.3", 131_072),
    ("llama3.3", 131_072),
    ("llama-3.1", 131_072),
    ("gpt-oss", 131_072),          # gpt-oss-Cloud-Familie: 128k
    ("gpt-4.1", 1_048_576),
    ("gpt-4o", 131_072),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-haiku-4", 200_000),
    ("nemotron", 131_072),         # nvidia nemotron-3-nano:30b u. ä.
)


def heuristic_num_ctx_for_model(model_name: str) -> Optional[int]:
    """Best-effort Substring-Match für bekannte Modellfamilien.

    Liefert None, wenn das Modell unbekannt ist — Caller fällt dann auf
    OLLAMA_NUM_CTX (legacy) zurück und emittiert ein WARNING (einmalig pro
    Modell, dedupliziert via lru_cache auf _warn_legacy_fallback_once).

    Um den Warning für ein unbekanntes Modell zu unterdrücken, trage es entweder
    in _MODEL_CONTEXT_HEURISTICS ein oder setze LLM_MODEL_CONTEXT_LIMITS_JSON.
    """
    if not model_name:
        return None
    needle = model_name.lower()
    for prefix, limit in _MODEL_CONTEXT_HEURISTICS:
        if prefix in needle:
            return limit
    return None


@lru_cache(maxsize=64)
def _warn_legacy_fallback_once(model_name: str, fallback: int) -> None:
    """Emit a WARNING exactly once per unknown model name (lru_cache deduplicates).

    Called only when _resolve_num_ctx reaches the legacy OLLAMA_NUM_CTX / 8192
    fallback, i.e. no heuristic, no per-model env map, no LLM_CONTEXT_LIMIT, and
    no explicit provider_options matched. The cache prevents log spam when the
    same unknown model is used repeatedly within a process lifetime.
    """
    logger.warning(
        "llm_client._resolve_num_ctx: no heuristic for model=%r, "
        "falling back to %d. Set LLM_MODEL_CONTEXT_LIMITS_JSON to override.",
        model_name,
        fallback,
    )


def _resolve_num_ctx(
    model_name: Optional[str],
    provider_options_num_ctx: Any,
) -> int:
    """Resolve num_ctx mit Override-Hierarchie.

    1. provider_options.num_ctx (explizit per ResolvedRoute, höchste Prio)
    2. LLM_MODEL_CONTEXT_LIMITS_JSON (per-Modell-Map via env)
    3. Heuristik-Tabelle (Modell-Familie-Default)
    4. LLM_CONTEXT_LIMIT (Global-Override, sofern höher als Heuristik)
    5. OLLAMA_NUM_CTX env oder 8192 (Legacy-Fallback) — emits WARNING once per model
    """
    if provider_options_num_ctx is not None:
        try:
            return int(provider_options_num_ctx)
        except (TypeError, ValueError):
            pass

    raw_per_model = os.environ.get("LLM_MODEL_CONTEXT_LIMITS_JSON", "").strip()
    if raw_per_model and model_name:
        try:
            parsed = json.loads(raw_per_model)
            if isinstance(parsed, dict) and model_name in parsed:
                return int(parsed[model_name])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    heuristic = heuristic_num_ctx_for_model(model_name or "")
    global_env = os.environ.get("LLM_CONTEXT_LIMIT")
    global_limit: Optional[int]
    try:
        global_limit = int(global_env) if global_env else None
    except ValueError:
        global_limit = None

    if heuristic is not None and global_limit is not None:
        return max(heuristic, global_limit)
    if heuristic is not None:
        return heuristic
    if global_limit is not None:
        return global_limit

    try:
        fallback = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
    except ValueError:
        fallback = 8192
    if model_name:
        _warn_legacy_fallback_once(model_name, fallback)
    return fallback
