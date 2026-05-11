"""OpenAI Chat-Completions-Wrapper."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..errors import MissingCredentialError, ProviderHTTPError

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class OpenAIClient:
    """Minimaler OpenAI-Client für Chat-Completions.

    API-Key wird zur Laufzeit aus ``OPENAI_API_KEY`` gelesen, niemals
    geloggt oder in Exceptions weitergereicht.
    """

    name = "openai"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout or DEFAULT_TIMEOUT)
        self._base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
        ).rstrip("/")

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    async def complete(
        self,
        prompt: str,
        model: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise MissingCredentialError("OPENAI_API_KEY")

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            # o-Modelle erwarten ``max_completion_tokens`` — Auto-Fallback
            # behandeln wir im UnifiedClient/Retry, hier bleibt es schlank.
            body["max_tokens"] = max_tokens

        resp = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if not resp.is_success:
            raise ProviderHTTPError(
                self.name,
                resp.status_code,
                detail=resp.reason_phrase or None,
            )
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderHTTPError(
                self.name, 200, detail=f"unerwartetes Response-Format ({type(exc).__name__})"
            ) from None
