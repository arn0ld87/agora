"""Provider-agnostischer Chat-Client.

Hält je Provider eine Wrapper-Instanz und routet ``complete(...)`` an den
passenden Backend-Client. Provider/Modell kann zur Laufzeit gewechselt
werden, ohne dass Caller die HTTP-Details kennen muss.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .errors import UnknownProviderError
from .model_discovery import ModelInfo, discover_models
from .providers import GeminiClient, OllamaClient, OpenAIClient

ProviderClient = OpenAIClient | GeminiClient | OllamaClient

_DEFAULT_MODEL_ENV: dict[str, str] = {
    "openai": "OPENAI_DEFAULT_MODEL",
    "gemini": "GEMINI_DEFAULT_MODEL",
    "ollama": "OLLAMA_DEFAULT_MODEL",
}

_HARDCODED_DEFAULT: dict[str, str] = {
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
    "ollama": "llama3",
}

ALLOWED_PROVIDERS: tuple[str, ...] = ("openai", "gemini", "ollama")


class UnifiedLLMClient:
    """Einheitliche Fassade über alle drei Provider.

    Beispiel::

        client = UnifiedLLMClient(provider="ollama")
        text = await client.complete("Hallo", model="llama3")
        await client.aclose()
    """

    def __init__(
        self,
        *,
        provider: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        slug = (provider or os.environ.get("AI_DEFAULT_PROVIDER", "ollama")).strip().lower()
        if slug not in ALLOWED_PROVIDERS:
            raise UnknownProviderError(slug)
        self._provider = slug
        self._http = http_client
        self._clients: dict[str, ProviderClient] = {}

    @property
    def provider(self) -> str:
        return self._provider

    def set_provider(self, provider: str) -> None:
        slug = provider.strip().lower()
        if slug not in ALLOWED_PROVIDERS:
            raise UnknownProviderError(slug)
        self._provider = slug

    def default_model(self, provider: str | None = None) -> str:
        slug = (provider or self._provider).lower()
        env_key = _DEFAULT_MODEL_ENV.get(slug)
        if env_key:
            value = os.environ.get(env_key, "").strip()
            if value:
                return value
        return _HARDCODED_DEFAULT.get(slug, "")

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        slug = (provider or self._provider).strip().lower()
        return await discover_models(slug, client=self._http)

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        slug = (provider or self._provider).strip().lower()
        chosen_model = model or self.default_model(slug)
        backend = self._get_or_create(slug)
        return await backend.complete(
            prompt,
            chosen_model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def aclose(self) -> None:
        for backend in self._clients.values():
            await backend.aclose()
        self._clients.clear()

    async def __aenter__(self) -> "UnifiedLLMClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    def _get_or_create(self, slug: str) -> ProviderClient:
        if slug in self._clients:
            return self._clients[slug]
        if slug == "openai":
            client: ProviderClient = OpenAIClient(client=self._http)
        elif slug == "gemini":
            client = GeminiClient(client=self._http)
        elif slug == "ollama":
            client = OllamaClient(client=self._http)
        else:
            raise UnknownProviderError(slug)
        self._clients[slug] = client
        return client
