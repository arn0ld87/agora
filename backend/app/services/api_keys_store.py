"""Thread-safe In-Memory-Store für API-Schlüssel (Slice G2).

Single-Workspace-Scope: kein Identity-Modul, keine Persistenz auf Disk.
Klartext-Token (``ago_<48-hex>``) wird genau einmal beim Anlegen
zurückgegeben; persistiert wird nur Prefix + Metadata.

Audit-Log-Hook ist Out-of-Scope für G2 (kommt in G3).
"""
from __future__ import annotations

import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..contracts.api_keys_contract import (
    ApiKeyCreateResponse,
    ApiKeyModel,
    ApiKeyScope,
)

_TOKEN_RANDOM_HEX = 48
_PREFIX_HEX_LEN = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_token() -> tuple[str, str]:
    """Erzeugt (Klartext-Token, Prefix). Prefix ist ``ago_`` + erste 8 Hex-Zeichen."""
    body = secrets.token_hex(_TOKEN_RANDOM_HEX // 2)
    token = f"ago_{body}"
    prefix = f"ago_{body[:_PREFIX_HEX_LEN]}"
    return token, prefix


class ApiKeysStore:
    """Thread-safe In-Memory-Store. Pro Prozess eine Instanz (Modul-Singleton)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[str, ApiKeyModel] = {}

    def list(self) -> list[ApiKeyModel]:
        with self._lock:
            return sorted(
                self._keys.values(),
                key=lambda k: k.created_at,
                reverse=True,
            )

    def get(self, key_id: str) -> Optional[ApiKeyModel]:
        with self._lock:
            return self._keys.get(key_id)

    def create(self, label: str, scopes: list[ApiKeyScope]) -> ApiKeyCreateResponse:
        token, prefix = _generate_token()
        key_id = uuid.uuid4().hex
        model = ApiKeyModel(
            id=key_id,
            label=label,
            prefix=prefix,
            scopes=list(scopes),
            status="active",
            created_at=_now(),
            last_used_at=None,
            revoked_at=None,
        )
        with self._lock:
            self._keys[key_id] = model
        return ApiKeyCreateResponse(key=model, token=token)

    def revoke(self, key_id: str) -> Optional[ApiKeyModel]:
        with self._lock:
            existing = self._keys.get(key_id)
            if existing is None:
                return None
            if existing.status == "revoked":
                return existing
            revoked = existing.model_copy(
                update={"status": "revoked", "revoked_at": _now()}
            )
            self._keys[key_id] = revoked
            return revoked

    def reset_for_tests(self) -> None:
        """Nur in Tests aufrufen — leert den Store hart."""
        with self._lock:
            self._keys.clear()


_store_singleton = ApiKeysStore()


def get_api_keys_store() -> ApiKeysStore:
    """Modul-Singleton — pro Flask-Prozess geteilt."""
    return _store_singleton
