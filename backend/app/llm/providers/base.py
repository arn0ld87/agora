"""Basisklasse der Provider-Adapter (Issue #590).

``ProviderAdapter`` definiert die einheitliche Schnittstelle, ueber die
Provider-spezifisches Verhalten gekapselt wird:

- Payload-Shaping (``prepare_request_kwargs``): Token-Limit-Key,
  ``extra_body``-Optionen, Response-Format- und Tool-Wire-Format.
- Transport (``complete`` / ``stream``) ueber einen injizierten
  OpenAI-kompatiblen Client mit dem gemeinsamen Retry-Layer
  (:mod:`app.llm.retry`).
- Fehler-Normalisierung (``normalize_error``) auf
  :class:`~app.contracts.llm_request.NormalizedLlmError`.

Die Adapter sind zustandsarm: Instanz-Konfiguration beschraenkt sich auf
``num_ctx``/``think`` (nur vom Ollama-Adapter genutzt). Der bestehende
``LLMClient`` delegiert sein Payload-Shaping an diese Schicht; die
Compliance-Suite (``tests/llm/test_provider_compliance.py``) fixiert das
einheitliche Verhalten aller Adapter.
"""
from __future__ import annotations

from abc import ABC
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Literal, Optional

from app.contracts.llm_request import (
    NormalizedLlmChunk,
    NormalizedLlmError,
    NormalizedLlmRequest,
    ResponseFormat,
    ToolSpec,
)
from app.contracts.provider_types import ProviderType
from app.llm.errors import LlmProviderError, normalize_provider_error
from app.llm.retry import llm_call_with_retry

CompletionTokenParam = Literal["max_tokens", "max_completion_tokens"]


@dataclass(frozen=True)
class ProviderCapabilities:
    """Deklarative Faehigkeiten eines Providers.

    Informativ fuer Routing-/Fallback-Entscheidungen; die Laufzeit-Fallbacks
    (z. B. strict-json_schema → json_object → Freitext) bleiben beim Caller.
    """

    supports_native_tools: bool
    supports_json_object_mode: bool
    supports_json_schema_mode: bool
    uses_ollama_native_options: bool = False


def wire_response_format(response_format: ResponseFormat) -> Dict[str, Any]:
    """Uebersetzt :class:`ResponseFormat` ins OpenAI-Wire-Format."""
    if response_format.type == "json_schema" and response_format.json_schema is not None:
        return {"type": "json_schema", "json_schema": response_format.json_schema}
    return {"type": response_format.type}


def wire_tool(tool: ToolSpec) -> Dict[str, Any]:
    """Uebersetzt :class:`ToolSpec` ins OpenAI-Function-Calling-Wire-Format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class ProviderAdapter(ABC):
    """Gemeinsame Adapter-Schnittstelle fuer Ollama, OpenAI und Gemini."""

    name: ClassVar[ProviderType]
    capabilities: ClassVar[ProviderCapabilities]

    def __init__(self, *, num_ctx: Optional[int] = None, think: bool = False) -> None:
        self.num_ctx = num_ctx
        self.think = think

    # ------------------------------------------------------------------
    # Payload-Shaping-Hooks (provider-spezifisch ueberschreibbar)
    # ------------------------------------------------------------------

    def completion_token_param(self, model: str) -> CompletionTokenParam:
        """Wire-Key fuer das Token-Limit (Default: ``max_tokens``)."""
        return "max_tokens"

    def build_extra_body(self) -> Optional[Dict[str, Any]]:
        """Provider-spezifischer ``extra_body``-Block (Default: keiner)."""
        return None

    def prepare_request_kwargs(self, request: NormalizedLlmRequest) -> Dict[str, Any]:
        """Baut die kwargs fuer ``client.chat.completions.create``."""
        kwargs: Dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs[self.completion_token_param(request.model)] = request.max_tokens
        if request.response_format is not None:
            kwargs["response_format"] = wire_response_format(request.response_format)
        if request.tools:
            kwargs["tools"] = [wire_tool(t) for t in request.tools]
        extra_body = self.build_extra_body()
        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        return kwargs

    # ------------------------------------------------------------------
    # Transport (gemeinsamer Retry-Layer)
    # ------------------------------------------------------------------

    def complete(
        self,
        client: Any,
        request: NormalizedLlmRequest,
        *,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> str:
        """Nicht-streamender Chat-Completion-Aufruf.

        Wirft :class:`LlmProviderError` mit normalisierter Payload; der
        Original-Fehler bleibt als ``__cause__`` erhalten.
        """
        kwargs = self.prepare_request_kwargs(request)
        try:
            response = llm_call_with_retry(
                client.chat.completions.create,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — bewusst: alles normalisieren
            raise LlmProviderError(self.normalize_error(exc)) from exc
        choices: List[Any] = getattr(response, "choices", None) or []
        if not choices:
            return ""
        content = getattr(getattr(choices[0], "message", None), "content", None)
        return content or ""

    def stream(
        self,
        client: Any,
        request: NormalizedLlmRequest,
        *,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> Iterator[NormalizedLlmChunk]:
        """Streamender Chat-Completion-Aufruf.

        Liefert ``token``-Chunks, abgeschlossen durch ``done``. Fehler werden
        als ``error``-Chunk mit normalisierter Payload emittiert (kein Raise —
        stream-freundlich fuer SSE-Weiterleitung).
        """
        kwargs = self.prepare_request_kwargs(request)
        kwargs["stream"] = True
        try:
            stream = llm_call_with_retry(
                client.chat.completions.create,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — bewusst: alles normalisieren
            yield NormalizedLlmChunk(type="error", error=self.normalize_error(exc))
            return
        try:
            for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                text = getattr(delta, "content", None)
                if text:
                    yield NormalizedLlmChunk(type="token", text=text)
        except Exception as exc:  # noqa: BLE001 — bewusst: alles normalisieren
            yield NormalizedLlmChunk(type="error", error=self.normalize_error(exc))
            return
        yield NormalizedLlmChunk(type="done")

    # ------------------------------------------------------------------
    # Fehler-Normalisierung
    # ------------------------------------------------------------------

    def normalize_error(self, exc: Exception) -> NormalizedLlmError:
        """Mappt eine rohe Exception auf :class:`NormalizedLlmError`."""
        return normalize_provider_error(exc, provider=self.name)
