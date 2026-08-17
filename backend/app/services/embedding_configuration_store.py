"""Atomarer, secret-freier Store für Embedding-Konfigurationen (Onboarding Slice 4.2).

Persistiert ausschließlich öffentliche Embedding-Konfigurations-Metadaten
(Provider-Referenz, Modell, verifizierte Dimension, Status, Scope, Zeitstempel).
API-Keys werden über die bestehende ``provider_connection_id`` referenziert
und liegen im verschlüsselten ``LlmProviderSecretsStore`` — niemals hier.

Persistenz: eine flache JSON-Datei unter ``AGORA_DATA_DIR/embedding_configurations.json``
mit ``flock``-basierter Prozesssperre (analog zu ``provider_connection_store.py``)
und ``os.replace``-basiertem atomarem Write. Datei-Modus 0600, damit andere
Lokale-Nutzer die Konfiguration nicht mitlesen können, auch wenn der Default-
Data-Dir world-readable sein sollte.

Schema-Stabilität: das gespeicherte Format ist explizit versioniert
(``schema_version: 1``). Eine Schema-Migration ist Aufgabe einer künftigen
Sub-Slice, nicht dieses Moduls.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import fcntl

from app.services.data_dir import resolve_data_dir as _resolve_data_dir

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationScope,
    EmbeddingConfigurationStatus,
    EmbeddingIndexVersion,
    EmbeddingProviderKind,
)

_STORE_FILENAME = "embedding_configurations.json"
_INDEX_FILENAME = "embedding_index_versions.json"
_SCHEMA_VERSION = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_configuration_id() -> str:
    """Erzeugt eine neue Konfigurations-ID. Hex-Schema, weil in Dateinamen
    und API-Pfaden stabil; Zufall (16 Bytes) verhindert Enumeration.
    """
    import secrets
    return f"emb-{secrets.token_hex(16)}"


class EmbeddingConfigurationStore:
    """Persistiert Embedding-Konfigurationen und versionierte Indizes.

    Konfigurationen und Index-Versionen leben in getrennten Dateien, damit
    das Schreiben einer neuen Probe (Configuration) den Index-Katalog nicht
    berührt. Beide Dateien teilen sich denselben Data-Dir und dieselbe
    Lock-Konvention.
    """

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._config_path = self._data_dir / _STORE_FILENAME
        self._index_path = self._data_dir / _INDEX_FILENAME

    # ------------------------------------------------------------------
    # Konfigurationen
    # ------------------------------------------------------------------

    def list_configurations(
        self, *, scope: Optional[str] = None
    ) -> list[EmbeddingConfiguration]:
        with self._lock:
            raw = self._read_raw(self._config_path)
        items = [
            EmbeddingConfiguration.model_validate(payload)
            for payload in raw["configurations"].values()
        ]
        if scope is None:
            return items
        return [c for c in items if c.scope == scope]

    def get_configuration(self, configuration_id: str) -> EmbeddingConfiguration | None:
        with self._lock:
            raw = self._read_raw(self._config_path)
        payload = raw["configurations"].get(configuration_id)
        if payload is None:
            return None
        return EmbeddingConfiguration.model_validate(payload)

    def get_active_global_configuration(self) -> EmbeddingConfiguration | None:
        for config in self.list_configurations(scope="global"):
            if config.status == "active":
                return config
        return None

    def upsert_configuration(
        self,
        *,
        configuration_id: Optional[str],
        provider_connection_id: str,
        provider_kind: EmbeddingProviderKind,
        model_id: str,
        dimensions: int,
        scope: EmbeddingConfigurationScope,
        project_id: Optional[str],
        status: EmbeddingConfigurationStatus = "proposed",
        status_message: Optional[str] = None,
        last_validated_at: Optional[datetime] = None,
    ) -> EmbeddingConfiguration:
        cid = configuration_id or _new_configuration_id()
        now = _now()
        with self._lock, self._process_lock(self._config_path):
            raw = self._read_raw(self._config_path)
            existing_payload = raw["configurations"].get(cid)
            existing = (
                EmbeddingConfiguration.model_validate(existing_payload)
                if existing_payload is not None
                else None
            )
            # Wenn sich relevante Felder (Provider-Connection, Provider-Art,
            # Modell, Dimension) aendern, ist die alte ``last_validated_at``-
            # Validierung nicht mehr aussagekraeftig — wir verwerfen sie.
            # Status wird ohnehin zurueck auf ``proposed`` gesetzt, daher
            # waere der alte Zeitstempel inkonsistent.
            relevant_fields_changed = (
                existing is not None
                and (
                    existing.provider_connection_id != provider_connection_id
                    or existing.provider_kind != provider_kind
                    or existing.model_id != model_id
                    or existing.dimensions != dimensions
                )
            )
            resolved_last_validated_at: datetime | None
            if relevant_fields_changed:
                resolved_last_validated_at = None
            elif last_validated_at is not None:
                resolved_last_validated_at = last_validated_at
            else:
                resolved_last_validated_at = (
                    existing.last_validated_at if existing else None
                )
            config = EmbeddingConfiguration(
                id=cid,
                provider_connection_id=provider_connection_id,
                provider_kind=provider_kind,
                model_id=model_id,
                dimensions=dimensions,
                scope=scope,
                project_id=project_id,
                index_version=existing.index_version if existing else 1,
                status=status,
                status_message=status_message,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                last_validated_at=resolved_last_validated_at,
            )
            raw["configurations"][cid] = config.model_dump(mode="json")
            self._write_raw(self._config_path, raw)
        return config

    def update_configuration_status(
        self,
        configuration_id: str,
        *,
        status: EmbeddingConfigurationStatus,
        status_message: Optional[str] = None,
        last_validated_at: Optional[datetime] = None,
        index_version: Optional[int] = None,
    ) -> EmbeddingConfiguration:
        with self._lock, self._process_lock(self._config_path):
            raw = self._read_raw(self._config_path)
            payload = raw["configurations"].get(configuration_id)
            if payload is None:
                raise KeyError(
                    f"Unbekannte Embedding-Konfiguration: {configuration_id}"
                )
            current = EmbeddingConfiguration.model_validate(payload)
            resolved_index_version = (
                index_version if index_version is not None else current.index_version
            )
            config = current.model_copy(
                update={
                    "status": status,
                    "status_message": status_message,
                    "updated_at": _now(),
                    "last_validated_at": last_validated_at,
                    "index_version": resolved_index_version,
                }
            )
            raw["configurations"][configuration_id] = config.model_dump(mode="json")
            self._write_raw(self._config_path, raw)
        return config

    def delete_configuration(self, configuration_id: str) -> bool:
        with self._lock, self._process_lock(self._config_path):
            raw = self._read_raw(self._config_path)
            if configuration_id not in raw["configurations"]:
                return False
            del raw["configurations"][configuration_id]
            self._write_raw(self._config_path, raw)
        return True

    # ------------------------------------------------------------------
    # Index-Versionen
    # ------------------------------------------------------------------

    def list_index_versions(self) -> list[EmbeddingIndexVersion]:
        with self._lock:
            raw = self._read_raw(self._index_path)
        return [
            EmbeddingIndexVersion.model_validate(payload)
            for payload in raw["versions"].values()
        ]

    def get_index_version(self, version: int) -> EmbeddingIndexVersion | None:
        for index in self.list_index_versions():
            if index.version == version:
                return index
        return None

    def get_active_index_version(self) -> EmbeddingIndexVersion | None:
        for index in self.list_index_versions():
            if index.status == "active":
                return index
        return None

    def next_index_version(self) -> int:
        with self._lock:
            raw = self._read_raw(self._index_path)
        versions = raw["versions"].keys()
        if not versions:
            return 1
        return max(int(v) for v in versions) + 1

    def upsert_index_version(
        self,
        *,
        version: Optional[int],
        provider_connection_id: str,
        model_id: str,
        dimensions: int,
        index_name: str,
        property_key: str,
        status: str = "active",
        retired_at: Optional[datetime] = None,
    ) -> EmbeddingIndexVersion:
        v = version if version is not None else self.next_index_version()
        now = _now()
        with self._lock, self._process_lock(self._index_path):
            raw = self._read_raw(self._index_path)
            existing_payload = raw["versions"].get(str(v))
            existing = (
                EmbeddingIndexVersion.model_validate(existing_payload)
                if existing_payload is not None
                else None
            )
            index = EmbeddingIndexVersion(
                version=v,
                provider_connection_id=provider_connection_id,
                model_id=model_id,
                dimensions=dimensions,
                index_name=index_name,
                property_key=property_key,
                status=status,  # type: ignore[arg-type]
                created_at=existing.created_at if existing else now,
                retired_at=retired_at,
            )
            raw["versions"][str(v)] = index.model_dump(mode="json")
            self._write_raw(self._index_path, raw)
        return index

    def supersede_index_version(self, version: int) -> EmbeddingIndexVersion:
        """Markiert eine Index-Version als ``superseded`` (nicht mehr aktiv,
        aber noch lesbar). Wird vom Migrations-Flow in Slice 4.3 genutzt.
        """
        with self._lock, self._process_lock(self._index_path):
            raw = self._read_raw(self._index_path)
            payload = raw["versions"].get(str(version))
            if payload is None:
                raise KeyError(f"Unbekannte Index-Version: {version}")
            index = EmbeddingIndexVersion.model_validate(payload).model_copy(
                update={"status": "superseded"}
            )
            raw["versions"][str(version)] = index.model_dump(mode="json")
            self._write_raw(self._index_path, raw)
        return index

    # ------------------------------------------------------------------
    # Persistenz-Mechanik
    # ------------------------------------------------------------------


    def _read_raw(self, path: Path) -> dict:
        # Default-Container anhand des Dateinamens bestimmen: die
        # Konfigurationsdatei hat einen "configurations"-Key, die
        # Indexdatei einen "versions"-Key. Wenn die Datei fehlt, wird
        # der passende leere Container zurueckgegeben, damit der
        # Aufrufer ohne Sonderbehandlung weiterarbeiten kann.
        if "configurations" in path.name:
            empty: dict = {
                "schema_version": _SCHEMA_VERSION,
                "configurations": {},
            }
        else:
            empty = {
                "schema_version": _SCHEMA_VERSION,
                "versions": {},
            }
        if not path.exists():
            return empty
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Top-Level muss ein Objekt sein")
            return raw
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Konnte Embedding-Store nicht lesen ({path}): {exc}"
            ) from exc

    @contextmanager
    def _process_lock(self, path: Path) -> Iterator[None]:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _write_raw(self, path: Path, raw: dict) -> None:
        tmp_path = path.with_suffix(".tmp")
        payload = json.dumps(raw, indent=2, sort_keys=True).encode("utf-8")
        try:
            fd = os.open(
                str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
            try:
                offset = 0
                while offset < len(payload):
                    written = os.write(fd, payload[offset:])
                    if written <= 0:
                        raise OSError("Unvollständiger Write in temporäre Store-Datei")
                    offset += written
            finally:
                os.close(fd)
            os.replace(tmp_path, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                # chmod kann auf manchen NFS-/Volume-Mounts fehlschlagen
                pass
        except OSError as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(
                f"Konnte Embedding-Store nicht schreiben ({path}): {exc}"
            ) from exc


__all__ = [
    "EmbeddingConfigurationStore",
]
