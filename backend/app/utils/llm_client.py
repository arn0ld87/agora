"""Rueckwaerts-kompatible Fassade — Implementation lebt in ``app.llm`` (#582).

Der ``LLMClient`` und seine Helper sind nach ``app/llm/`` umgezogen:
``client.py`` (Klasse + Tool-Calling + ``build_client_from_profile``),
``context.py`` (num_ctx-Heuristik), ``json_mode.py`` (JSON-Mode-Bausteine),
``providers/`` (Adapter + Detection-Registry).

Dieses Modul ersetzt sich selbst in ``sys.modules`` durch
``app.llm.client``: Damit treffen Monkeypatches/Mocks auf
``app.utils.llm_client.<Name>`` (z. B. ``OpenAI``, ``llm_call_with_retry``,
``_read_active_config_safely``, ``Config.*``) weiterhin das echte
Implementations-Modul. Ein reiner Re-Export-Shim wuerde solche Patches ins
Leere laufen lassen, weil die Call-Sites in ``app.llm.client`` ihre eigenen
Modul-Globals aufloesen.

Neue Importe bitte direkt auf ``app.llm.client`` zeigen; dieser Shim
verschwindet, sobald alle Aufrufer migriert sind (Follow-up zu #582).
"""
from __future__ import annotations

import sys

from app.llm import client as _client

# Explizite Export-Liste — haelt mypy-Konsumenten (no_implicit_reexport-
# Semantik bei Re-Import-Shims) gruen; zur Laufzeit gilt ohnehin der Alias.
__all__ = [
    "LLMClient",
    "ToolCallItem",
    "ToolCallResponse",
    "build_client_from_profile",
    "heuristic_num_ctx_for_model",
    "should_disable_openai_json_mode",
]

# Statische Re-Exports — nur fuer Type-Checker/IDE-Aufloesung; zur Laufzeit
# zaehlt der sys.modules-Alias unten (saemtliche Modul-Attribute inklusive).
from app.llm.client import (  # noqa: F401
    LLMClient,
    ToolCallItem,
    ToolCallResponse,
    _flatten_pydantic_schema_for_ollama,
    _resolve_num_ctx,
    _strip_llm_json_envelope,
    _warn_legacy_fallback_once,
    build_client_from_profile,
    heuristic_num_ctx_for_model,
    should_disable_openai_json_mode,
)

sys.modules[__name__] = _client
