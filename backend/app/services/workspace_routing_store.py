"""Persistenter JSON-Store für Workspace-LLM-Routing-Defaults.

Storage-Pfad: ``backend/data/workspace_llm_routing.json`` (überschreibbar via
``AGORA_DATA_DIR``-Env). File-Locking via threading.Lock; atomic write über
tmp-File + rename.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..contracts.llm_routing_contract import StageId, StageLLMRoute
from ..contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults

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
    """File-backed JSON-Store für Workspace-Routing-Defaults."""

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._path = self._data_dir / _STORE_FILENAME

    def load(self) -> WorkspaceLlmRoutingDefaults:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> WorkspaceLlmRoutingDefaults:
        if not self._path.exists():
            return WorkspaceLlmRoutingDefaults()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return WorkspaceLlmRoutingDefaults()
        return WorkspaceLlmRoutingDefaults.model_validate(raw)

    def _save_unlocked(self, model: WorkspaceLlmRoutingDefaults) -> WorkspaceLlmRoutingDefaults:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = model.model_copy(update={"updated_at": _now()})
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp_path, self._path)
        return payload

    def save(self, model: WorkspaceLlmRoutingDefaults) -> WorkspaceLlmRoutingDefaults:
        with self._lock:
            return self._save_unlocked(model)

    def set_stage_override(
        self, stage_id: StageId, route: Optional[StageLLMRoute]
    ) -> WorkspaceLlmRoutingDefaults:
        with self._lock:
            current = self._load_unlocked()
            overrides = dict(current.stage_overrides)
            if route is None:
                overrides.pop(stage_id, None)
            else:
                overrides[stage_id] = route
            updated = current.model_copy(update={"stage_overrides": overrides})
            return self._save_unlocked(updated)

    def set_global_default(self, route: StageLLMRoute) -> WorkspaceLlmRoutingDefaults:
        with self._lock:
            current = self._load_unlocked()
            updated = current.model_copy(update={"global_default": route})
            return self._save_unlocked(updated)

    def reset_for_tests(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()


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
