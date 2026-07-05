"""
LLM Client Wrapper — Re-Export-Shim (Issue #582).

Die Implementierung wurde nach ``app/llm/`` verschoben (mechanischer Split
nach Providern/Verantwortlichkeiten, keine Verhaltensänderung, noch keine
neue Abstraktionsschicht — siehe #582/#590/#591). Dieses Modul bleibt aus
Backward-Compatibility-Gründen bestehen: bestehender Code, der
``from app.utils.llm_client import ...`` nutzt, funktioniert unverändert
weiter.

Layout der neuen Implementierung:
- ``app.llm.context``            — num_ctx-Heuristik
- ``app.llm.json_mode``          — Strict-Schema/JSON-Envelope-Utilities
- ``app.llm.providers.base``     — Provider-Detection (Ollama/Cloud/OpenAI/Google)
- ``app.llm.providers.openai``   — OpenAI Token-Key-Quirks
- ``app.llm.providers.ollama``   — natives /api/chat::format-Schema
- ``app.llm.tool_calls``         — native Function-Calling (chat_with_tools)
- ``app.llm.client``             — ``LLMClient``
- ``app.llm.factory``            — ``build_client_from_profile``
"""

from openai import OpenAI  # noqa: F401  (re-exported — tests patch app.utils.llm_client.OpenAI)

from ..config import Config  # noqa: F401  (re-exported — tests patch app.utils.llm_client.Config)
from .logger import get_logger
from .retry import llm_call_with_retry  # noqa: F401  (re-exported)

from ..llm.context import (
    _MODEL_CONTEXT_HEURISTICS,  # noqa: F401
    heuristic_num_ctx_for_model,
    _resolve_num_ctx,
    _warn_legacy_fallback_once,
)
from ..llm.json_mode import (
    JsonSchemaLike,
    _CODEFENCE_HEAD_RE,  # noqa: F401
    _CODEFENCE_TAIL_RE,  # noqa: F401
    _STRICT_DROP_KEYS,  # noqa: F401
    _STRICT_UNSUPPORTED_HINTS,  # noqa: F401
    _enforce_openai_strict_schema,
    _env_flag,
    _is_json_object_mode_disabled,
    _is_json_schema_mode_disabled,
    _is_unsupported_open_object,  # noqa: F401
    _read_active_config_safely,
    _strip_llm_json_envelope,
    _try_repair_truncated_json,
    should_disable_openai_json_mode,
)
from ..llm.providers.ollama import _flatten_pydantic_schema_for_ollama
from ..llm.tool_calls import (
    ToolCallItem,
    ToolCallResponse,
    _accumulate_streaming_tool_calls,
    _extract_tool_calls_from_message,
)
from ..llm.client import LLMClient
from ..llm.factory import build_client_from_profile

logger = get_logger("agora.llm_client")

__all__ = [
    "LLMClient",
    "build_client_from_profile",
    "JsonSchemaLike",
    "ToolCallItem",
    "ToolCallResponse",
    "heuristic_num_ctx_for_model",
    "should_disable_openai_json_mode",
    "OpenAI",
    "Config",
    "llm_call_with_retry",
    "logger",
    "_flatten_pydantic_schema_for_ollama",
    "_resolve_num_ctx",
    "_warn_legacy_fallback_once",
    "_strip_llm_json_envelope",
    "_try_repair_truncated_json",
    "_extract_tool_calls_from_message",
    "_accumulate_streaming_tool_calls",
    "_enforce_openai_strict_schema",
    "_read_active_config_safely",
    "_env_flag",
    "_is_json_object_mode_disabled",
    "_is_json_schema_mode_disabled",
]
