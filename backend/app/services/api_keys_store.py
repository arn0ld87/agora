"""Thread-safe API-Schlüssel-Store mit Fernet-verschlüsselter Persistenz (PR 4 Hardening).

In-Memory-Store mit automatischer Disk-Persistenz via
:mod:`app.services.api_keys_persistence`. Klartext-Token (``ago_<48-hex>``)
wird genau einmal beim Anlegen zurückgegeben; persistiert wird nur Prefix,
Metadata und ein serverseitig gepepperter HMAC-SHA256-Lookup-Hash.

Audit-Log-Hook ist Out-of-Scope (kommt in G3).
"""
from __future__ import annotations

import hashlib
import hmac
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
from ..utils.logger import get_logger
from . import api_keys_persistence as _persist

logger = get_logger("agora.services.api_keys_store")

_TOKEN_RANDOM_HEX = 48
_PREFIX_HEX_LEN = 8
_HASH_PREFIX = "hmac-sha256:"
_HASH_PEPPER_ENV = "AGORA_API_KEY_HASH_PEPPER"
# TTL für `last_used_at`-Disk-Flush. Ohne TTL würde jeder API-Request einen
# Fernet-Encrypt + Disk-Write des kompletten Stores triggern — Gemini-Review
# zu PR #524 nennt das als High-Severity-I/O-Bottleneck. Updates landen
# weiter sofort In-Memory; nur die Persistenz wird gebündelt. Bei Crash
# gehen maximal ``_LAST_USED_PERSIST_TTL_SECONDS`` Audit-Daten verloren.
_LAST_USED_PERSIST_TTL_SECONDS = 60.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_token() -> tuple[str, str]:
    """Erzeugt (Klartext-Token, Prefix). Prefix ist ``ago_`` + erste 8 Hex-Zeichen."""
    body = secrets.token_hex(_TOKEN_RANDOM_HEX // 2)
    token = f"ago_{body}"
    prefix = f"ago_{body[:_PREFIX_HEX_LEN]}"
    return token, prefix


def _hash_token(token: str) -> str:
    """Berechnet einen serverseitig gepepperten Lookup-Hash des Tokens."""
    secret = _resolve_hash_secret()
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def _legacy_hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _resolve_hash_secret() -> bytes:
    raw = os.environ.get(_HASH_PEPPER_ENV) or os.environ.get("AGORA_FERNET_KEY")
    if raw:
        return raw.encode("utf-8")
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
    if debug_mode:
        return b"agora-debug-api-key-hash-pepper"
    raise RuntimeError(
        "AGORA_API_KEY_HASH_PEPPER or AGORA_FERNET_KEY missing in non-debug mode"
    )


def _token_hash_matches(stored_hash: str, token: str) -> tuple[bool, bool]:
    current_hash = _hash_token(token)
    if hmac.compare_digest(stored_hash, current_hash):
        return True, False
    legacy_hash = _legacy_hash_token(token)
    if hmac.compare_digest(stored_hash, legacy_hash):
        return True, True
    return False, False


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
        # Tracking, wann `last_used_at` zuletzt für jeden Key persistiert
        # wurde. Beim Load von Disk übernehmen wir den existierenden Wert,
        # damit der erste Validate keinen sofortigen Flush triggert.
        self._last_used_persisted_at: dict[str, datetime] = {
            kid: model.last_used_at
            for kid, model in self._keys.items()
            if model.last_used_at is not None
        }

    def _load_from_disk(self) -> dict[str, ApiKeyModel]:
        try:
            raw = _persist.load(data_dir=self._data_dir)
        except RuntimeError:
            # RuntimeError aus _persist.load signalisiert Config-/Crypto-
            # Probleme (fehlender FERNET-Key in Prod, korrupter Ciphertext).
            # Schlucken würde einen leeren Key-Store ohne Diagnose-Hinweis
            # ergeben — Operator muss das beim Boot sehen.
            raise
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error("Failed to load API keys from disk: %s", exc)
            return {}
        result: dict[str, ApiKeyModel] = {}
        for key_id, fields in raw.items():
            try:
                result[key_id] = ApiKeyModel.model_validate(fields)
            except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning(
                    "Skipping corrupt API key entry '%s': %s", key_id, exc
                )
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
        """Validiert einen Klartext-Token und aktualisiert last_used_at.

        `last_used_at` wird unmittelbar In-Memory aktualisiert; der Disk-
        Flush wird per TTL (`_LAST_USED_PERSIST_TTL_SECONDS`) gedrosselt,
        damit nicht jeder API-Request einen Fernet-Encrypt + Disk-Write des
        gesamten Stores triggert (Gemini-Review zu PR #524).
        """
        if not token.startswith("ago_"):
            return None
        hashed = _hash_token(token)
        now = _now()
        with self._lock:
            for key_id, model in self._keys.items():
                matches, needs_migration = _token_hash_matches(model.hashed_token, token)
                if matches:
                    if model.status == "revoked":
                        return model
                    update_fields: dict[str, object] = {"last_used_at": now}
                    if needs_migration:
                        update_fields["hashed_token"] = hashed
                    updated = model.model_copy(update=update_fields)
                    self._keys[key_id] = updated
                    if needs_migration or self._should_flush_last_used_at(key_id, now):
                        self._save()
                        self._last_used_persisted_at[key_id] = now
                    return updated
        return None

    def _should_flush_last_used_at(self, key_id: str, now: datetime) -> bool:
        previous = self._last_used_persisted_at.get(key_id)
        if previous is None:
            return True
        return (now - previous).total_seconds() >= _LAST_USED_PERSIST_TTL_SECONDS

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


_store_singleton: Optional[ApiKeysStore] = None


def get_api_keys_store() -> ApiKeysStore:
    """Lazy Modul-Singleton — pro Flask-Prozess geteilt.

    Lazy-Init verhindert, dass eine fehlende ``AGORA_FERNET_KEY``-
    Konfiguration den Modul-Import sprengt — der Konfigurationsfehler
    wird erst am ersten echten Use sichtbar (klare Diagnose statt
    ``ImportError`` aus dem Pytest-Collector).
    """
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = ApiKeysStore()
    return _store_singleton
