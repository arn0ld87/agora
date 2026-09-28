"""Regressionstests für CodeQL-Triage Slice C (#1669): Path-Injection-Guards.

Deckt alle in Slice C mit ``validate_path_id`` gehärteten Call-Sites ab:
``branching_service.create_branch``, ``event_bus._simulation_abs_dir``,
``action_log_reader.get_all_actions``, sechs Funktionen in
``interview_client``, zwei in ``interview_direct``,
``SimulationManager._get_simulation_dir`` und
``SimulationRunner.get_console_log``.

Jede Funktion muss ``PathTraversalError`` werfen, bevor sie das Dateisystem
berührt (bewiesen durch geblockte ``os.path.exists``/``os.path.isdir``/
``os.makedirs``-Aufrufe), und eine reale ID (``sim_abcdef012345``) muss den
Guard passieren — nachgelagerte Fehler (fehlende Verzeichnisse, fehlender
Manager-State) sind hier irrelevant, geprüft wird ausschließlich der Guard.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app.services import branching_service, event_bus, simulation_manager, simulation_runner
from app.services.sim import action_log_reader, interview_client, interview_direct
from app.utils.path_safety import PathTraversalError

MALICIOUS_IDS = ["../x", "a/b", ".."]
VALID_ID = "sim_abcdef012345"


def _block_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lässt jeden ``os.path.exists``/``os.path.isdir``/``os.makedirs``-Aufruf
    hart fehlschlagen — Beweis, dass der Guard VOR jeder Dateisystem-Berührung
    greift. Stünde der Guard fehlerhaft nach dem I/O, schlüge der Test mit
    ``AssertionError`` statt ``PathTraversalError`` fehl."""

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("I/O reached before path guard fired")

    monkeypatch.setattr(os.path, "exists", _boom)
    monkeypatch.setattr(os.path, "isdir", _boom)
    monkeypatch.setattr(os, "makedirs", _boom)


CASES: list[tuple[str, Callable[[str], Any]]] = [
    (
        "branching_service.create_branch",
        lambda sim_id: branching_service.create_branch(object(), sim_id, "branch"),
    ),
    (
        "event_bus._simulation_abs_dir",
        lambda sim_id: event_bus._simulation_abs_dir(sim_id),
    ),
    (
        "action_log_reader.get_all_actions",
        lambda sim_id: action_log_reader.get_all_actions(sim_id, "/tmp/unused-1669c"),
    ),
    (
        "interview_client.check_env_alive",
        lambda sim_id: interview_client.check_env_alive(
            sim_id, run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_client.interview_agent",
        lambda sim_id: interview_client.interview_agent(
            sim_id, 0, "prompt", run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_client.interview_agents_batch",
        lambda sim_id: interview_client.interview_agents_batch(
            sim_id, [], run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_client.interview_all_agents",
        lambda sim_id: interview_client.interview_all_agents(
            sim_id, "prompt", run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_client.close_simulation_env",
        lambda sim_id: interview_client.close_simulation_env(
            sim_id, run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_client.get_interview_history",
        lambda sim_id: interview_client.get_interview_history(
            sim_id, run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_direct._load_personas",
        lambda sim_id: interview_direct._load_personas(
            sim_id, "twitter", run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "interview_direct.interview_agents_batch_direct",
        lambda sim_id: interview_direct.interview_agents_batch_direct(
            sim_id, [], run_state_dir="/tmp/unused-1669c"
        ),
    ),
    (
        "simulation_manager._get_simulation_dir",
        lambda sim_id: simulation_manager.SimulationManager._get_simulation_dir(
            SimpleNamespace(), sim_id
        ),
    ),
    (
        "simulation_runner.get_console_log",
        lambda sim_id: simulation_runner.SimulationRunner.get_console_log(sim_id),
    ),
]


@pytest.mark.parametrize("bad_id", MALICIOUS_IDS)
@pytest.mark.parametrize("label, invoke", CASES, ids=[c[0] for c in CASES])
def test_guard_rejects_traversal_before_io(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    invoke: Callable[[str], Any],
    bad_id: str,
) -> None:
    _block_io(monkeypatch)
    with pytest.raises(PathTraversalError):
        invoke(bad_id)


@pytest.mark.parametrize("label, invoke", CASES, ids=[c[0] for c in CASES])
def test_guard_passes_valid_simulation_id(label: str, invoke: Callable[[str], Any]) -> None:
    try:
        invoke(VALID_ID)
    except PathTraversalError:
        pytest.fail(f"{label}: valid simulation_id must pass the path guard")
    except Exception:
        # Nachgelagerte Fehler (fehlende Verzeichnisse, kein IPC, fehlender
        # Manager-State) sind hier irrelevant — geprüft wird nur der Guard.
        pass
