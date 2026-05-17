"""Thread-safe API-Schlüssel-Store mit Fernet-verschlüsselter Persistenz (PR 4 Hardening).

In-Memory-Store mit automatischer Disk-Persistenz via
:mod:`app.services.api_keys_persistence`. Klartext-Token (``ago_<48-hex>``)
wird genau einmal beim Anlegen zurückgegeben; persistiert wird nur Prefix,
Metadata und SHA-256-Hash.

Audit-Log-Hook ist Out-of-Scope (kommt in G3).
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..contracts.api_keys_contract import (
    ApiKeyCreateResponse,
    ApiKeyModel,
    ApiKeyScope,
)
from . import api_keys_persistence as _persist

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


def _hash_token(token: str) -> str:
    """Berechnet SHA-256 Hash des Tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _resolve_data_dir() -> Optional[Path]:
    raw = os.environ.get("AGORA_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return None


class ApiKeysStore:
    """Thread-safe Store mit Fernet-Persistenz. Pro Prozess eine Instanz (Modul-Singleton)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        data_dir = _resolve_data_dir()
        self._data_dir: Optional[Path] = data_dir
        # Initialer Load von Disk
        self._keys: dict[str, ApiKeyModel] = self._load_from_disk()

    def _load_from_disk(self) -> dict[str, ApiKeyModel]:
        try:
            raw = _persist.load(data_dir=self._data_dir)
        except (RuntimeError, Exception):
            # Im Fehlerfall (z. B. fehlender Key ohne Debug) leer starten;
            # Save-Operationen werden dann beim nächsten Schreibversuch scheitern.
            return {}
        result: dict[str, ApiKeyModel] = {}
        for key_id, fields in raw.items():
            try:
                result[key_id] = ApiKeyModel.model_validate(fields)
            except Exception:
                pass  # Korrupte Einträge überspringen
        return result

    def _serialize_for_disk(self) -> dict:
        """Serialisiert alle Keys als Plain-Dict (inkl. hashed_token)."""
        out: dict = {}
        for key_id, model in self._keys.items():
            # model_dump mit exclude=False um hashed_token einzuschließen
            # (exclude=True ist im Field definiert für API-Responses, nicht für Disk)
            d = model.model_dump(mode="json")
            d["hashed_token"] = model.hashed_token
            out[key_id] = d
        return out

    def _save(self) -> None:
        """Persistiert den aktuellen In-Memory-State auf Disk. Lock muss gehalten sein."""
        _persist.save(self._serialize_for_disk(), data_dir=self._data_dir)

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
        hashed = _hash_token(token)
        key_id = uuid.uuid4().hex
        model = ApiKeyModel(
            id=key_id,
            label=label,
            prefix=prefix,
            scopes=list(scopes),
            status="active",
            hashed_token=hashed,
            created_at=_now(),
            last_used_at=None,
            revoked_at=None,
        )
        with self._lock:
            self._keys[key_id] = model
            self._save()
        return ApiKeyCreateResponse(key=model, token=token)

    def validate_token(self, token: str) -> Optional[ApiKeyModel]:
        """Validiert einen Klartext-Token und aktualisiert last_used_at."""
        if not token.startswith("ago_"):
            return None
        hashed = _hash_token(token)
        with self._lock:
            for key_id, model in self._keys.items():
                if model.hashed_token == hashed:
                    if model.status == "revoked":
                        return model
                    updated = model.model_copy(update={"last_used_at": _now()})
                    self._keys[key_id] = updated
                    self._save()
                    return updated
        return None

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
            self._save()
            return revoked

    def reset_for_tests(self) -> None:
        """Nur in Tests aufrufen — leert den Store und löscht die Disk-Datei."""
        with self._lock:
            self._keys.clear()
            # Disk-Datei ebenfalls löschen
            if self._data_dir:
                data_file = self._data_dir / "api_keys.json"
                if data_file.exists():
                    try:
                        data_file.unlink()
                    except OSError:
                        pass
            else:
                from .api_keys_persistence import _resolve_data_dir as _pdr
                data_file = _pdr() / "api_keys.json"
                if data_file.exists():
                    try:
                        data_file.unlink()
                    except OSError:
                        pass


_store_singleton = ApiKeysStore()


def get_api_keys_store() -> ApiKeysStore:
    """Modul-Singleton — pro Flask-Prozess geteilt."""
    return _store_singleton
