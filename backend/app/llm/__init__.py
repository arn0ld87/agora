"""LLM-Runtime-Paket (Milestone M3, Issues #582/#590/#591).

Buendelt die LLM-Infrastruktur des Backends:

- ``app.llm.providers.registry`` — zentrale Provider-Erkennung (#591)
- ``app.llm.providers.*`` — Provider-Adapter-Schicht (#590)
- ``app.llm.client`` — ``LLMClient`` (aus ``app.utils.llm_client`` umgezogen, #582)

``app.utils.llm_client`` bleibt als Rueckwaerts-kompatible Fassade erhalten.
"""
