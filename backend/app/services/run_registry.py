"""
Persistent run registry for long-running work.

Each run is stored as a JSON manifest in backend/uploads/run_registry/.
The registry complements TaskManager's in-memory state so runs survive
backend restarts and different subsystems can be queried uniformly.
"""

from __future__ import annotations

import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.json_io import read_json_file, write_json_atomic
from ..utils.logger import get_logger

logger = get_logger("agora.run_registry")

# Sentinel returned by ``read_json_file`` on missing files. A corrupt file
# also returns this default, so we distinguish the two cases by a preceding
# ``os.path.exists`` check.
_MISSING = object()


class RunRegistry:
    REGISTRY_DIR = os.path.join(Config.UPLOAD_FOLDER, "run_registry")

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache: Dict[str, Dict[str, Any]] = {}
                    cls._instance._lock = threading.Lock()
                    # Directory creation is deferred to _ensure_registry_dir()
                    # so that a bind-mounted uploads directory without the
                    # correct permissions for the container user does not abort
                    # the worker process at import time (PermissionError).
        return cls._instance

    def _ensure_registry_dir(self) -> None:
        """Create the registry directory if it does not exist yet.

        Called lazily before any actual file I/O so that a missing or
        not-yet-writable uploads bind-mount does not crash the worker on
        import/startup.
        """
        os.makedirs(self.REGISTRY_DIR, exist_ok=True)

    @staticmethod
    def canonical_status(raw_status: Optional[str]) -> str:
        value = (raw_status or "").strip().lower()
        mapping = {
            "pending": "pending",
            "planning": "processing",
            "generating": "processing",
            "processing": "processing",
            "running": "processing",
            "starting": "processing",
            "preparing": "processing",
            "ready": "completed",
            "completed": "completed",
            "failed": "failed",
            "paused": "paused",
            "stopped": "stopped",
            "stopping": "stopped",
            "idle": "pending",
            "not_started": "pending",
            "created": "pending",
        }
        return mapping.get(value, "pending")

    def _run_path(self, run_id: str) -> str:
        return os.path.join(self.REGISTRY_DIR, f"{run_id}.json")

    def _read_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        if run_id in self._cache:
            return deepcopy(self._cache[run_id])
        path = self._run_path(run_id)
        if not os.path.exists(path):
            return None
        data = read_json_file(path, default=_MISSING, logger=logger, description=f"run manifest {run_id}")
        if data is _MISSING or not isinstance(data, dict):
            # Corrupt or unreadable — treat as absent so list_runs et al. keep
            # working instead of crashing the whole history endpoint.
            return None
        self._cache[run_id] = data
        return deepcopy(data)

    def _write_run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_registry_dir()
        run_id = data["run_id"]
        path = self._run_path(run_id)
        write_json_atomic(path, data)
        self._cache[run_id] = deepcopy(data)
        return deepcopy(data)

    def create_run(
        self,
        run_type: str,
        entity_id: str,
        *,
        linked_ids: Optional[Dict[str, Any]] = None,
        parent_run_id: Optional[str] = None,
        status: str = "pending",
        progress: int = 0,
        message: str = "",
        error: Optional[str] = None,
        artifacts: Optional[Dict[str, Any]] = None,
        resume_capability: Optional[Dict[str, Any]] = None,
        branch_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = datetime.now().isoformat()
            run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
            manifest = {
                "run_id": run_id,
                "run_type": run_type,
                "entity_id": entity_id,
                "parent_run_id": parent_run_id,
                "status": self.canonical_status(status),
                "progress": progress,
                "message": message or "",
                "error": error,
                "started_at": now,
                "updated_at": now,
                "completed_at": now if self.canonical_status(status) in {"completed", "failed", "stopped"} else None,
                "artifacts": artifacts or {},
                "resume_capability": resume_capability or {},
                "branch_label": branch_label,
                "metadata": metadata or {},
                "linked_ids": linked_ids or {},
                "events": [],
            }
            self._append_event_locked(
                manifest,
                event_type="created",
                status=manifest["status"],
                progress=progress,
                message=message or f"{run_type} created",
            )
            return self._write_run(manifest)

    def _append_event_locked(
        self,
        manifest: Dict[str, Any],
        *,
        event_type: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        manifest.setdefault("events", []).append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "status": self.canonical_status(status or manifest.get("status")),
            "progress": manifest.get("progress") if progress is None else progress,
            "message": message or "",
            "error": error,
            "details": details or {},
        })

    def append_event(self, run_id: str, event_type: str, **kwargs) -> Optional[Dict[str, Any]]:
        with self._lock:
            manifest = self._read_run(run_id)
            if not manifest:
                return None
            self._append_event_locked(manifest, event_type=event_type, **kwargs)
            manifest["updated_at"] = datetime.now().isoformat()
            return self._write_run(manifest)

    def update_run(self, run_id: str, **updates) -> Optional[Dict[str, Any]]:
        with self._lock:
            manifest = self._read_run(run_id)
            if not manifest:
                return None

            old_status = manifest.get("status")
            if "status" in updates and updates["status"] is not None:
                manifest["status"] = self.canonical_status(updates["status"])
            if "progress" in updates and updates["progress"] is not None:
                manifest["progress"] = int(updates["progress"])
            if "message" in updates and updates["message"] is not None:
                manifest["message"] = updates["message"]
            if "error" in updates:
                manifest["error"] = updates["error"]
            if "entity_id" in updates and updates["entity_id"]:
                manifest["entity_id"] = updates["entity_id"]
            if "parent_run_id" in updates:
                manifest["parent_run_id"] = updates["parent_run_id"]
            if "branch_label" in updates:
                manifest["branch_label"] = updates["branch_label"]

            if updates.get("artifacts"):
                manifest.setdefault("artifacts", {}).update(updates["artifacts"])
            if updates.get("resume_capability"):
                manifest["resume_capability"] = updates["resume_capability"]
            if updates.get("linked_ids"):
                manifest.setdefault("linked_ids", {}).update(updates["linked_ids"])
            if updates.get("metadata"):
                manifest.setdefault("metadata", {}).update(updates["metadata"])

            manifest["updated_at"] = datetime.now().isoformat()
            if manifest["status"] in {"completed", "failed", "stopped"}:
                manifest["completed_at"] = manifest.get("completed_at") or manifest["updated_at"]
            elif manifest["status"] not in {"completed", "failed", "stopped"}:
                manifest["completed_at"] = None

            should_log = any(key in updates for key in ("status", "progress", "message", "error"))
            if should_log:
                self._append_event_locked(
                    manifest,
                    event_type=updates.get("event_type", "updated"),
                    status=manifest["status"],
                    progress=manifest.get("progress"),
                    message=manifest.get("message"),
                    error=manifest.get("error"),
                    details=updates.get("event_details"),
                )
            elif old_status != manifest.get("status"):
                self._append_event_locked(
                    manifest,
                    event_type="updated",
                    status=manifest["status"],
                    progress=manifest.get("progress"),
                    message=manifest.get("message"),
                    error=manifest.get("error"),
                )
            return self._write_run(manifest)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._read_run(run_id)

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        run = self.get_run(run_id)
        if not run:
            return []
        return run.get("events", [])

    def list_runs(
        self,
        *,
        project_id: Optional[str] = None,
        run_type: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        branch: Optional[str] = None,
        entity_id: Optional[str] = None,
        simulation_id: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List runs with optional filtering.

        ``statuses`` accepts a list of canonical status strings and supersedes
        the single ``status`` parameter when provided.  Both are kept for
        backwards compatibility with existing callers.

        ``since`` is an ISO-8601 string; only runs whose ``updated_at`` is
        >= that value are returned.  Filtering happens in-memory because the
        storage layer is file-based — this is a performance concern at scale.

        ``offset`` and ``limit`` implement basic pagination over the sorted
        result set.
        """
        self._ensure_registry_dir()

        # Normalise status filter to a set of canonical values.
        canonical_statuses: Optional[set[str]] = None
        if statuses:
            canonical_statuses = {self.canonical_status(s) for s in statuses}
        elif status:
            canonical_statuses = {self.canonical_status(status)}

        manifests: List[Dict[str, Any]] = []
        with self._lock:
            for filename in os.listdir(self.REGISTRY_DIR):
                if not filename.endswith(".json"):
                    continue
                # Skip tempfiles from atomic writes (.tmp-json-*.json).
                if filename.startswith("."):
                    continue
                run = self._read_run(filename[:-5])
                if not run:
                    continue
                linked = run.get("linked_ids", {})
                metadata = run.get("metadata", {})
                if project_id and linked.get("project_id") != project_id and metadata.get("project_id") != project_id:
                    continue
                if run_type and run.get("run_type") != run_type:
                    continue
                if canonical_statuses and run.get("status") not in canonical_statuses:
                    continue
                if branch and run.get("branch_label") != branch and metadata.get("branch_name") != branch:
                    continue
                if entity_id and run.get("entity_id") != entity_id:
                    continue
                if simulation_id and linked.get("simulation_id") != simulation_id:
                    continue
                if since and (run.get("updated_at") or "") < since:
                    continue
                manifests.append(run)

        manifests.sort(key=lambda item: item.get("updated_at") or item.get("started_at") or "", reverse=True)
        # Apply offset + limit for pagination.
        return manifests[offset: offset + limit]

    def aggregate_by_status(
        self,
        *,
        project_id: Optional[str] = None,
        run_type: Optional[str] = None,
        simulation_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Return a count-per-canonical-status dict over all matching runs.

        Intended to accompany ``list_runs`` responses when ``?aggregate=status``
        is requested.  Performs a full scan — same O(n) cost caveat as
        ``list_runs``.
        """
        counts: Dict[str, int] = {s: 0 for s in ("pending", "processing", "paused", "completed", "failed", "stopped")}
        # Use a large internal limit to count all matching runs, not just the
        # current page.
        all_runs = self.list_runs(
            project_id=project_id,
            run_type=run_type,
            simulation_id=simulation_id,
            limit=100_000,
            offset=0,
        )
        for run in all_runs:
            s = run.get("status", "pending")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def find_by_linked_id(self, key: str, value: str, *, run_type: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            run for run in self.list_runs(limit=1000, run_type=run_type)
            if run.get("linked_ids", {}).get(key) == value
        ]

    def get_latest_by_linked_id(self, key: str, value: str, *, run_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        matches = self.find_by_linked_id(key, value, run_type=run_type)
        return matches[0] if matches else None

    def sync_task(self, task: Any) -> Optional[Dict[str, Any]]:
        metadata = getattr(task, "metadata", {}) or {}
        run_id = metadata.get("run_id")
        if not run_id:
            return None
        return self.update_run(
            run_id,
            status=getattr(task, "status", None).value if getattr(task, "status", None) else None,
            progress=getattr(task, "progress", None),
            message=getattr(task, "message", None),
            error=getattr(task, "error", None),
            linked_ids={"task_id": getattr(task, "task_id", None)},
            metadata={"task_type": getattr(task, "task_type", None)},
        )
