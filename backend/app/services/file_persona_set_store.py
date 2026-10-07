"""Dateibasierter Adapter fuer Personasaetze (Issue #1807, Etappe 7).

Jeder Satz liegt als ``<storage_root>/<set_id>.json``; Standard ist
``<UPLOAD_FOLDER>/persona_sets``. Geschrieben wird atomar mit ``fsync``
(``app.utils.json_io.write_json_atomic``): ein Leser sieht nie eine halb
geschriebene Datei. Storage- und Permission-Fehler (``OSError``) werden nicht
geschluckt.

**Warum ``storage_root`` hereingereicht wird:** wie bei den uebrigen
Dateiadaptern wird der Pfad zur Laufzeit von Tests umgebogen; ein beim Import
eingefrorener Pfad liefe daran vorbei.

**Atomizitaet von ``mark_used``:** ein prozessweites ``RLock`` serialisiert
alle Schreibvorgaenge. Das genuegt, weil Agora mit genau einem Web-Worker
laeuft (``docs/runbooks/``); ein zweiter Prozess auf derselben Ablage waere
nicht abgedeckt. Der PostgreSQL-Adapter sperrt dafuer die Zeile.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from typing import List, Optional

from ..config import Config
from ..contracts.persona_set_contract import PersonaSetRecord
from ..utils.json_io import write_json_atomic
from ..utils.logger import get_logger
from ..utils.validation import join_within

logger = get_logger('agora.persona_sets.file_store')

#: Die Satzkennung ist zugleich der Dateiname. Erlaubt ist nur, was ein
#: Dateiname unbedenklich tragen kann; ``join_within`` bleibt die zweite Schranke.
_SAFE_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')

#: Gemeinsam fuer alle Adapterinstanzen: die Fabrik baut je Aufruf eine neue.
_WRITE_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat()


class FilePersonaSetRepository:
    """Personasaetze als JSON-Datei je Satz."""

    def __init__(self, storage_root: str) -> None:
        self.storage_root = storage_root

    # --- Pfade ------------------------------------------------------------

    def _path(self, set_id: str) -> Optional[str]:
        """Dateipfad des Satzes oder ``None``, wenn die Kennung kein Dateiname sein darf."""
        if not _SAFE_ID.fullmatch(set_id):
            return None
        return join_within(self.storage_root, f'{set_id}.json')

    # --- Port -------------------------------------------------------------

    def get(self, set_id: str) -> Optional[PersonaSetRecord]:
        path = self._path(set_id)
        if path is None or not os.path.exists(path):
            return None
        # Bewusst kein ``read_json_file``: das macht aus ``OSError`` einen
        # Vorgabewert. Eine kaputte Datei (``JSONDecodeError`` ist ein
        # ``ValueError``) ist hier kein "nicht vorhanden", und Rechte- oder
        # Datentraegerfehler sollen den Aufrufer erreichen.
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return PersonaSetRecord.model_validate(data)

    def list(self) -> List[PersonaSetRecord]:
        """Alle Saetze, neuester zuerst.

        Ein inhaltlich kaputter Datensatz (kein gueltiges JSON, Vertrag
        verletzt) laesst die Liste stehen und wird mit seiner Kennung als
        Warnung protokolliert. ``OSError`` — unlesbarer Datentraeger, fehlende
        Rechte — wird nicht geschluckt.
        """
        if not os.path.isdir(self.storage_root):
            return []

        records: List[PersonaSetRecord] = []
        for name in os.listdir(self.storage_root):
            if name.startswith('.') or not name.endswith('.json'):
                continue
            set_id = name[: -len('.json')]
            try:
                record = self.get(set_id)
            except ValueError as exc:
                # ValueError deckt pydantic.ValidationError mit ab.
                logger.warning(
                    'Skipping unreadable persona set %s: %s',
                    set_id,
                    type(exc).__name__,
                )
                continue
            if record is not None:
                records.append(record)

        records.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return records

    def save(self, record: PersonaSetRecord) -> None:
        path = self._require_path(record.id)
        with _WRITE_LOCK:
            existing = self.get(record.id)
            if existing is not None:
                # Die Sperre aendert nur ``mark_used`` (Port-Docstring).
                record.locked_at = existing.locked_at
                record.used_by_simulation_ids = list(existing.used_by_simulation_ids)
            record.updated_at = _now()
            self._write(path, record)

    def delete(self, set_id: str) -> bool:
        path = self._path(set_id)
        if path is None:
            return False
        with _WRITE_LOCK:
            if not os.path.exists(path):
                return False
            os.remove(path)
            return True

    def mark_used(
        self, set_id: str, simulation_id: str
    ) -> Optional[PersonaSetRecord]:
        if not simulation_id:
            raise ValueError('simulation_id must not be empty')
        path = self._path(set_id)
        if path is None:
            return None
        with _WRITE_LOCK:
            record = self.get(set_id)
            if record is None:
                return None
            if simulation_id in record.used_by_simulation_ids:
                return record
            now = _now()
            record.used_by_simulation_ids.append(simulation_id)
            if record.locked_at is None:
                record.locked_at = now
            record.updated_at = now
            self._write(path, record)
            return record

    # --- intern -----------------------------------------------------------

    def _require_path(self, set_id: str) -> str:
        path = self._path(set_id)
        if path is None:
            raise ValueError(
                f'persona set id {set_id!r} is not a valid file name '
                '(allowed: A-Z a-z 0-9 _ -, 1-64 characters)'
            )
        return path

    @staticmethod
    def _write(path: str, record: PersonaSetRecord) -> None:
        # Vor dem Schreiben validieren: ein Datensatz, der den Vertrag beim
        # Zurueckladen verletzte, soll gar nicht erst auf die Platte.
        validated = PersonaSetRecord.model_validate(record.model_dump(mode='json'))
        write_json_atomic(path, validated.model_dump(mode='json'))


def get_file_persona_set_repository(
    storage_root: Optional[str] = None,
) -> FilePersonaSetRepository:
    """Baut den Dateiadapter.

    Ohne Angabe gilt ``<UPLOAD_FOLDER>/persona_sets``.
    """
    if storage_root is None:
        storage_root = os.path.join(Config.UPLOAD_FOLDER, 'persona_sets')
    return FilePersonaSetRepository(storage_root)
