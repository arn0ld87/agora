"""Google Gemini generateContent-Wrapper."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..errors import MissingCredentialError, ProviderHTTPError

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class GeminiClient:
    """Minimaler Wrapper für ``v1beta/models/{model}:generateContent``.

    Der API-Key wird ausschließlich aus ``GEMINI_API_KEY`` gelesen und nie
    in Exceptions ausgegeben.
    """

    name = "gemini"

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
            or os.environ.get(
                "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"
            )
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
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise MissingCredentialError("GEMINI_API_KEY")

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        gen_config: dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_tokens is not None:
            gen_config["maxOutputTokens"] = max_tokens
        if gen_config:
            body["generationConfig"] = gen_config

        model_id = model.split("/", 1)[1] if model.startswith("models/") else model
        url = f"{self._base_url}/v1beta/models/{model_id}:generateContent"

        resp = await self._client.post(
            url,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=body,
        )
        if not resp.is_success:
            detail = resp.reason_phrase or None
            if detail and api_key in detail:
                detail = "<redacted>"
            raise ProviderHTTPError(self.name, resp.status_code, detail=detail)

        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            return ""
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict))
