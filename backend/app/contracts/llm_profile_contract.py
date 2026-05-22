"""LLM-Profile-Contract (Pydantic v2) — P5.1 Layer 0.

Repräsentiert benannte LLM-Konfigurationen (Provider + Modell + Key).
Jeder Agora-Run kann pro Schritt ein Profil referenzieren.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .provider_types import ProviderType

_STRICT = ConfigDict(extra="forbid", populate_by_name=True)


class LlmProfile(BaseModel):
    model_config = _STRICT

    id: str = Field(..., description="UUID, server-generiert")
    name: str = Field(..., min_length=1, max_length=80)
    provider: ProviderType
    base_url: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    # None = nicht gesetzt (Update lässt Feld weg). "" = explizit geleert.
    api_key: Optional[str] = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class LlmProfileListResponse(BaseModel):
    model_config = _STRICT
    profiles: list[LlmProfile]


class LlmProfileCreateRequest(BaseModel):
    model_config = _STRICT

    name: str = Field(..., min_length=1, max_length=80)
    provider: ProviderType
    base_url: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    # None = nicht gesetzt (Update lässt Feld weg). "" = explizit geleert.
    api_key: Optional[str] = None
    is_default: bool = False
