"""Eine blockierende Degradierung darf ``READY`` nicht erreichen (Issue #1419).

Der Vertrag in ``pipeline_degradation_contract`` sagt es woertlich:
``BLOCKING`` heisst, dass der Schritt den Zustand "bereit" nicht erreichen
darf, auch wenn technisch kein Fehler aufgetreten ist. Bis hierher war das
eine Absichtserklaerung — ``prepare_simulation`` setzte ``READY``
unbedingt, und eine Vorbereitung, in der keine einzige Persona vom Modell
kam, war regulaer startbar.

Isolationsstrategie wie ``test_prepare_cancel.py``: die drei Prepare-Phasen
sind gemockt, ``_set_status`` validiert gegen die echte FSM-Tabelle. Geprueft
wird ausschliesslich, ob der Orchestrator die Konsequenz zieht.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from app.services import prepare_service
from app.services.degradation_collector import DegradationCollector
from app.services.prepare_service import prepare_simulation
from app.services.simulation_manager import SimulationStatus
from app.services.simulation_state_machine import assert_valid_transition
from app.services.sim.cancel_flag import clear_cancel


def _unique_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _make_state(simulation_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        simulation_id=simulation_id,
        project_id="proj-1",
        graph_id="graph-1",
        status=SimulationStatus.CREATED,
        entities_count=0,
        profiles_count=0,
        persona_floor=None,
        error=None,
    )


class _FakeManager:
    """Minimaler Manager-Stub mit echter FSM-Validierung."""

    def __init__(self, state: SimpleNamespace) -> None:
        self.state = state
        self.status_history: list[SimulationStatus] = [state.status]
        self.saved_states: list[SimpleNamespace] = []

    def _load_simulation_state(self, simulation_id: str) -> SimpleNamespace:
        assert simulation_id == self.state.simulation_id
        return self.state

    def _set_status(self, state: SimpleNamespace, new_status: SimulationStatus) -> None:
        assert_valid_transition(state.status, new_status)
        state.status = new_status
        self.status_history.append(new_status)

    def _get_simulation_dir(self, simulation_id: str) -> str:
        return f"/tmp/sim/{simulation_id}"

    def _save_simulation_state(self, state: SimpleNamespace) -> None:
        self.saved_states.append(state)


@pytest.fixture()
def run_id():
    rid = _unique_run_id()
    clear_cancel(rid)
    yield rid
    clear_cancel(rid)


@pytest.fixture(autouse=True)
def _patch_phases(monkeypatch):
    """Die drei Phasen sind andernorts getestet — hier zaehlt der Orchestrator."""

    def _phase1(*args, **kwargs):
        return SimpleNamespace(filtered_count=1, entity_types={"Person"})

    def _phase2(*args, **kwargs):
        return [], []

    def _phase3(*args, **kwargs):
        return None

    monkeypatch.setattr(prepare_service, "_phase_read_entities", _phase1)
    monkeypatch.setattr(prepare_service, "_phase_generate_profiles", _phase2)
    monkeypatch.setattr(prepare_service, "_phase_generate_config", _phase3)
    monkeypatch.setattr(
        prepare_service,
        "_get_settings",
        lambda: SimpleNamespace(effective_value=lambda k: "10"),
    )


def _run(manager, run_id, degradations=None):
    return prepare_simulation(
        manager,
        manager.state.simulation_id,
        "Requirement text",
        "document text",
        storage=MagicMock(),
        run_id=run_id,
        degradations=degradations,
    )


def _collector(severity: DegradationSeverity) -> DegradationCollector:
    collector = DegradationCollector()
    collector.record(
        kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
        severity=severity,
        detail="20 von 20 Personas sind regelbasierte Platzhalter.",
        context={"fallback_personas": 20, "total_personas": 20},
    )
    return collector


def test_a_blocking_degradation_never_reaches_ready(run_id):
    """Der beobachtete Fall aus #1419: 20 von 20 Personas sind Platzhalter."""
    manager = _FakeManager(_make_state("sim_blocking"))

    state = _run(manager, run_id, _collector(DegradationSeverity.BLOCKING))

    assert state.status == SimulationStatus.FAILED
    assert SimulationStatus.READY not in manager.status_history


def test_a_blocking_degradation_names_its_cause(run_id):
    """Ein Status ohne Begruendung ist so stumm wie das Log vorher."""
    manager = _FakeManager(_make_state("sim_blocking_reason"))

    state = _run(manager, run_id, _collector(DegradationSeverity.BLOCKING))

    assert state.error
    assert "Platzhalter" in state.error


def test_a_warning_degradation_still_becomes_ready(run_id):
    """Eine Teilquote bleibt startbar — sonst waere jede Warnung ein Abbruch."""
    manager = _FakeManager(_make_state("sim_warning"))

    state = _run(manager, run_id, _collector(DegradationSeverity.WARNING))

    assert state.status == SimulationStatus.READY
    assert state.error is None


def test_a_clean_run_becomes_ready(run_id):
    """Baseline: ein leerer Collector aendert nichts am bisherigen Ablauf."""
    manager = _FakeManager(_make_state("sim_clean"))

    state = _run(manager, run_id, DegradationCollector())

    assert state.status == SimulationStatus.READY


def test_without_a_collector_the_orchestrator_is_unchanged(run_id):
    """``degradations=None`` ist der Bestandsaufruf und darf nicht brechen."""
    manager = _FakeManager(_make_state("sim_no_collector"))

    state = _run(manager, run_id, None)

    assert state.status == SimulationStatus.READY
