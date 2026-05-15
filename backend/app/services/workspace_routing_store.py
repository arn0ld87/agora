"""Persistenter JSON-Store für Workspace-LLM-Routing-Defaults.

Storage-Pfad: ``backend/data/workspace_llm_routing.json`` (überschreibbar via
``AGORA_DATA_DIR``-Env). Locking auf zwei Ebenen:

- ``threading.Lock`` schützt innerhalb eines Python-Prozesses.
- ``fcntl.flock`` auf einer ``.lock``-Sidecar-Datei schützt prozessübergreifend
  (mehrere Gunicorn-Worker). Load-modify-save-Operationen halten den
  File-Lock über den gesamten Roundtrip — sonst gehen parallele
  ``set_stage_override``-Calls verloren (Lost Update).

Atomic write über tmp-File + ``os.replace``; geschriebene Dateien bekommen
``0600`` (Issue #450 P1.3 — Provider-Secrets/Routing dürfen für andere User
auf dem Host nicht lesbar sein).
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

from ..contracts.llm_routing_contract import StageId, StageLLMRoute
from ..contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
from ..utils.logger import get_logger

logger = get_logger("agora.services.workspace_routing_store")

_DATA_DIR_ENV = "AGORA_DATA_DIR"
_STORE_FILENAME = "workspace_llm_routing.json"


def _resolve_data_dir() -> Path:
    raw = os.environ.get(_DATA_DIR_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceRoutingStore:
    """File-backed JSON-Store für Workspace-Routing-Defaults.

    Schreib-Operationen sind sowohl innerhalb eines Prozesses
    (``threading.Lock``) als auch zwischen Prozessen (``fcntl.flock`` auf
    ``self._path.with_suffix(".lock")``) atomar. Read-modify-write-Sequenzen
    in ``set_stage_override`` / ``set_global_default`` halten den File-Lock
    über Load **und** Save — sonst können zwei parallele Worker das gleiche
    Routing-Dokument überschreiben und Updates verlieren.
    """

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._path = self._data_dir / _STORE_FILENAME
        self._lock_path = self._path.with_suffix(".lock")

    @contextmanager
    def _file_lock(self) -> Iterator[IO[str]]:
        """Hält einen exklusiven ``fcntl.flock`` für die Lebensdauer des Blocks.

        Die Lock-Datei liegt im selben Verzeichnis wie der Store und wird beim
        ersten Schreib-Versuch erstellt. Der Lock wird auch beim Lesen
        verwendet, sobald die Operation Teil einer Read-modify-write-Kette ist
        (``set_stage_override``, ``set_global_default``). Reine ``load()``-
        Aufrufe verzichten auf den File-Lock — sie sind tolerant gegenüber
        einem zeitgleichen ``os.replace``, da dieser POSIX-atomar ist.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield lock_fh
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def load(self) -> WorkspaceLlmRoutingDefaults:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> WorkspaceLlmRoutingDefaults:
        if not self._path.exists():
            return WorkspaceLlmRoutingDefaults()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as exc:
            # Dateisystem-Fehler beim Lesen — nicht silent schlucken (Gemini MEDIUM #4)
            logger.error(
                "Workspace-Routing-Store konnte nicht gelesen werden (%s): %s — "
                "verwende leere Defaults",
                self._path,
                exc,
            )
            return WorkspaceLlmRoutingDefaults()
        except json.JSONDecodeError as exc:
            # Korrupte Datei: laut loggen statt silent Default zurückgeben.
            # Beim nächsten save() würde die Datei überschrieben, was zu
            # Datenverlust führt. Der Nutzer muss die Korruption sehen.
            logger.error(
                "Workspace-Routing-Store ist korrupt (%s): %s — "
                "verwende leere Defaults. Bitte Datei manuell prüfen oder löschen.",
                self._path,
                exc,
            )
            return WorkspaceLlmRoutingDefaults()
        return WorkspaceLlmRoutingDefaults.model_validate(raw)

    def _save_unlocked(self, model: WorkspaceLlmRoutingDefaults) -> WorkspaceLlmRoutingDefaults:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = model.model_copy(update={"updated_at": _now()})
        serialized = json.dumps(
            payload.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode("utf-8")
        tmp_path = self._path.with_suffix(".tmp")
        # Tmp-File mit 0600 anlegen, nicht erst chmod nach dem Write — sonst
        # liegt der Inhalt zwischen Write und os.replace mit umask-Default
        # auf der Platte (Copilot finding #2 / Issue #450 P1.3). Routing-
        # Defaults enthalten zwar nur Provider-IDs + Modell-Strings, das
        # Härtungs-Level bleibt aber konsistent mit dem Secrets-Store.
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.write(fd, serialized)
        finally:
            os.close(fd)
        os.replace(tmp_path, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError as exc:
            # Bei gemounteten Volumes mit fixer UID/GID kann chmod fehlschlagen;
            # in dem Fall darf der Store trotzdem schreiben. Wir loggen,
            # damit Operator-Doku-Hinweise nachvollziehbar bleiben.
            logger.warning(
                "Konnte Rechte auf %s nicht auf 0600 setzen: %s",
                self._path,
                exc,
            )
        return payload

    def save(self, model: WorkspaceLlmRoutingDefaults) -> WorkspaceLlmRoutingDefaults:
        with self._lock, self._file_lock():
            return self._save_unlocked(model)

    def set_stage_override(
        self, stage_id: StageId, route: Optional[StageLLMRoute]
    ) -> WorkspaceLlmRoutingDefaults:
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            overrides = dict(current.stage_overrides)
            if route is None:
                overrides.pop(stage_id, None)
            else:
                overrides[stage_id] = route
            updated = current.model_copy(update={"stage_overrides": overrides})
            return self._save_unlocked(updated)

    def set_global_default(self, route: StageLLMRoute) -> WorkspaceLlmRoutingDefaults:
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            updated = current.model_copy(update={"global_default": route})
            return self._save_unlocked(updated)

    def reset_for_tests(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()
            if self._lock_path.exists():
                self._lock_path.unlink()


_store_singleton: Optional[WorkspaceRoutingStore] = None
_singleton_lock = threading.Lock()


def get_workspace_routing_store() -> WorkspaceRoutingStore:
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                _store_singleton = WorkspaceRoutingStore()
    return _store_singleton


def reset_singleton_for_tests() -> None:
    global _store_singleton
    with _singleton_lock:
        _store_singleton = None
