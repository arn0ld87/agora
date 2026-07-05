"""
OpenAI-spezifische Request-Quirks + OpenAI-Adapter (Issue #590).

Zwei Rollen koexistieren in diesem Modul, klar getrennt:

1. Token-Key-Quirks (main, #582): ``uses_max_completion_tokens``,
   ``is_token_key_400`` und ``swap_token_kwargs`` — extrahiert aus dem
   ehemaligen ``LLMClient``-Monolith, werden als ``LLMClient``-staticmethods
   re-exportiert und von ``app/llm/tool_calls.py`` sowie dem Shim
   ``app/utils/llm_client.py`` konsumiert. Unangetastet bei der
   #590-Portierung (nur Docstring-Kommentar zur Divergenz).
2. Provider-Adapter (PR-Vorlage, #590): :class:`OpenAIAdapter` — kapselt
   das Payload-Shaping fuer den OpenAI-kompatiblen Client-Pfad.
   ``completion_token_param`` delegiert an :func:`uses_max_completion_tokens`
   (single source of truth — kein Drift zwischen Payload-Shaping und
   Fallback-Heuristik).
"""

from typing import Any, Dict, Optional

from app.llm.providers.base import (
    CompletionTokenParam,
    ProviderAdapter,
    ProviderCapabilities,
)


# ----------------------------------------------------------------------
# Rolle 1: Token-Key-Quirks (main, #582)
# ----------------------------------------------------------------------


def uses_max_completion_tokens(model: str) -> bool:
    """Whether *model* requires ``max_completion_tokens`` instead of ``max_tokens``.

    GPT-5 / o1 / o3 / o4 verlangen max_completion_tokens; OpenAI antwortet
    sonst 400 "Unsupported parameter: 'max_tokens'". Heuristik gespiegelt
    aus backend/scripts/_sim_common.py::uses_max_completion_tokens —
    Single Source of Truth bleibt dort, hier nur die zweite Stelle.
    Striktes Prefix-Matching ("gpt-5", "gpt-5-…") verhindert
    Mismatches wie hypothetisches "gpt-500".

    Bekannte, testfixierte Divergenz: ``scripts/_sim_common.py::
    uses_max_completion_tokens`` matcht ``gpt-5`` per ``startswith`` (ohne
    Wortgrenze) und kennt keine ``.``-Grenze fuer o1/o3/o4 — Vereinheitlichung
    ist ein Follow-up, kein Teil dieses Refactorings.
    """
    lowered = (model or "").strip().lower()
    for prefix in ("gpt-5", "o1", "o3", "o4"):
        if lowered == prefix or lowered.startswith(f"{prefix}-") or lowered.startswith(f"{prefix}."):
            return True
    return False


def is_token_key_400(exc: Exception) -> bool:
    """True wenn ein OpenAI-/Proxy-400 auf eine Token-Limit-Key-Inkompatibilität hindeutet.

    Erkennt beide Richtungen, je nachdem welcher Schlüssel im Request stand:
    - "'max_tokens' is not supported with this model. Use 'max_completion_tokens'"
    - "'max_completion_tokens' is not supported …" / Unsupported parameter

    Wird von ``chat()`` als Fallback-Retry-Trigger genutzt — Heuristik
    kann z. B. bei einem neuen OpenAI-kompatiblen Proxy daneben liegen,
    und dann reicht der Wortlaut der Antwort als Fallback.
    """
    try:
        from openai import APIStatusError
    except ImportError:
        APIStatusError = ()  # type: ignore[assignment]

    if APIStatusError and isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if status != 400:
            return False
    msg = str(exc).lower()
    if "max_tokens" not in msg and "max_completion_tokens" not in msg:
        return False
    return (
        "not supported" in msg
        or "unsupported parameter" in msg
        or "use 'max_completion_tokens'" in msg
        or "use 'max_tokens'" in msg
        or "use max_completion_tokens" in msg
        or "use max_tokens" in msg
    )


def swap_token_kwargs(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Liefert eine Kopie von *kwargs* mit getauschtem Token-Limit-Schlüssel,
    oder ``None`` wenn keiner der beiden Schlüssel gesetzt ist.
    """
    swapped = dict(kwargs)
    if "max_tokens" in swapped:
        value = swapped.pop("max_tokens")
        swapped["max_completion_tokens"] = value
        return swapped
    if "max_completion_tokens" in swapped:
        value = swapped.pop("max_completion_tokens")
        swapped["max_tokens"] = value
        return swapped
    return None


# ----------------------------------------------------------------------
# Rolle 2: Provider-Adapter (#590)
# ----------------------------------------------------------------------


class OpenAIAdapter(ProviderAdapter):
    """Adapter fuer OpenAI und OpenAI-kompatible Gateways (Default-Adapter).

    Provider-Quirks, die dieser Adapter kapselt:

    - ``max_completion_tokens``-Heuristik: Die GPT-5-Familie und die
      Reasoning-Modelle o1/o3/o4 haben ``max_tokens`` deprecated und antworten
      400 "Unsupported parameter: 'max_tokens' …". Aeltere Modelle (gpt-4o,
      gpt-4-turbo, gpt-3.5-turbo) und alle Nicht-OpenAI-Backends verlangen
      weiterhin ``max_tokens``.
    - Strict-JSON-Schema (``response_format={"type": "json_schema", …}``) wird
      unterstuetzt; das Laufzeit-Fallback strict -> json_object -> Freitext
      orchestriert weiterhin der ``LLMClient``.
    """

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