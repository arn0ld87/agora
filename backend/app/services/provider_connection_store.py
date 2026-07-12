"""Atomarer, secret-freier Store für Provider-Verbindungsmetadaten."""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import fcntl

from app.contracts.ai_provider_contract import (
    ProviderConnection,
    ProviderConnectionUpsertRequest,
    ProviderStatus,
)
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore

_DATA_DIR_ENV = "AGORA_DATA_DIR"
_STORE_FILENAME = "provider_connections.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_data_dir() -> Path:
    raw = os.environ.get(_DATA_DIR_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


class ProviderConnectionStore:
    """Persistiert ausschließlich öffentliche ``ProviderConnection``-Metadaten."""

    def __init__(
        self,
        *,
        data_dir: Optional[Path] = None,
        secrets_store: Optional[LlmProviderSecretsStore] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._path = self._data_dir / _STORE_FILENAME
        self._secrets_store = secrets_store or LlmProviderSecretsStore(
            data_dir=self._data_dir
        )

    def list_connections(self) -> list[ProviderConnection]:
        with self._lock:
            raw = self._read_raw()
        return [
            ProviderConnection.model_validate(payload)
            for payload in raw["connections"].values()
        ]

    def upsert_connection(
        self, request: ProviderConnectionUpsertRequest
    ) -> ProviderConnection:
        connection_id = request.provider_kind
        now = _now()
        api_key = (
            request.api_key.get_secret_value() if request.api_key is not None else None
        )

        with self._lock, self._process_lock():
            raw = self._read_raw()
            existing_payload = raw["connections"].get(connection_id)
            existing = (
                ProviderConnection.model_validate(existing_payload)
                if existing_payload is not None
                else None
            )
            secret_ref = connection_id if api_key else (existing.secret_ref if existing else None)
            connection = ProviderConnection(
                id=connection_id,
                provider_kind=request.provider_kind,
                display_name=request.display_name,
                transport="local" if request.provider_kind == "ollama" else "http",
                auth_mode="api_key" if secret_ref else "none",
                base_url=request.base_url,
                enabled=request.enabled,
                status=existing.status if existing else "unknown",
                status_message=existing.status_message if existing else None,
                secret_ref=secret_ref,
                capabilities=existing.capabilities if existing else {},
                created_at=existing.created_at if existing else now,
                updated_at=now,
                last_tested_at=existing.last_tested_at if existing else None,
            )
            raw["connections"][connection_id] = connection.model_dump(mode="json")
            self._write_raw(raw)

        if api_key:
            self._secrets_store.upsert(connection_id, api_key=api_key)
        return connection

    def delete_connection(self, connection_id: str) -> bool:
        with self._lock, self._process_lock():
            raw = self._read_raw()
            payload = raw["connections"].get(connection_id)
            if payload is None:
                return False
            connection = ProviderConnection.model_validate(payload)
            del raw["connections"][connection_id]
            self._write_raw(raw)

        if connection.secret_ref:
            self._secrets_store.delete(connection.secret_ref)
        return True

    def update_probe(
        self,
        connection_id: str,
        *,
        status: ProviderStatus,
        status_message: str | None,
        tested_at: datetime,
    ) -> ProviderConnection:
        with self._lock, self._process_lock():
            raw = self._read_raw()
            payload = raw["connections"].get(connection_id)
            if payload is None:
                raise KeyError(f"Unbekannte Provider-Verbindung: {connection_id}")
            connection = ProviderConnection.model_validate(payload).model_copy(
                update={
                    "status": status,
                    "status_message": status_message,
                    "updated_at": _now(),
                    "last_tested_at": tested_at,
                }
            )
            raw["connections"][connection_id] = connection.model_dump(mode="json")
            self._write_raw(raw)
        return connection

    def _read_raw(self) -> dict:
        if not self._path.exists():
            return {"version": 1, "connections": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("connections"), dict):
                raise ValueError("connections muss ein Objekt sein")
            return raw
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Konnte Provider-Connection-Store nicht lesen ({self._path}): {exc}"
            ) from exc

    @contextmanager
    def _process_lock(self) -> Iterator[None]:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_suffix(".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _write_raw(self, raw: dict) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        payload = json.dumps(raw, indent=2, sort_keys=True).encode("utf-8")
        try:
            fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                offset = 0
                while offset < len(payload):
                    written = os.write(fd, payload[offset:])
                    if written <= 0:
                        raise OSError("Unvollständiger Write in temporäre Store-Datei")
                    offset += written
            finally:
                os.close(fd)
            os.replace(tmp_path, self._path)
            os.chmod(self._path, 0o600)
        except OSError as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(
                f"Konnte Provider-Connection-Store nicht schreiben ({self._path}): {exc}"
            ) from exc
