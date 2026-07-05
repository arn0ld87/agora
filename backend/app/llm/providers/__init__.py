"""
Per-provider helpers for ``LLMClient`` (#582).

Plain functions only — no provider protocol/class hierarchy here yet.
The shared-abstraction layer (``NormalizedLlmRequest``-style adapters) is
scoped separately to #590/#591; this package is a mechanical grouping of
the provider-specific quirks that already existed as ``LLMClient``
staticmethods/private methods.

Modules:
    base.py     Provider detection (``is_ollama`` / ``detect_provider``).
    openai.py   OpenAI token-limit-key quirks (``max_tokens`` vs.
                ``max_completion_tokens``) and the associated 400-detection.
    ollama.py   Native Ollama ``/api/chat`` schema path (schema flattening +
                the direct httpx call bypassing the OpenAI-compat wrapper).
"""
