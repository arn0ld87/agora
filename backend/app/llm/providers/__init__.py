"""
Per-provider helpers for ``LLMClient`` (#582) + Provider-Adapter (#590/#591).

Zwei Schichten koexistieren in diesem Paket:

1. Mechanisches Grouping (#582): pro-Provider-Helfer, die aus dem
   ehemaligen ``LLMClient``-Monolith extrahiert wurden — plain functions,
   keine Protokoll-Hierarchie.
2. Provider-Adapter (#590/#591): :class:`~app.llm.providers.base.ProviderAdapter`
   als gemeinsame Schnittstelle fuer Payload-Shaping + Transport +
   Fehler-Normalisierung; :mod:`~app.llm.providers.registry` als
   Single-Source-of-Truth fuer Provider-Detection (``detect_provider``)
   und Adapter-Aufloesung (``get_adapter``).

Modules:
    base.py     ``ProviderAdapter``-ABC + ``ProviderCapabilities`` +
                Backward-Compat-Re-Exports ``is_ollama`` / ``detect_provider``.
    registry.py Provider-Detection (``detect_provider(mode="http"|"oasis")``)
                + Adapter-Aufloesung (``get_adapter``) — SSOT seit #591.
    openai.py   Token-limit-key-quirks (``max_tokens`` vs.
                ``max_completion_tokens``) + 400-detection + ``OpenAIAdapter``.
    ollama.py   Native Ollama ``/api/chat`` schema path + ``OllamaAdapter``.
    gemini.py   ``GeminiAdapter`` (OpenAI-Compat-Layer).
"""