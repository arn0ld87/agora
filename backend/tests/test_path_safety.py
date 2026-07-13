"""SEC-1: Workspace path-boundary validation.

RED-Tests für Path-Traversal über user-kontrollierte ``simulation_id``.
Repräsentative Alerts: CodeQL ``py/path-injection`` #9, #349–#353 in
``backend/app/services/artifact_store.py``. Die Pydantic-Verträge validieren
``simulation_id`` nur mit ``min_length=1``; ``os.path.join(root, simulation_id,
rel)`` lässt ``..``/absolute Pfade durch — der Sink ist über die API erreichbar.

Diese Suite fixiert das Verhalten: traversal-IDs müssen ``PathTraversalError``
werfen, normale IDs bleiben funktionsfähig.
"""

from __future__ import annotations

import os

import pytest

from app.services.artifact_store import LocalFilesystemArtifactStore
from app.utils.path_safety import (
    PathTraversalError,
    safe_join_within_root,
    validate_path_id,
)


# ---------------------------------------------------------------------------
# path_safety unit
# ---------------------------------------------------------------------------

VALID_IDS = ["sim_test_001", "sim_abcdef012345", "run_42", "rep_x-y_z"]


@pytest.mark.parametrize("value", VALID_IDS)
def test_validate_path_id_accepts_real_ids(value):
    assert validate_path_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "../etc",
        "..%2f",
        "/etc/passwd",
        "sim/../../etc",
        "sim\\..\\etc",
        "\x00sim",
        "sim.txt",
        "sim.id",
        " leading",
        "sim evil",
    ],
)
def test_validate_path_id_rejects_traversal(value):
    with pytest.raises(PathTraversalError):
        validate_path_id(value)


def test_validate_path_id_rejects_none_and_non_str():
    with pytest.raises(PathTraversalError):
        validate_path_id(None)  # type: ignore[arg-type]
    with pytest.raises(PathTraversalError):
        validate_path_id(123)  # type: ignore[arg-type]


def test_safe_join_within_root_accepts_subdir(tmp_path):
    root = str(tmp_path)
    p = safe_join_within_root(root, "sim_abc", "ipc_commands/cmd1.json")
    assert os.path.commonpath([os.path.realpath(root), p]) == os.path.realpath(root)


def test_safe_join_within_root_rejects_traversal(tmp_path):
    root = str(tmp_path)
    # realpath resolves ``..`` → target escapes root.
    with pytest.raises(PathTraversalError):
        safe_join_within_root(root, "..", "..", "etc", "passwd")


def test_safe_join_within_root_rejects_absolute_part(tmp_path):
    with pytest.raises(PathTraversalError):
        safe_join_within_root(str(tmp_path), "sim", "/etc/passwd")


def test_safe_join_within_root_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "sim_link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathTraversalError):
        safe_join_within_root(str(root), "sim_link", "state.json")


# ---------------------------------------------------------------------------
# ArtifactStore integration (production adapter)
# ---------------------------------------------------------------------------

@pytest.fixture
def fs_store(tmp_path) -> LocalFilesystemArtifactStore:
    return LocalFilesystemArtifactStore(simulations_root=str(tmp_path))


def test_artifact_store_rejects_traversal_sim_id(fs_store):
    # RED: currently no error — ``..`` escapes root.
    with pytest.raises(PathTraversalError):
        fs_store.read_json("../../../../etc", "state")


def test_artifact_store_rejects_absolute_sim_id(fs_store):
    with pytest.raises(PathTraversalError):
        fs_store.read_json("/etc/passwd", "state")


def test_artifact_store_rejects_dotdot_sim_id_write(fs_store):
    with pytest.raises(PathTraversalError):
        fs_store.write_json("..", "state", {"x": 1})


def test_artifact_store_rejects_traversal_delete(fs_store):
    with pytest.raises(PathTraversalError):
        fs_store.delete("../..", "state")


def test_artifact_store_rejects_traversal_list(fs_store):
    with pytest.raises(PathTraversalError):
        fs_store.list_artifacts("../..")


def test_artifact_store_normal_id_roundtrip(fs_store):
    # Positive case: real IDs stay fully functional (regression guard).
    fs_store.write_json("sim_test_001", "state", {"x": 1})
    assert fs_store.exists("sim_test_001", "state") is True
    assert fs_store.read_json("sim_test_001", "state") == {"x": 1}
    fs_store.delete("sim_test_001", "state")
    assert fs_store.exists("sim_test_001", "state") is False


def test_artifact_store_normal_id_ipc_subdir(fs_store):
    # IPC sub-directory path must still work (contains a ``/`` in the rel part).
    fs_store.write_json("sim_test_001", "ipc_command/cmd1", {"ping": 1})
    assert fs_store.read_json("sim_test_001", "ipc_command/cmd1") == {"ping": 1}
    assert "ipc_command/cmd1" in fs_store.list_artifacts("sim_test_001")