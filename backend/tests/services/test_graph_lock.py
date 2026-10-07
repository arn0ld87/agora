"""Abgeleitete Graph-Sperre (Issue #1808, ADR-0022 §6)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.simulation_record_contract import SimulationRecord
from app.services.graph_lock import (
    GraphLockedError,
    ensure_graph_unlocked,
    get_graph_lock_state,
)

GRAPH = "11111111-1111-4111-8111-111111111111"
OTHER_GRAPH = "22222222-2222-4222-8222-222222222222"


class _Repo:
    def __init__(self, *records: SimulationRecord) -> None:
        self._records = list(records)
        self.list_calls = 0

    def list(self, project_id=None):
        self.list_calls += 1
        return list(self._records)


def _sim(sim_id: str, *, project_id: str = "", graph_id: str = "", status: str = "completed"):
    return SimulationRecord(
        simulation_id=sim_id, project_id=project_id, graph_id=graph_id, status=status
    )


def _projects(*pairs: tuple[str, str | None]):
    return lambda: [SimpleNamespace(project_id=pid, graph_id=gid) for pid, gid in pairs]


def test_unlocked_without_simulations():
    state = get_graph_lock_state(GRAPH, repository=_Repo(), project_lister=_projects())
    assert state.locked is False
    assert state.used_by == []
    assert state.graph_id == GRAPH


def test_locked_by_simulation_with_same_graph_id():
    repo = _Repo(_sim("sim_aaaaaaaaaaaa", graph_id=GRAPH, status="running"))
    state = get_graph_lock_state(GRAPH, repository=repo, project_lister=_projects())
    assert state.locked is True
    assert [u.simulation_id for u in state.used_by] == ["sim_aaaaaaaaaaaa"]
    assert state.used_by[0].status == "running"


def test_locked_by_simulation_of_the_graphs_project_even_with_other_graph_id():
    """Das Projekt trägt den Graphen; die Simulation hängt am Projekt."""
    repo = _Repo(_sim("sim_bbbbbbbbbbbb", project_id="proj_0123456789ab", graph_id=OTHER_GRAPH))
    state = get_graph_lock_state(
        GRAPH, repository=repo, project_lister=_projects(("proj_0123456789ab", GRAPH))
    )
    assert state.locked is True
    assert state.used_by[0].project_id == "proj_0123456789ab"


def test_unrelated_simulation_does_not_lock():
    repo = _Repo(
        _sim("sim_cccccccccccc", project_id="proj_other0000000", graph_id=OTHER_GRAPH)
    )
    state = get_graph_lock_state(
        GRAPH, repository=repo, project_lister=_projects(("proj_0123456789ab", GRAPH))
    )
    assert state.locked is False


def test_explicit_project_ids_count_even_when_project_graph_id_was_reset():
    repo = _Repo(_sim("sim_dddddddddddd", project_id="proj_0123456789ab"))
    state = get_graph_lock_state(
        GRAPH,
        project_ids=["proj_0123456789ab"],
        repository=repo,
        project_lister=_projects(("proj_0123456789ab", None)),
    )
    assert state.locked is True


def test_project_without_graph_is_locked_by_its_simulations_only():
    repo = _Repo(
        _sim("sim_eeeeeeeeeeee", project_id="proj_0123456789ab"),
        _sim("sim_ffffffffffff", project_id="proj_other0000000"),
        # graph_id leer darf nie als „gleicher Graph“ zählen
        _sim("sim_000000000000", project_id="", graph_id=""),
    )
    state = get_graph_lock_state(
        "", project_ids=["proj_0123456789ab"], repository=repo, project_lister=_projects()
    )
    assert state.locked is True
    assert [u.simulation_id for u in state.used_by] == ["sim_eeeeeeeeeeee"]


def test_one_repository_scan_regardless_of_project_count():
    repo = _Repo(_sim("sim_aaaaaaaaaaaa", graph_id=OTHER_GRAPH))
    get_graph_lock_state(
        GRAPH,
        repository=repo,
        project_lister=_projects(*[(f"proj_{i:012x}", GRAPH) for i in range(25)]),
    )
    assert repo.list_calls == 1


def test_ensure_raises_with_state():
    repo = _Repo(_sim("sim_aaaaaaaaaaaa", graph_id=GRAPH))
    with pytest.raises(GraphLockedError) as excinfo:
        ensure_graph_unlocked(GRAPH, repository=repo, project_lister=_projects())
    assert excinfo.value.state.locked is True
    assert excinfo.value.state.used_by[0].simulation_id == "sim_aaaaaaaaaaaa"


def test_ensure_passes_when_free():
    ensure_graph_unlocked(GRAPH, repository=_Repo(), project_lister=_projects())


def test_repository_failure_is_not_swallowed():
    class _Broken:
        def list(self, project_id=None):
            raise OSError("state.json unlesbar")

    with pytest.raises(OSError):
        ensure_graph_unlocked(GRAPH, repository=_Broken(), project_lister=_projects())


def test_default_repository_sees_records_written_by_simulation_manager(
    tmp_path, monkeypatch
):
    """Regression (PR #1812, e2e „37186“): Der Default des Locks muss denselben
    Ablageort aufzaehlen, in den ``SimulationManager`` schreibt.

    ``get_simulation_repository()`` ohne ``simulations_dir`` zaehlt nur die
    instanzlokale Menge bekannter Kennungen — eine frische Instanz sieht
    niemanden, und die abgeleitete Sperre meldet still „frei“, obwohl eine
    Simulation den Graphen verwendet. Der e2e Golden-Gate-Smoke fiel genau
    darauf; Unit-Tests mit injizierten Fakes merken es nicht.
    """
    import os

    from app.config import Config
    from app.repositories.simulation_repository import get_simulation_repository
    from app.services.simulation_manager import SimulationManager

    sims_dir = str(tmp_path / "simulations")
    os.makedirs(sims_dir, exist_ok=True)
    # Write- und Read-Root auf dieselbe Stelle ziehen wie in Produktion
    # (``Config.UPLOAD_FOLDER/simulations`` ≡ ``SIMULATION_DATA_DIR``).
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", sims_dir)

    # Schreibpfad: exakt wie ``SimulationManager`` seine Ablage baut.
    write_repo = get_simulation_repository(simulations_dir=sims_dir)
    write_repo.save(_sim("sim_0123456789ab", graph_id=GRAPH))

    # Lesepfad: den Default nehmen, nichts injizieren.
    state = get_graph_lock_state(GRAPH, project_lister=_projects())

    assert state.locked is True
    assert [u.simulation_id for u in state.used_by] == ["sim_0123456789ab"]
