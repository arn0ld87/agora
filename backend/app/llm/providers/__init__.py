"""Provider-Adapter-Schicht (Issues #590/#591).

- ``registry`` — zentrale Provider-Erkennung (``detect_provider``) und
  Adapter-Aufloesung (``get_adapter``).
- ``base`` — ``ProviderAdapter``-Basisklasse + ``ProviderCapabilities``.
- ``ollama`` / ``openai`` / ``gemini`` — die konkreten Adapter mit den
  jeweiligen Provider-Quirks.
"""
