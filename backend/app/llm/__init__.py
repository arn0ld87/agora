"""LLM-Runtime-Paket (Milestone M3, Issues #582/#590/#591).

Buendelt die LLM-Infrastruktur des Backends:

- ``app.llm.providers.registry`` — zentrale Provider-Erkennung (#591)
- ``app.llm.providers.*`` — Provider-Adapter-Schicht (#590)
- ``app.llm.client`` — ``LLMClient`` (aus ``app.utils.llm_client`` umgezogen, #582)

``app.utils.llm_client`` bleibt als Rueckwaerts-kompatible Fassade erhalten.
"""
from typing import Any

__all__ = ["LLMClient", "build_client_from_profile"]


def __getattr__(name: str) -> Any:
    # Lazy Re-Export (PEP 562): haelt den Paket-Import leichtgewichtig —
    # Konsumenten der Registry (z. B. scripts/_sim_common.py) sollen nicht
    # transitiv den kompletten Client (openai-SDK etc.) laden.
    if name in __all__:
        from app.llm import client as _client

        return getattr(_client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
