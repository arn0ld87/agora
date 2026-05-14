"""API-Keys-Contract v1 (Pydantic v2).

Single-Workspace-Scope: API-Schlüssel sind keine User-Identity, sondern
Workspace-Zugänge mit Scopes (read|write|admin). Klartext-Token (`ago_<48-hex>`)
wird nur einmal im CreateResponse zurückgegeben; persistiert wird nur der Prefix
zur UI-Anzeige.

Status:
  active   — Schlüssel ist verwendbar.
  revoked  — Manuell zurückgezogen, kein erneutes Aktivieren.

Siehe ADR-Slice G2 + docu/2026-05-14-design-v4-slice-g2-api-keys-worklog.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ApiKeyScope = Literal["read", "write", "admin"]
ApiKeyStatus = Literal["active", "revoked"]

_STRICT = ConfigDict(extra="forbid")

# Klartext-Token-Format: ago_<48-hex>
TOKEN_PREFIX_LENGTH = 12  # "ago_" + 8 Hex-Zeichen


class ApiKeyModel(BaseModel):
    """Persistierte Repräsentation eines API-Schlüssels (ohne Klartext)."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=120)
    prefix: str = Field(
        min_length=TOKEN_PREFIX_LENGTH,
        max_length=TOKEN_PREFIX_LENGTH,
        pattern=r"^ago_[0-9a-f]{8}$",
    )
    scopes: list[ApiKeyScope] = Field(min_length=1)
    status: ApiKeyStatus
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ApiKeyCreateRequest(BaseModel):
    """Eingabe für POST /api/api-keys."""

    model_config = _STRICT

    label: str = Field(min_length=1, max_length=120)
    scopes: list[ApiKeyScope] = Field(min_length=1)


class ApiKeyCreateResponse(BaseModel):
    """Antwort auf POST /api/api-keys — Klartext-Token erscheint hier genau einmal."""

    model_config = _STRICT

    key: ApiKeyModel
    token: str = Field(pattern=r"^ago_[0-9a-f]{48}$")


class ApiKeysListResponse(BaseModel):
    """Antwort auf GET /api/api-keys."""

    model_config = _STRICT

    items: list[ApiKeyModel]
    total: int = Field(ge=0)
