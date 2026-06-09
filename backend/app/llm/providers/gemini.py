"""Gemini-Adapter (OpenAI-Compat-Layer auf generativelanguage.googleapis.com) — Issue #590.

Provider-Quirks, die dieser Adapter kapselt bzw. dokumentiert:

- Natives ``tools=``/``tool_choice=`` MUSS genutzt werden: Der XML-im-Prompt-
  Fallback wird von Geminis Function-Filter mit MALFORMED_FUNCTION_CALL
  abgelehnt (siehe ``LLMClient._chat_with_tools``-Branch).
- Gemini-3 verlangt ein ``thought_signature``-Echo in Multi-Turn-Tool-Calls.
  Der OpenAI-Compat-Wire-Pfad strippt das Feld — deshalb routet der
  OASIS-Dispatch (``detect_provider(mode="oasis")``) Gemini-Modelle auf die
  native CAMEL-GEMINI-Plattform statt auf den Compat-Layer.
- Kein ``extra_body``: Ollama-Optionen (``options.num_ctx``/``think``)
  fuehren auf dem Compat-Layer zu 400ern.
"""
from __future__ import annotations

from app.llm.providers.base import ProviderAdapter, ProviderCapabilities


class GeminiAdapter(ProviderAdapter):
    """Adapter fuer Gemini via OpenAI-Compat-Layer."""

    name = "google"
    capabilities = ProviderCapabilities(
        supports_native_tools=True,
        supports_json_object_mode=True,
        supports_json_schema_mode=True,
    )
