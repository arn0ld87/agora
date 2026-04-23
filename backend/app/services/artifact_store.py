"""SimulationArtifactStore – Hexagonal port + adapters for simulation JSON artifacts.

Issue #13: SoC-Refactor. Services in ``backend/app/services`` and the simulation
API layer must not import ``utils.json_io`` or call ``open()`` on
``uploads/simulations/<sim_id>/*.json`` directly. Everything goes through this
port. Two adapters ship today:

* :class:`LocalFilesystemArtifactStore` – wraps :mod:`utils.json_io` and
  ``ArtifactLocator``, used in production.
* :class:`InMemoryArtifactStore` – pure-Python dict, used by tests.

Cloud adapters (S3, Azure Blob) can land later behind the same interface
without touching the domain.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

from ..utils.artifact_locator import ArtifactLocator
from ..utils.json_io import read_json_file, write_json_atomic
from ..utils.logger import get_logger

logger = get_logger("agora.artifact_store")


# ---------------------------------------------------------------------------
# Logical artifact namespace
# ---------------------------------------------------------------------------

# Logical name → on-disk filename. Subpath artifacts (``ipc_command/<uuid>``,
# ``ipc_response/<uuid>``) are resolved separately by ``_resolve_filename``.
_ARTIFACT_FILENAMES: dict[str, str] = {
    "state": "state.json",
    "simulation_config": "simulation_config.json",
    "run_state": "run_state.json",
    "control_state": "control_state.json",
    "reddit_profiles": "reddit_profiles.json",
    "env_status": "env_status.json",
}

_IPC_COMMAND_DIR = "ipc_commands"
_IPC_RESPONSE_DIR = "ipc_responses"

_IPC_COMMAND_PREFIX = "ipc_command/"
_IPC_RESPONSE_PREFIX = "ipc_response/"


def _resolve_relative_path(artifact: str) -> str:
    """Map a logical artifact name to a relative path inside the sim dir."""
    if artifact in _ARTIFACT_FILENAMES:
        return _ARTIFACT_FILENAMES[artifact]
    if artifact.startswith(_IPC_COMMAND_PREFIX):
        cmd_id = artifact[len(_IPC_COMMAND_PREFIX):]
        if not cmd_id or "/" in cmd_id or cmd_id.startswith("."):
            raise ValueError(f"Invalid IPC command id: {cmd_id!r}")
        return f"{_IPC_COMMAND_DIR}/{cmd_id}.json"
    if artifact.startswith(_IPC_RESPONSE_PREFIX):
        resp_id = artifact[len(_IPC_RESPONSE_PREFIX):]
        if not resp_id or "/" in resp_id or resp_id.startswith("."):
            raise ValueError(f"Invalid IPC response id: {resp_id!r}")
        return f"{_IPC_RESPONSE_DIR}/{resp_id}.json"
    raise KeyError(f"Unknown artifact name: {artifact!r}")


def _reverse_lookup(rel_path: str) -> Optional[str]:
    """Best-effort reverse: relative path → logical name (for ``list_artifacts``)."""
    for name, filename in _ARTIFACT_FILENAMES.items():
        if rel_path == filename:
            return name
    if rel_path.startswith(f"{_IPC_COMMAND_DIR}/") and rel_path.endswith(".json"):
        cmd_id = rel_path[len(_IPC_COMMAND_DIR) + 1:-5]
        if cmd_id:
            return f"{_IPC_COMMAND_PREFIX}{cmd_id}"
    if rel_path.startswith(f"{_IPC_RESPONSE_DIR}/") and rel_path.endswith(".json"):
        resp_id = rel_path[len(_IPC_RESPONSE_DIR) + 1:-5]
        if resp_id:
            return f"{_IPC_RESPONSE_PREFIX}{resp_id}"
    return None


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


@runtime_checkable
class SimulationArtifactStore(Protocol):
    """Hexagonal port for simulation JSON artifacts.

    All implementations MUST treat writes as atomic from a reader's perspective:
    a concurrent reader either sees the previous payload or the full new one,
    never a half-written state.
    """

    def read_json(
        self, simulation_id: str, artifact: str, default: Any = None
    ) -> Any:
        """Return the parsed JSON payload, or ``default`` if missing/unreadable."""
        ...

    def write_json(self, simulation_id: str, artifact: str, payload: Any) -> None:
        """Persist ``payload`` atomically under the logical ``artifact`` name."""
        ...

    def exists(self, simulation_id: str, artifact: str) -> bool:
        """True if the artifact is currently persisted."""
        ...

    def delete(self, simulation_id: str, artifact: str) -> None:
        """Remove the artifact. Idempotent: missing artifact is a no-op."""
        ...

    def list_artifacts(
        self, simulation_id: str, prefix: str = ""
    ) -> list[str]:
        """List logical artifact names currently stored, optionally filtered by prefix."""
        ...


# ---------------------------------------------------------------------------
# Local filesystem adapter
# ---------------------------------------------------------------------------


class LocalFilesystemArtifactStore:
    """Production adapter. Wraps ``json_io`` + ``ArtifactLocator`` for atomic JSON I/O."""

    def __init__(self, simulations_root: Optional[str] = None) -> None:
        self._root = simulations_root or ArtifactLocator.simulations_dir()

    def _abs_path(self, simulation_id: str, artifact: str) -> str:
        rel = _resolve_relative_path(artifact)
        return os.path.join(self._root, simulation_id, rel)

    def _ensure_simulation_dir(self, simulation_id: str) -> str:
        sim_dir = os.path.join(self._root, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir

    def read_json(
        self, simulation_id: str, artifact: str, default: Any = None
    ) -> Any:
        path = self._abs_path(simulation_id, artifact)
        return read_json_file(
            path, default=default, logger=logger, description=f"{simulation_id}/{artifact}"
        )

    def write_json(self, simulation_id: str, artifact: str, payload: Any) -> None:
        self._ensure_simulation_dir(simulation_id)
        path = self._abs_path(simulation_id, artifact)
        # ``write_json_atomic`` already creates parent dirs (e.g. ipc_commands/).
        write_json_atomic(path, payload)

    def exists(self, simulation_id: str, artifact: str) -> bool:
        return os.path.exists(self._abs_path(simulation_id, artifact))

    def delete(self, simulation_id: str, artifact: str) -> None:
        path = self._abs_path(simulation_id, artifact)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def list_artifacts(
        self, simulation_id: str, prefix: str = ""
    ) -> list[str]:
        sim_dir = os.path.join(self._root, simulation_id)
        if not os.path.isdir(sim_dir):
            return []
        results: list[str] = []
        # Top-level files (state, simulation_config, ...).
        with os.scandir(sim_dir) as entries:
            for entry in entries:
                if entry.is_file():
                    name = _reverse_lookup(entry.name)
                    if name is not None:
                        results.append(name)
        # IPC subdirectories.
        for sub in (_IPC_COMMAND_DIR, _IPC_RESPONSE_DIR):
            sub_path = os.path.join(sim_dir, sub)
            if not os.path.isdir(sub_path):
                continue
            with os.scandir(sub_path) as entries:
                for entry in entries:
                    if entry.is_file():
                        name = _reverse_lookup(f"{sub}/{entry.name}")
                        if name is not None:
                            results.append(name)
        if prefix:
            results = [n for n in results if n.startswith(prefix)]
        results.sort()
        return results


# ---------------------------------------------------------------------------
# In-memory adapter (tests)
# ---------------------------------------------------------------------------


class InMemoryArtifactStore:
    """Pure-Python adapter for tests. Deep-copies on read/write to avoid aliasing."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def _validate(self, artifact: str) -> None:
        # Reuse the same validation as the local adapter so tests catch bad names.
        _resolve_relative_path(artifact)

    def read_json(
        self, simulation_id: str, artifact: str, default: Any = None
    ) -> Any:
        self._validate(artifact)
        sim = self._data.get(simulation_id)
        if not sim or artifact not in sim:
            return default
        return copy.deepcopy(sim[artifact])

    def write_json(self, simulation_id: str, artifact: str, payload: Any) -> None:
        self._validate(artifact)
        self._data.setdefault(simulation_id, {})[artifact] = copy.deepcopy(payload)

    def exists(self, simulation_id: str, artifact: str) -> bool:
        self._validate(artifact)
        return artifact in self._data.get(simulation_id, {})

    def delete(self, simulation_id: str, artifact: str) -> None:
        self._validate(artifact)
        sim = self._data.get(simulation_id)
        if sim is not None:
            sim.pop(artifact, None)

    def list_artifacts(
        self, simulation_id: str, prefix: str = ""
    ) -> list[str]:
        names: Iterable[str] = self._data.get(simulation_id, {}).keys()
        if prefix:
            names = [n for n in names if n.startswith(prefix)]
        return sorted(names)


def resolve_default_store() -> SimulationArtifactStore:
    """Return the app-wide store, falling back to a local one outside Flask context.

    Services that may run inside the Flask request lifecycle *or* in a worker
    without an app context (e.g. ``SimulationRunner`` static methods, OASIS
    subprocess) can call this to obtain a usable store without forcing every
    caller to construct one explicitly.
    """
    try:
        from flask import current_app, has_app_context  # local import: keep module import-cheap

        if has_app_context():
            store = current_app.extensions.get("artifact_store")
            if store is not None:
                return store
    except Exception:  # noqa: BLE001 — Flask not available or extensions missing
        pass
    return LocalFilesystemArtifactStore()


__all__ = [
    "SimulationArtifactStore",
    "LocalFilesystemArtifactStore",
    "InMemoryArtifactStore",
    "resolve_default_store",
]
