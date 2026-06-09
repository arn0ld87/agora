"""Ollama-Adapter (lokal + Ollama Cloud) — Issue #590.

Provider-Quirks, die dieser Adapter kapselt:

- ``extra_body["options"]["num_ctx"]`` verhindert Prompt-Truncation; nur
  Ollama versteht den Block (OpenAI/Anthropic/Mistral antworten 400
  "Unknown parameter").
- ``extra_body["think"]`` steuert Reasoning-Output auf faehigen Modellen.
- Force-Streaming-Workaround: Der OpenAI-kompatible Endpoint in Ollama
  0.21.0 haengt bei non-streaming Completions fuer Cloud-Modelle; der
  ``LLMClient`` erzwingt deshalb Streaming (``LLM_FORCE_STREAM``,
  Default an) und reassembliert die Chunks.
- Nativer ``/api/chat``-Schema-Pfad (``format=<schema>``) fuer striktes
  JSON — siehe ``LLMClient._ollama_chat_with_schema``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.llm.providers.base import ProviderAdapter, ProviderCapabilities


def build_ollama_extra_body(*, num_ctx: Optional[int], think: bool) -> Dict[str, Any]:
    """Baut den Ollama-``extra_body``-Block (``options.num_ctx`` + ``think``).

    Verhalten 1:1 aus ``LLMClient.chat()`` uebernommen: ``options`` nur bei
    truthy ``num_ctx``; ``think`` wird immer gesetzt.
    """
    body: Dict[str, Any] = {}
    if num_ctx:
        body["options"] = {"num_ctx": num_ctx}
    body["think"] = think
    return body


class OllamaAdapter(ProviderAdapter):
    """Adapter fuer lokales Ollama (:11434) und Ollama Cloud (ollama.com)."""

    name = "ollama"
    capabilities = ProviderCapabilities(
        supports_native_tools=True,
        supports_json_object_mode=True,
        supports_json_schema_mode=True,
        uses_ollama_native_options=True,
    )

    def build_extra_body(self) -> Optional[Dict[str, Any]]:
        return build_ollama_extra_body(num_ctx=self.num_ctx, think=self.think)
