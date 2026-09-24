"""Dateibasierter Adapter für Run-Registry-Manifeste (#1579).

Das ist die bisherige Datei-I/O-Logik aus ``RunRegistry._read_run``,
``RunRegistry._write_run`` und dem Scan-Teil von ``RunRegistry.list_runs``,
hinter den ``RunRepository``-Port gelegt — eine Verschiebung, keine
Neuimplementierung.  Pfadbildung, Dateiname (``<run_id>.json``) und der Inhalt
des Manifests bleiben unveränderlich, damit eine bestehende Installation nach
diesem Umbau dieselben Dateien liest und schreibt wie davor.

Warum ``registry_dir`` hereingereicht wird und nicht hier steht:
``RunRegistry.REGISTRY_DIR`` ist ein Klassenattribut, das Testdateien zur
Laufzeit auf ein temporäres Verzeichnis umbiegen.  Würde der Adapter den Pfad
selbst aus ``Config.UPLOAD_FOLDER`` ableiten, liefe er an diesen Patches vorbei
und die Tests schrieben in das echte Upload-Verzeichnis.  Der Aufrufer bleibt
deshalb die Quelle des Pfades.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from ..contracts.run_record_contract import RunRecord
from ..utils.json_io import read_json_file, write_json_atomic
from ..utils.logger import get_logger
from ..utils.path_safety import safe_join_within_root, validate_path_id

logger = get_logger("agora.run_store")

_MISSING = object()


class FileRunRepository:
    """Run-Manifeste als ``<run_id>.json`` je Eintrag unter ``registry_dir``."""

    def __init__(self, registry_dir: str) -> None:
        self.registry_dir = registry_dir

    # --- Pfade ---------------------------------------------------------------

    def _ensure_dir(self) -> None:
        os.makedirs(self.registry_dir, exist_ok=True)

    def _run_path(self, run_id: str) -> str:
        validate_path_id(run_id, field_name="run_id")
        return safe_join_within_root(self.registry_dir, f"{run_id}.json")

    # --- Port ----------------------------------------------------------------

    def get(self, run_id: str) -> Optional[RunRecord]:
        """Record oder ``None`` — niemals Raise bei fehlendem Run.

        Korruptes JSON gibt ebenfalls ``None`` zurück (gleiche Semantik wie
        ``RunRegistry._read_run``).
        """
        path = self._run_path(run_id)
        if not os.path.exists(path):
            return None
        data: Any = read_json_file(
            path,
            default=_MISSING,
            logger=logger,
            description=f"run manifest {run_id}",
        )
        if data is _MISSING or not isinstance(data, dict):
            return None
        try:
            return RunRecord(**data)
        except Exception:  # noqa: BLE001 — korruptes Manifest zählt als fehlend
            logger.warning("Skipping unreadable run manifest %s", run_id)
            return None

    def save(self, record: RunRecord) -> RunRecord:
        """Schreibt den Record atomar (kein Reader sieht halbe Dateien)."""
        self._ensure_dir()
        path = self._run_path(record.run_id)
        write_json_atomic(path, record.to_manifest())
        return record

    def list_all(self, *, limit: int = 100_000) -> list[RunRecord]:
        """Alle Records, neueste zuerst (``updated_at`` absteigend).

        Korrupte Dateien werden übersprungen.  Temp-Dateien aus atomaren
        Writes (``.tmp-json-*.json``) werden herausgefiltert.
        """
        self._ensure_dir()

        records: list[RunRecord] = []
        for filename in os.listdir(self.registry_dir):
            if not filename.endswith(".json"):
                continue
            if filename.startswith("."):
                continue
            run_id = filename[:-5]
            record = self.get(run_id)
            if record is not None:
                records.append(record)

        records.sort(
            key=lambda r: r.updated_at or r.started_at or "",
            reverse=True,
        )
        return records[:limit]
