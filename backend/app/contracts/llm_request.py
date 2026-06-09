"""Normalisierte LLM-Request-/Chunk-/Error-Typen (Issue #590).

Provider-neutrale Wire-Typen fuer die Adapter-Schicht in
``app/llm/providers/``: Ein ``NormalizedLlmRequest`` beschreibt einen
Chat-Completion-Aufruf unabhaengig vom Provider; die Adapter uebersetzen
ihn in das jeweilige Wire-Format (Token-Limit-Key, ``extra_body``-Optionen,
Response-Format). ``NormalizedLlmError`` traegt die providerneutrale
Fehlerklassifikation (``code``/``retryable``), die das Frontend-Error-
Envelope direkt uebernehmen kann.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.provider_types import ProviderType


class ChatMessage(BaseModel):
    """Eine Chat-Nachricht im providerneutralen Format."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None


class ResponseFormat(BaseModel):
    """Gewuenschtes Antwortformat (Text, JSON-Objekt oder striktes Schema)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text", "json_object", "json_schema"]
    json_schema: Optional[dict[str, object]] = None


class ToolSpec(BaseModel):
    """Provider-neutrale Tool-/Function-Definition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)


class NormalizedLlmRequest(BaseModel):
    """Provider-neutraler Chat-Completion-Request."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderType
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    response_format: Optional[ResponseFormat] = None
    tools: Optional[list[ToolSpec]] = None


class NormalizedLlmError(BaseModel):
    """Provider-neutral klassifizierter Fehler.

    ``retryable`` spiegelt die Retry-Semantik aus
    ``app.utils.retry._is_transient_llm_error``: Verbindungsabbrueche,
    Timeouts, HTTP 429 sowie 5xx/408 sind transient; uebrige 4xx nicht.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderType
    code: str
    message: str
    status: Optional[int] = None
    retryable: bool
    cause: Optional[str] = None


class NormalizedLlmChunk(BaseModel):
    """Ein Element eines normalisierten Streaming-Responses."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["token", "metadata", "done", "error"]
    text: Optional[str] = None
    metadata: Optional[dict[str, object]] = None
    error: Optional[NormalizedLlmError] = None
