"""Persistenter, Fernet-verschlüsselter Store für LLM-Provider-API-Keys.

Storage-Layout (`backend/data/llm_provider_secrets.json`):

    {
      "version": 1,
      "entries": {
        "openai": {
          "ciphertext": "<fernet-base64>",
          "base_url": null,
          "created_at": "2026-...",
          "updated_at": "2026-...",
          "last_validated_at": null,
          "last_validation_ok": null
        },
        ...
      }
    }

Master-Key:
    `AGORA_SECRET_KEY` (Pflicht; Fail-Fast wenn nicht gesetzt). Wert muss ein
    gültiger Fernet-Key sein (URL-safe base64, 32 Bytes). Ungesetzt oder
    invalid → ``RuntimeError`` beim ersten Zugriff. Dadurch kann die Flask-App
    beim Start (oder beim ersten Request) einen klaren Fehler werfen.

Security:
    - Klartext-Keys werden ausschließlich beim Encrypt-Roundtrip im Speicher
      gehalten und nie geloggt.
    - ``masked_value`` ist die einzige Repräsentation, die das Modul nach außen
      gibt; sie wird aus dem Klartext abgeleitet, nicht aus dem Ciphertext.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, Optional

from cryptography.fernet import Fernet, InvalidToken

from ..contracts.llm_provider_keys_contract import LlmProviderKeyEntry
from ..utils.logger import get_logger
from .data_dir import resolve_data_dir as _resolve_data_dir

logger = get_logger("agora.services.llm_provider_secrets_store")

_SECRET_KEY_ENV = "AGORA_SECRET_KEY"
_STORE_FILENAME = "llm_provider_secrets.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_key(plaintext: str) -> str:
    """Erzeugt ein Maskierungsformat ``sk-...abcd`` aus einem Klartext-Key."""
    if len(plaintext) <= 4:
        # zu kurz für sinnvolle Maskierung — Sentinel, aber Pattern-konform
        return f"key-...{plaintext.rjust(4, '_')[-4:]}"
    prefix = plaintext[:2] if plaintext.startswith(("sk", "gh", "go", "AI")) else plaintext[:3]
    if not prefix:
        prefix = "key"
    return f"{prefix}-...{plaintext[-4:]}"


class SecretDecryptionError(RuntimeError):
    """Ciphertext genau eines Providers passt nicht zum aktuellen Fernet-Key.

    Bewusst von ``RuntimeError`` abgeleitet, damit bestehende Aufrufer
    unverändert weiterlaufen. Der eigene Typ trennt den Einzel-Credential-Defekt
    von globalen Store- und Konfigurationsfehlern (fehlender oder ungültiger
    ``AGORA_SECRET_KEY``, unlesbare Store-Datei), die weiter als blankes
    ``RuntimeError`` fliegen und hart bleiben müssen.
    """


def _load_fernet() -> Fernet:
    raw = os.environ.get(_SECRET_KEY_ENV)
    if not raw:
        raise RuntimeError(
            f"{_SECRET_KEY_ENV} ist nicht gesetzt. Erzeugen mit:\n"
            "  python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'\n"
            f"Anschließend in der Umgebung exportieren ({_SECRET_KEY_ENV}=…)."
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{_SECRET_KEY_ENV} ist kein gültiger Fernet-Key: {exc}"
        ) from exc


class LlmProviderSecretsStore:
    """File-backed, Fernet-encrypted Multi-Provider-Secret-Store.

    Thread-safe via internen Lock. Lese-Operationen entschlüsseln on-demand und
    cachen Klartext NICHT — jeder Aufruf von ``get_plaintext`` macht einen
    Decrypt-Roundtrip.

    Die ``Fernet``-Instanz wird beim ersten Zugriff einmalig erstellt und dann
    gecacht, um das wiederholte Key-Parsing zu vermeiden (Gemini MEDIUM #1).
    """

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._path = self._data_dir / _STORE_FILENAME
        self._fernet_instance: Optional[Fernet] = None
        self._fernet_key_raw: Optional[str] = None  # Wert aus Env beim letzten Cache-Fill

    def _fernet(self) -> Fernet:
        """Lazy-cached Fernet-Instanz.

        Der Cache wird nur dann wiederverwendet, wenn der Env-Var-Wert von
        ``AGORA_SECRET_KEY`` unverändert ist. Key-Rotation (oder Testwechsel)
        invalidiert den Cache automatisch.
        """
        current_key_raw = os.environ.get(_SECRET_KEY_ENV)
        if self._fernet_instance is None or self._fernet_key_raw != current_key_raw:
            self._fernet_instance = _load_fernet()
            self._fernet_key_raw = current_key_raw
        return self._fernet_instance

    def _read_raw(self) -> dict:
        if not self._path.exists():
            return {"version": 1, "entries": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Konnte LLM-Secrets-Store nicht lesen ({self._path}): {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise RuntimeError(
                f"Konnte LLM-Secrets-Store nicht lesen ({self._path}): "
                "JSON-Root muss ein Objekt sein"
            )
        return raw

    @contextmanager
    def _file_lock(self) -> Iterator[IO[str]]:
        """Hält den Prozess-Lock über eine komplette Read-modify-write-Operation."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_suffix(".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield lock_fh
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _write_raw(self, raw: dict) -> None:
        """Atomisches Schreiben innerhalb eines gehaltenen File-Level-Locks.

        ``threading.Lock`` schützt nur innerhalb eines Prozesses. Bei mehreren
        Gunicorn-Workern ist zusätzlich ``fcntl.flock`` nötig, um Lost-Updates
        zu verhindern (Gemini MEDIUM #2).

        Nach dem Replace setzt der Store ``0600`` auf das JSON-File, damit der
        Fernet-Ciphertext nicht für andere User auf dem Host lesbar ist
        (Issue #450 P1.3). chmod-Fehler werden geloggt statt zu crashen — auf
        manchen NFS-/Volume-Mounts ist chmod nicht erlaubt.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(raw, indent=2, sort_keys=True).encode("utf-8")
        tmp_path = self._path.with_suffix(".tmp")
        # Tmp-File mit 0600 *anlegen*, nicht erst nach dem Schreiben
        # chmod-en — sonst läge der Ciphertext zwischen Write und
        # os.replace mit umask-Default (oft 0644) lesbar herum
        # (Copilot finding #2 / Issue #450 P1.3).
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError("Konnte vollständigen Secret-Store-Payload nicht schreiben")
                offset += written
        finally:
            os.close(fd)
        os.replace(tmp_path, self._path)
        # Defense in depth: nach dem Replace nochmal chmod, damit
        # bei umask-restriktiven Hosts oder ACL-Edge-Cases der
        # finale Pfad garantiert 0600 hat. Bei NFS-Mounts ohne
        # chmod-Permission ist das kein Fail.
        try:
            os.chmod(self._path, 0o600)
        except OSError as exc:
            logger.warning(
                "Konnte Rechte auf %s nicht auf 0600 setzen: %s",
                self._path,
                exc,
            )

    def list_entries(self) -> list[LlmProviderKeyEntry]:
        with self._lock:
            raw = self._read_raw()
        return [self._to_entry(pid, payload) for pid, payload in raw.get("entries", {}).items()]

    def get_entry(self, provider_id: str) -> Optional[LlmProviderKeyEntry]:
        with self._lock:
            raw = self._read_raw()
        payload = raw.get("entries", {}).get(provider_id)
        if payload is None:
            return None
        return self._to_entry(provider_id, payload)

    def get_plaintext(self, provider_id: str) -> Optional[str]:
        """Entschlüsselt und gibt den Klartext-Key zurück. ``None`` wenn fehlt."""
        with self._lock:
            raw = self._read_raw()
        payload = raw.get("entries", {}).get(provider_id)
        if payload is None:
            return None
        ciphertext = payload.get("ciphertext")
        if not ciphertext:
            return None
        try:
            return self._fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretDecryptionError(
                "LLM-Provider-Key konnte nicht entschlüsselt werden. "
                f"AGORA_SECRET_KEY passt nicht zum Ciphertext für '{provider_id}'."
            ) from exc

    def upsert(
        self,
        provider_id: str,
        *,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> LlmProviderKeyEntry:
        if not api_key or len(api_key) < 4:
            raise ValueError("api_key zu kurz")
        ciphertext = self._fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")
        masked = _mask_key(api_key)
        now = _now()
        with self._lock, self._file_lock():
            raw = self._read_raw()
            entries = raw.setdefault("entries", {})
            existing = entries.get(provider_id)
            created_at = existing["created_at"] if existing else now.isoformat()
            entry_payload = {
                "ciphertext": ciphertext,
                "masked_value": masked,
                "base_url": base_url,
                "created_at": created_at,
                "updated_at": now.isoformat(),
                "last_validated_at": existing.get("last_validated_at") if existing else None,
                "last_validation_ok": existing.get("last_validation_ok") if existing else None,
            }
            entries[provider_id] = entry_payload
            raw["version"] = 1
            self._write_raw(raw)
        return self._to_entry(provider_id, entry_payload)

    def mark_validated(self, provider_id: str, *, ok: bool) -> Optional[LlmProviderKeyEntry]:
        now = _now()
        with self._lock, self._file_lock():
            raw = self._read_raw()
            entry = raw.get("entries", {}).get(provider_id)
            if entry is None:
                return None
            entry["last_validated_at"] = now.isoformat()
            entry["last_validation_ok"] = ok
            self._write_raw(raw)
        return self._to_entry(provider_id, entry)

    def delete(self, provider_id: str) -> bool:
        with self._lock, self._file_lock():
            raw = self._read_raw()
            entries = raw.get("entries", {})
            if provider_id not in entries:
                return False
            del entries[provider_id]
            self._write_raw(raw)
        return True

    def reset_for_tests(self) -> None:
        """Nur in Tests — löscht das gesamte Store-File."""
        with self._lock:
            if self._path.exists():
                self._path.unlink()

    @staticmethod
    def _to_entry(provider_id: str, payload: dict) -> LlmProviderKeyEntry:
        masked = payload.get("masked_value")
        if not masked:
            # Legacy-Fallback, falls jemand das File manuell editiert hat
            masked = "key-...XXXX"
        return LlmProviderKeyEntry(
            provider_id=provider_id,
            masked_value=masked,
            base_url=payload.get("base_url"),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            last_validated_at=(
                datetime.fromisoformat(payload["last_validated_at"])
                if payload.get("last_validated_at")
                else None
            ),
            last_validation_ok=payload.get("last_validation_ok"),
        )


_store_singleton: Optional[LlmProviderSecretsStore] = None
_singleton_lock = threading.Lock()


def get_llm_provider_secrets_store() -> LlmProviderSecretsStore:
    """Singleton-Accessor — pro Prozess geteilt."""
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                _store_singleton = LlmProviderSecretsStore()
    return _store_singleton


def reset_singleton_for_tests() -> None:
    """Nur in Tests aufrufen — zwingt Neuinitialisierung des Singletons."""
    global _store_singleton
    with _singleton_lock:
        _store_singleton = None
