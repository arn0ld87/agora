"""LLM-Profile-Contract (Pydantic v2) — P5.1 Layer 0.

Repräsentiert benannte LLM-Konfigurationen (Provider + Modell + Key).
Jeder Agora-Run kann pro Schritt ein Profil referenzieren.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", populate_by_name=True)

ProviderLiteral = Literal["ollama", "openai", "gemini", "anthropic", "custom"]


class LlmProfile(BaseModel):
    model_config = _STRICT

    id: str = Field(..., description="UUID, server-generiert")
    name: str = Field(..., min_length=1, max_length=80)
    provider: ProviderLiteral
    base_url: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    api_key: str = Field(default="")
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class LlmProfileListResponse(BaseModel):
    model_config = _STRICT
    profiles: list[LlmProfile]


class LlmProfileCreateRequest(BaseModel):
    model_config = _STRICT

    name: str = Field(..., min_length=1, max_length=80)
    provider: ProviderLiteral
    base_url: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    api_key: str = ""
    is_default: bool = False
