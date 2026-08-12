"""LLM-Provider-API-Keys Contract (Pydantic v2).

Persistiert pro Provider-ID **einen** API-Key plus optionale Base-URL für
``openai_compatible``-Provider (OpenRouter, Ollama, custom). Klartext-Keys
verlassen das Backend nie — die API antwortet ausschließlich mit
maskierten Werten (``sk-...abc`` Format, letzte vier Zeichen sichtbar).

Strikt getrennt von ``api_keys_contract.py``: dort geht es um
Agora-eigene Workspace-Auth-Tokens (``ago_<48-hex>``), hier um
Drittanbieter-API-Keys (OpenAI, Google, Copilot, OpenAI-compat).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

# "sk-...abc" → vier Zeichen vom Ende sichtbar, davor immer das gleiche Präfix.
# Die End-Klasse deckt Base64-Padding (``=``) und Standard-Base64-Zeichen
# (``+``/``/``) ab — AWS-Bedrock-Bearer-Tokens sind URL-safe-Base64 und enden
# häufig auf ``=``, ohne diese Erweiterung ließen sie sich nicht persistieren.
MASKED_KEY_PATTERN = r"^.{1,8}\.\.\.[A-Za-z0-9_\-=+/]{4}$"


class LlmProviderKeyEntry(BaseModel):
    """Persistierte Repräsentation eines Provider-Keys (ohne Klartext)."""

    model_config = _STRICT

    provider_id: str = Field(min_length=1, max_length=64)
    masked_value: str = Field(pattern=MASKED_KEY_PATTERN)
    base_url: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime
    updated_at: datetime
    last_validated_at: Optional[datetime] = None
    last_validation_ok: Optional[bool] = None


class LlmProviderKeyCreateRequest(BaseModel):
    """Eingabe für POST /api/llm/providers/<provider_id>/api-key."""

    model_config = _STRICT

    api_key: str = Field(min_length=4, max_length=1024)
    base_url: Optional[str] = Field(default=None, max_length=512)


class LlmProviderKeysListResponse(BaseModel):
    """Antwort auf GET /api/llm/providers/api-keys (Übersicht aller Provider)."""

    model_config = _STRICT

    items: list[LlmProviderKeyEntry]
    total: int = Field(ge=0)
