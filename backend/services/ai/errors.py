"""Fehlerklassen für den Multi-Provider-AI-Layer.

Alle Exception-Strings sind sekret-frei: Wir nehmen ENV-Variablen-Namen,
HTTP-Status, Provider-Namen — nie Key-Werte.
"""

from __future__ import annotations


class AIProviderError(Exception):
    """Basisfehler für alle Provider-Operationen."""


class MissingCredentialError(AIProviderError):
    """Pflicht-ENV fehlt. Meldung verweist auf .env.example, nie auf den Key-Inhalt."""

    def __init__(self, env_var: str, hint: str | None = None) -> None:
        msg = f"{env_var} nicht in .env gesetzt — siehe .env.example"
        if hint:
            msg = f"{msg} ({hint})"
        super().__init__(msg)
        self.env_var = env_var


class ProviderHTTPError(AIProviderError):
    """Upstream-HTTP-Fehler. Bewusst ohne Request-/Response-Body, da diese
    Auth-Header oder Echo-Keys enthalten könnten."""

    def __init__(self, provider: str, status_code: int, detail: str | None = None) -> None:
        msg = f"{provider}: HTTP {status_code}"
        if detail:
            msg = f"{msg} — {detail}"
        super().__init__(msg)
        self.provider = provider
        self.status_code = status_code


class UnknownProviderError(AIProviderError):
    """Provider-Slug ist nicht openai/gemini/ollama."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Unbekannter Provider '{provider}'. Erlaubt: openai, gemini, ollama"
        )
        self.provider = provider
