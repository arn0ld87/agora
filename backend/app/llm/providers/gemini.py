"""Gemini-Adapter (OpenAI-Compat-Layer auf generativelanguage.googleapis.com) — Issue #590.

Provider-Quirks, die dieser Adapter kapselt bzw. dokumentiert:

- Natives ``tools=``/``tool_choice=`` MUSS genutzt werden: Der XML-im-Prompt-
  Fallback wird von Geminis Function-Filter mit MALFORMED_FUNCTION_CALL
  abgelehnt (siehe ``LLMClient._chat_with_tools``-Branch).
- Gemini-3 verlangt ein ``thought_signature``-Echo in Multi-Turn-Tool-Calls.
  CAMEL 0.2.78 rekonstruiert Tool-Historie ohne dieses Feld; der lokale
  OASIS-Adapter bewahrt und ergänzt es deshalb im Compat-Layer.
- Kein ``extra_body``: Ollama-Optionen (``options.num_ctx``/``think``)
  fuehren auf dem Compat-Layer zu 400ern.
"""
from __future__ import annotations

from app.llm.providers.base import ProviderAdapter, ProviderCapabilities


class GeminiAdapter(ProviderAdapter):
    """Adapter fuer Gemini via OpenAI-Compat-Layer.

    ``name`` ist der kanonische Provider-String ``"google"`` (siehe
    :data:`app.contracts.provider_types.PROVIDER_GOOGLE`) — nicht das
    Legacy-Literal ``'gemini'``; das ``gemini``-Literal-Gate
    (``test_no_gemini_literals_in_code``) erlaubt letzteres nur in
    ``app/contracts/provider_types.py``.
    """

    name = "google"
    capabilities = ProviderCapabilities(
        supports_native_tools=True,
        supports_json_object_mode=True,
        supports_json_schema_mode=True,
    )
