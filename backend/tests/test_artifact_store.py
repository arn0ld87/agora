"""Contract tests for SimulationArtifactStore adapters (Issue #13)."""

from __future__ import annotations

import json
import os
import threading
from typing import Callable
from unittest.mock import patch

import pytest

from app.services.artifact_store import (
    InMemoryArtifactStore,
    LocalFilesystemArtifactStore,
    SimulationArtifactStore,
)


# ---------------------------------------------------------------------------
# Adapter factories — parametrized over both implementations.
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=["local", "memory"],
    ids=["LocalFilesystemArtifactStore", "InMemoryArtifactStore"],
)
def store_factory(request, tmp_path) -> Callable[[], SimulationArtifactStore]:
    if request.param == "local":
        return lambda: LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    return lambda: InMemoryArtifactStore()


@pytest.fixture
def store(store_factory) -> SimulationArtifactStore:
    return store_factory()


SIM_ID = "sim_test_001"


# ---------------------------------------------------------------------------
# Contract: read missing → default
# ---------------------------------------------------------------------------


def test_read_missing_returns_default(store):
    assert store.read_json(SIM_ID, "state") is None
    assert store.read_json(SIM_ID, "state", default={"x": 1}) == {"x": 1}


def test_exists_false_for_missing(store):
    assert store.exists(SIM_ID, "state") is False


# ---------------------------------------------------------------------------
# Contract: roundtrip
# ---------------------------------------------------------------------------


def test_write_then_read_roundtrip(store):
    payload = {"current_round": 7, "agents": [1, 2, 3], "meta": {"k": "v"}}
    store.write_json(SIM_ID, "run_state", payload)
    assert store.exists(SIM_ID, "run_state") is True
    assert store.read_json(SIM_ID, "run_state") == payload


def test_write_overwrites(store):
    store.write_json(SIM_ID, "state", {"v": 1})
    store.write_json(SIM_ID, "state", {"v": 2})
    assert store.read_json(SIM_ID, "state") == {"v": 2}


def test_isolation_between_simulations(store):
    store.write_json("sim_a", "state", {"id": "a"})
    store.write_json("sim_b", "state", {"id": "b"})
    assert store.read_json("sim_a", "state") == {"id": "a"}
    assert store.read_json("sim_b", "state") == {"id": "b"}


# ---------------------------------------------------------------------------
# Contract: delete is idempotent
# ---------------------------------------------------------------------------


def test_delete_existing(store):
    store.write_json(SIM_ID, "state", {"v": 1})
    store.delete(SIM_ID, "state")
    assert store.exists(SIM_ID, "state") is False


def test_delete_missing_is_noop(store):
    # Must not raise.
    store.delete(SIM_ID, "state")
    store.delete("never_existed", "run_state")


# ---------------------------------------------------------------------------
# Contract: list_artifacts
# ---------------------------------------------------------------------------


def test_list_empty_for_unknown_sim(store):
    assert store.list_artifacts("nope") == []


def test_list_returns_written_artifacts(store):
    store.write_json(SIM_ID, "state", {"a": 1})
    store.write_json(SIM_ID, "control_state", {"paused": False})
    store.write_json(SIM_ID, "run_state", {"round": 0})
    listed = store.list_artifacts(SIM_ID)
    assert set(listed) >= {"state", "control_state", "run_state"}


def test_list_filters_by_prefix(store):
    store.write_json(SIM_ID, "ipc_command/abc-1", {"type": "interview"})
    store.write_json(SIM_ID, "ipc_command/abc-2", {"type": "interview"})
    store.write_json(SIM_ID, "ipc_response/abc-1", {"status": "completed"})
    store.write_json(SIM_ID, "state", {"v": 1})

    cmds = store.list_artifacts(SIM_ID, prefix="ipc_command/")
    assert sorted(cmds) == ["ipc_command/abc-1", "ipc_command/abc-2"]

    resps = store.list_artifacts(SIM_ID, prefix="ipc_response/")
    assert sorted(resps) == ["ipc_response/abc-1"]


# ---------------------------------------------------------------------------
# Contract: invalid artifact names are rejected
# ---------------------------------------------------------------------------


def test_unknown_artifact_raises(store):
    with pytest.raises(KeyError):
        store.write_json(SIM_ID, "totally_made_up", {})


def test_ipc_subpath_validation(store):
    with pytest.raises(ValueError):
        store.write_json(SIM_ID, "ipc_command/", {})
    with pytest.raises(ValueError):
        store.write_json(SIM_ID, "ipc_command/with/slash", {})


# ---------------------------------------------------------------------------
# In-memory adapter: deep-copy semantics (no aliasing).
# ---------------------------------------------------------------------------


def test_in_memory_does_not_alias():
    store = InMemoryArtifactStore()
    payload = {"agents": [1, 2, 3]}
    store.write_json(SIM_ID, "state", payload)
    payload["agents"].append(99)  # Mutate after write — must not affect store.
    stored = store.read_json(SIM_ID, "state")
    assert stored == {"agents": [1, 2, 3]}
    stored["agents"].append(42)  # Mutate read result — must not affect store.
    assert store.read_json(SIM_ID, "state") == {"agents": [1, 2, 3]}


# ---------------------------------------------------------------------------
# LocalFilesystemArtifactStore-specific: atomicity + tmp cleanup.
# ---------------------------------------------------------------------------


def test_local_write_lands_on_correct_path(tmp_path):
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    store.write_json(SIM_ID, "state", {"v": 1})
    expected = tmp_path / SIM_ID / "state.json"
    assert expected.exists()
    assert json.loads(expected.read_text()) == {"v": 1}


def test_local_ipc_command_lands_in_subdir(tmp_path):
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    store.write_json(SIM_ID, "ipc_command/cmd-42", {"type": "ping"})
    expected = tmp_path / SIM_ID / "ipc_commands" / "cmd-42.json"
    assert expected.exists()


def test_local_write_failure_cleans_tmp(tmp_path):
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    sim_dir = tmp_path / SIM_ID
    sim_dir.mkdir(parents=True)
    # Force os.replace to fail mid-write; the tmp file must not leak.
    with patch("app.utils.json_io.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.write_json(SIM_ID, "state", {"v": 1})
    leftovers = [p.name for p in sim_dir.iterdir() if p.name.startswith(".tmp-json-")]
    assert leftovers == []


def test_local_concurrent_writers_no_partial_reads(tmp_path):
    """Stress the atomicity contract: a reader spinning during writes must
    only ever see fully-formed JSON, never a partial file."""
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    store.write_json(SIM_ID, "state", {"v": 0})

    stop = threading.Event()
    errors: list[Exception] = []

    def writer():
        i = 0
        while not stop.is_set():
            store.write_json(SIM_ID, "state", {"v": i, "filler": "x" * 4096})
            i += 1

    def reader():
        path = tmp_path / SIM_ID / "state.json"
        try:
            for _ in range(2000):
                if path.exists():
                    # Direct json.loads to catch any partial file the writer
                    # might have exposed. Atomic writes => never raises.
                    json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(exc)

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)
    t_writer.start()
    t_reader.start()
    t_reader.join(timeout=5)
    stop.set()
    t_writer.join(timeout=5)

    assert not errors, f"Reader saw a partial JSON file: {errors[0]}"


def test_local_default_root_uses_artifact_locator():
    store = LocalFilesystemArtifactStore()
    # Just sanity: root should be a non-empty path under the configured uploads dir.
    assert store._root  # noqa: SLF001 — internal state OK in test
    assert os.path.basename(store._root) == "simulations"
