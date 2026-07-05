"""Provider-neutrale Fehler-Normalisierung (Issue #590).

Vorher gab es keine Fehler-Normalisierung — rohe ``openai.BadRequestError``,
``httpx.ReadTimeout`` etc. blubberten bis zum Caller hoch. Die Adapter-Schicht
mappt jede Transport-/SDK-Exception auf :class:`NormalizedLlmError`
(``provider``/``code``/``retryable``), sodass das Frontend-Error-Envelope
providerneutral befuellt werden kann.
"""
from __future__ import annotations

from typing import Optional

import httpx
import openai

from app.contracts.llm_request import NormalizedLlmError
from app.contracts.provider_types import ProviderType


class LlmProviderError(Exception):
    """Exception-Wrapper um eine normalisierte Fehler-Payload.

    Adapter werfen diese Exception aus ``complete()``; der Original-Fehler
    bleibt als ``__cause__`` erhalten (``raise ... from exc``).
    """

    def __init__(self, normalized: NormalizedLlmError) -> None:
        super().__init__(
            f"[{normalized.provider}:{normalized.code}] {normalized.message}"
        )
        self.normalized = normalized


def _status_of(exc: Exception) -> Optional[int]:
    """HTTP-Status aus einer openai-SDK-Exception extrahieren (best effort)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def normalize_provider_error(
    exc: Exception, *, provider: ProviderType
) -> NormalizedLlmError:
    """Mappt eine rohe Exception auf einen :class:`NormalizedLlmError`.

    Retry-Semantik gespiegelt aus ``app.utils.retry._is_transient_llm_error``:
    transient (``retryable=True``) sind Verbindungsabbrueche, Timeouts,
    HTTP 429 sowie 5xx/408 — uebrige 4xx-Client-Fehler nicht.

    Reihenfolge der ``isinstance``-Checks ist signifikant:
    ``APITimeoutError`` ist Subklasse von ``APIConnectionError``,
    ``RateLimitError`` ist Subklasse von ``APIStatusError``.
    """
    cause = type(exc).__name__
    message = str(exc) or cause

    if isinstance(exc, openai.APITimeoutError):
        return NormalizedLlmError(
            provider=provider,
            code="timeout",
            message=message,
            status=None,
            retryable=True,
            cause=cause,
        )
    if isinstance(exc, openai.APIConnectionError):
        return NormalizedLlmError(
            provider=provider,
            code="connection_error",
            message=message,
            status=None,
            retryable=True,
            cause=cause,
        )
    if isinstance(exc, openai.RateLimitError):
        return NormalizedLlmError(
            provider=provider,
            code="rate_limited",
            message=message,
            status=_status_of(exc) or 429,
            retryable=True,
            cause=cause,
        )
    if isinstance(exc, openai.APIStatusError):
        status = _status_of(exc)
        retryable = status is not None and (status >= 500 or status in (408, 429))
        code = "server_error" if status is not None and status >= 500 else "client_error"
        return NormalizedLlmError(
            provider=provider,
            code=code,
            message=message,
            status=status,
            retryable=retryable,
            cause=cause,
        )
    if isinstance(exc, httpx.TimeoutException):
        return NormalizedLlmError(
            provider=provider,
            code="timeout",
            message=message,
            status=None,
            retryable=True,
            cause=cause,
        )
    if isinstance(exc, httpx.HTTPError):
        return NormalizedLlmError(
            provider=provider,
            code="connection_error",
            message=message,
            status=None,
            retryable=True,
            cause=cause,
        )
    return NormalizedLlmError(
        provider=provider,
        code="unknown",
        message=message,
        status=None,
        retryable=False,
        cause=cause,
    )