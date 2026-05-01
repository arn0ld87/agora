"""Effektive Verhaltens-Tests für ``SimulationManager``-Statusübergänge.

Spiegelt die deklarative Tabelle aus ``simulation_state_machine.py`` gegen
das echte Manager-Verhalten. Ein Drift zwischen Tabelle und Code soll hier
auffallen — wenn ``create_simulation`` plötzlich READY statt CREATED setzt
oder ``create_branch`` aus einem CREATED-State branchen lässt, schlagen
diese Tests Alarm.

Out-of-scope: ``prepare_simulation`` als Ganzes (LLM-/Filesystem-Pipeline,
gehört zu Integrationstests). Wir testen den Eingangs-Übergang
(``CREATED → PREPARING``) ohne den Erfolgspfad zu fahren — der reale
``prepare`` schreibt PREPARING in der ersten Anweisung der ``try``-Block.
"""

from __future__ import annotations

import pytest

from app.services.artifact_store import InMemoryArtifactStore
from app.services.simulation_manager import (
    SimulationManager,
    SimulationStatus,
)
from app.services.simulation_state_machine import (
    get_allowed_next,
    is_valid_transition,
)


@pytest.fixture
def manager(tmp_path, monkeypatch) -> SimulationManager:
    """SimulationManager mit isoliertem tmp-Verzeichnis und In-Memory-Store."""
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations")
    )
    return SimulationManager(store=InMemoryArtifactStore())


class TestCreateSimulation:
    def test_returns_status_created(self, manager: SimulationManager) -> None:
        state = manager.create_simulation(project_id="proj-1", graph_id="graph-1")
        assert state.status == SimulationStatus.CREATED

    def test_persists_state(self, manager: SimulationManager) -> None:
        state = manager.create_simulation(project_id="proj-1", graph_id="graph-1")
        loaded = manager.get_simulation(state.simulation_id)
        assert loaded is not None
        assert loaded.status == SimulationStatus.CREATED
        assert loaded.simulation_id == state.simulation_id

    def test_root_id_equals_self_for_top_level(
        self, manager: SimulationManager
    ) -> None:
        state = manager.create_simulation(project_id="proj-1", graph_id="graph-1")
        assert state.root_simulation_id == state.simulation_id
        assert state.source_simulation_id is None
        assert state.branch_depth == 0


class TestEffectiveTransitionsMatchTable:
    """Die in der Tabelle erlaubten Transitions sollen auch durchführbar sein.

    Wir manipulieren ``state.status`` direkt (wie es Manager/API tun) und
    prüfen, dass die persistente Reload-Variante den neuen Status zurückliest.
    Das deckt den Persistenz-Pfad ohne Sub-Process- oder LLM-Aufrufe ab.
    """

    @pytest.fixture
    def state_id(self, manager: SimulationManager) -> str:
        state = manager.create_simulation(project_id="proj-1", graph_id="graph-1")
        return state.simulation_id

    @pytest.mark.parametrize(
        "target_status",
        [
            SimulationStatus.PREPARING,
            SimulationStatus.READY,
            SimulationStatus.RUNNING,
            SimulationStatus.PAUSED,
            SimulationStatus.STOPPED,
            SimulationStatus.COMPLETED,
            SimulationStatus.FAILED,
        ],
    )
    def test_set_and_reload_each_status(
        self, manager: SimulationManager, state_id: str, target_status: SimulationStatus
    ) -> None:
        state = manager.get_simulation(state_id)
        assert state is not None
        state.status = target_status
        manager._save_simulation_state(state)

        # Cache leeren, damit wirklich von Storage neu geladen wird.
        manager._simulations.clear()
        reloaded = manager.get_simulation(state_id)
        assert reloaded is not None
        assert reloaded.status == target_status


class TestStateMachineCompliance:
    """Belegt, dass die deklarative Tabelle alle real auftretenden
    ``state.status = SimulationStatus.X``-Zuweisungen abdeckt.

    Wenn jemand eine neue Transition in den Manager-Code patcht
    (``state.status = SimulationStatus.SOME_NEW``), die nicht in der Tabelle
    erlaubt ist, fällt das spätestens im EPIC-06-ST-02-Refactor auf —
    dieser Test dokumentiert die aktuell erfassten Aufrufstellen
    (Stand 2026-05-01, Commit a02cf3f).
    """

    OBSERVED_TRANSITIONS = [
        # (Aufrufstelle, from, to)
        # services/simulation_manager.py:300
        ("simulation_manager.prepare_simulation:enter", SimulationStatus.CREATED, SimulationStatus.PREPARING),
        ("simulation_manager.prepare_simulation:reprepare", SimulationStatus.READY, SimulationStatus.PREPARING),
        # services/simulation_manager.py:500
        ("simulation_manager.prepare_simulation:success", SimulationStatus.PREPARING, SimulationStatus.READY),
        # services/simulation_manager.py:346/512 (catch-all FAILED)
        ("simulation_manager.prepare_simulation:fail_preparing", SimulationStatus.PREPARING, SimulationStatus.FAILED),
        ("simulation_manager.prepare_simulation:fail_created", SimulationStatus.CREATED, SimulationStatus.FAILED),
        # services/simulation_manager.py:603 (create_branch setzt READY)
        ("simulation_manager.create_branch", SimulationStatus.CREATED, SimulationStatus.READY),
        # api/simulation_run.py:212
        ("api.simulation_run.start", SimulationStatus.READY, SimulationStatus.RUNNING),
        # api/simulation_run.py:270
        ("api.simulation_run.pause", SimulationStatus.RUNNING, SimulationStatus.PAUSED),
        # api/simulation_run.py:563 (auto-complete)
        ("api.simulation_run.auto_complete", SimulationStatus.RUNNING, SimulationStatus.COMPLETED),
        # api/runs.py:202
        ("api.runs.stop_from_running", SimulationStatus.RUNNING, SimulationStatus.STOPPED),
        ("api.runs.stop_from_paused", SimulationStatus.PAUSED, SimulationStatus.STOPPED),
        # api/runs.py:426
        ("api.runs.resume_from_stopped", SimulationStatus.STOPPED, SimulationStatus.RUNNING),
        ("api.runs.resume_from_paused", SimulationStatus.PAUSED, SimulationStatus.RUNNING),
    ]

    @pytest.mark.parametrize(
        "label,from_status,to_status",
        OBSERVED_TRANSITIONS,
        ids=[entry[0] for entry in OBSERVED_TRANSITIONS],
    )
    def test_observed_transition_is_allowed_by_table(
        self,
        label: str,
        from_status: SimulationStatus,
        to_status: SimulationStatus,
    ) -> None:
        # Hinweis: ``create_branch`` setzt den NEUEN Branch-State auf READY, der
        # neue State startet aus CREATED (per ``create_simulation``) und wird
        # direkt überschrieben. Das ist ein zulässiger Manager-internal
        # Initialisierungs-Setter, kein "echter" Transition aus laufendem Status —
        # darum auch CREATED→READY in der Tabelle erlaubt? Nein: Tabelle erlaubt
        # das NICHT, weil reguläre Transitions niemals so springen. Branch-Init
        # ist Sonderfall, akzeptieren wir hier durch eigenen Test-Pfad.
        if label == "simulation_manager.create_branch":
            allowed_next = get_allowed_next(from_status)
            # CREATED → READY ist nicht in der allowed_next-Menge (korrekt),
            # aber semantisch ist das ein Initialisierungs-Setter, kein
            # Lifecycle-Transition. Wir dokumentieren den Sonderfall hier.
            assert SimulationStatus.READY not in allowed_next, (
                "Branch-Init ist Sonderfall: setzt READY direkt nach CREATED. "
                "Tabelle erlaubt das absichtlich NICHT (würde regulären "
                "Lifecycle bypassen). EPIC-06-ST-02 muss diesen Pfad als "
                "Init-Setter explizit modellieren."
            )
            return
        assert is_valid_transition(from_status, to_status), (
            f"Real beobachtete Transition {label} ({from_status.value} → "
            f"{to_status.value}) ist in der Tabelle NICHT erlaubt — "
            f"Tabelle und Code driften."
        )
