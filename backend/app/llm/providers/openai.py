"""OpenAI-Adapter (echtes OpenAI + generische Compat-Gateways) — Issue #590.

Provider-Quirks, die dieser Adapter kapselt:

- ``max_completion_tokens``-Heuristik: Die GPT-5-Familie und die
  Reasoning-Modelle o1/o3/o4 haben ``max_tokens`` deprecated und antworten
  400 "Unsupported parameter: 'max_tokens' …". Aeltere Modelle (gpt-4o,
  gpt-4-turbo, gpt-3.5-turbo) und alle Nicht-OpenAI-Backends verlangen
  weiterhin ``max_tokens``.
- Strict-JSON-Schema (``response_format={"type": "json_schema", …}``) wird
  unterstuetzt; das Laufzeit-Fallback strict → json_object → Freitext
  orchestriert weiterhin der ``LLMClient``.
"""
from __future__ import annotations

from app.llm.providers.base import (
    CompletionTokenParam,
    ProviderAdapter,
    ProviderCapabilities,
)


def uses_max_completion_tokens(model: str) -> bool:
    """True wenn das Modell ``max_completion_tokens`` statt ``max_tokens`` verlangt.

    Kanonische Heuristik (vormals ``LLMClient._uses_max_completion_tokens``):
    striktes Prefix-Matching mit Wortgrenze (exakt, ``-`` oder ``.``) —
    verhindert Mismatches wie hypothetisches ``gpt-500``.

    Bekannte, testfixierte Divergenz: ``scripts/_sim_common.py::
    uses_max_completion_tokens`` matcht ``gpt-5`` per ``startswith`` (ohne
    Wortgrenze) und kennt keine ``.``-Grenze fuer o1/o3/o4 — Vereinheitlichung
    ist ein Follow-up, kein Teil dieses Refactorings.
    """
    lowered = (model or "").strip().lower()
    for prefix in ("gpt-5", "o1", "o3", "o4"):
        if (
            lowered == prefix
            or lowered.startswith(f"{prefix}-")
            or lowered.startswith(f"{prefix}.")
        ):
            return True
    return False


class OpenAIAdapter(ProviderAdapter):
    """Adapter fuer OpenAI und OpenAI-kompatible Gateways (Default-Adapter)."""

    name = "openai"
    capabilities = ProviderCapabilities(
        supports_native_tools=True,
        supports_json_object_mode=True,
        supports_json_schema_mode=True,
    )

    def completion_token_param(self, model: str) -> CompletionTokenParam:
        return (
            "max_completion_tokens"
            if uses_max_completion_tokens(model)
            else "max_tokens"
        )
