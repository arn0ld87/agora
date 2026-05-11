"""Ollama Chat-Wrapper (lokal, kein API-Key)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..errors import ProviderHTTPError

DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


class OllamaClient:
    """Spricht ``/api/chat`` auf einem lokalen oder LAN-Ollama-Daemon.

    ``OLLAMA_BASE_URL`` darf gesetzt sein; Default ist
    ``http://localhost:11434``. Es gibt keinen API-Key — wer den Endpunkt
    nicht erreicht, bekommt eine sprechende Fehlermeldung mit Basis-URL.
    """

    name = "ollama"

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
            base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
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
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            body["options"] = options

        try:
            resp = await self._client.post(
                f"{self._base_url}/api/chat",
                headers={"Content-Type": "application/json"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProviderHTTPError(
                self.name,
                0,
                detail=f"nicht erreichbar unter {self._base_url} ({type(exc).__name__})",
            ) from None

        if not resp.is_success:
            raise ProviderHTTPError(
                self.name,
                resp.status_code,
                detail=resp.reason_phrase or None,
            )

        data = resp.json()
        message = data.get("message") or {}
        return message.get("content", "") or data.get("response", "") or ""
