"""Tests für kooperativen Abbruch von ``simulation_prepare`` (Plan B2).

Isolationsstrategie wie ``test_persona_quota_wiring.py``: die drei
Prepare-Phasen (``_phase_read_entities``/``_phase_generate_profiles``/
``_phase_generate_config``) sind eigene, bereits andernorts getestete
Funktionen (LLM- und Graph-lastig) — hier zählt nur, ob der Orchestrator
``prepare_service.prepare_simulation`` das Cancel-Flag korrekt an den drei
Phasengrenzen prüft und den FSM richtig umbiegt. Die Phasenfunktionen werden
deshalb gemockt, nicht real ausgeführt.

Abgedeckte Szenarien:
  1  Cancel vor Phase 1 → PrepareCancelledError, Status CANCELLED_PARTIAL,
     Phase 1 wird NIE aufgerufen
  2  Cancel vor Phase 2 → Phase 1 lief, Phase 2 NIE, Status CANCELLED_PARTIAL
  3  Cancel vor Phase 3 → Phase 1+2 liefen, Phase 3 NIE, Status CANCELLED_PARTIAL
  4  Kein Cancel → alle drei Phasen laufen durch, Status READY (Baseline)
  5  FSM: PREPARING -> CANCELLED_PARTIAL ist erlaubt, CANCELLED_PARTIAL ->
     PREPARING (Retry) ebenfalls, CANCELLED_PARTIAL -> READY NICHT
  6  API-Ebene (``_make_prepare_job.run_prepare``): ``PrepareCancelledError``
     endet als RunRegistry status="stopped" + termination_reason="user_cancel";
     bereits generierte Profildatei bleibt unangetastet (kein Löschen/Rollback)
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import prepare_service
from app.services.prepare_service import PrepareCancelledError, prepare_simulation
from app.services.simulation_manager import SimulationStatus
from app.services.simulation_state_machine import (
    InvalidStatusTransition,
    assert_valid_transition,
)
from app.contracts import PersonaQuotaPlan
from app.services.sim.cancel_flag import clear_cancel, request_cancel


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
    """Minimaler Manager-Stub: nur die vier Methoden, die der Orchestrator ruft.

    ``_set_status`` validiert über die echte FSM-Tabelle
    (``simulation_state_machine.assert_valid_transition``) — ein Test, der
    einen verbotenen Übergang triggert, schlägt hier fehl statt still zu
    bestehen.
    """

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
    """Ersetzt die drei Phasenfunktionen durch call-tracking Stubs.

    Phase 1 liefert ein ``filtered_count=1``-Objekt (sonst bricht der
    Orchestrator vor jedem Cancel-Check mit ``ValueError`` ab). Phase 2
    liefert ein leeres Profiles-Tupel.
    """
    calls: list[str] = []

    def _phase1(*args, **kwargs):
        calls.append("phase1")
        return SimpleNamespace(filtered_count=1, entity_types={"Person"})

    def _phase2(*args, **kwargs):
        calls.append("phase2")
        return [], []

    def _phase3(*args, **kwargs):
        calls.append("phase3")
        return None

    monkeypatch.setattr(prepare_service, "_phase_read_entities", _phase1)
    monkeypatch.setattr(prepare_service, "_phase_generate_profiles", _phase2)
    monkeypatch.setattr(prepare_service, "_phase_generate_config", _phase3)
    # AGORA_PARALLEL_PERSONA_COUNT-Auflösung ist irrelevant für diesen Test —
    # real ausgeführt würde sie Settings-Layer-IO anstoßen.
    monkeypatch.setattr(
        prepare_service, "_get_settings", lambda: SimpleNamespace(effective_value=lambda k: "10")
    )
    return calls


def _run(manager, run_id, calls_ref):
    return prepare_simulation(
        manager,
        manager.state.simulation_id,
        "Requirement text",
        "document text",
        storage=MagicMock(),
        run_id=run_id,
    )


# ---------------------------------------------------------------------------
# Szenario 1: Cancel vor Phase 1
# ---------------------------------------------------------------------------


def test_cancel_before_phase1_stoppt_vor_jeder_phase(run_id, _patch_phases):
    simulation_id = "sim_cancel_1"
    manager = _FakeManager(_make_state(simulation_id))
    request_cancel(run_id)

    with pytest.raises(PrepareCancelledError) as excinfo:
        _run(manager, run_id, _patch_phases)

    assert _patch_phases == [], "Keine Phase darf nach einem frühen Cancel laufen"
    assert manager.state.status == SimulationStatus.CANCELLED_PARTIAL
    assert excinfo.value.state is manager.state


# ---------------------------------------------------------------------------
# Szenario 2: Cancel vor Phase 2
# ---------------------------------------------------------------------------


def test_cancel_before_phase2_laesst_phase1_laufen(run_id, _patch_phases, monkeypatch):
    simulation_id = "sim_cancel_2"
    manager = _FakeManager(_make_state(simulation_id))

    # Cancel erst NACH Phase 1 anfordern: wir hängen uns an den echten
    # Phase-1-Stub und setzen das Flag als Seiteneffekt.
    original_phase1 = prepare_service._phase_read_entities

    def _phase1_then_cancel(*args, **kwargs):
        result = original_phase1(*args, **kwargs)
        request_cancel(run_id)
        return result

    monkeypatch.setattr(prepare_service, "_phase_read_entities", _phase1_then_cancel)

    with pytest.raises(PrepareCancelledError):
        _run(manager, run_id, _patch_phases)

    assert _patch_phases == ["phase1"], "Nur Phase 1 darf gelaufen sein"
    assert manager.state.status == SimulationStatus.CANCELLED_PARTIAL


# ---------------------------------------------------------------------------
# Szenario 3: Cancel vor Phase 3
# ---------------------------------------------------------------------------


def test_cancel_before_phase3_laesst_phase1_und_2_laufen(run_id, _patch_phases, monkeypatch):
    simulation_id = "sim_cancel_3"
    manager = _FakeManager(_make_state(simulation_id))

    original_phase2 = prepare_service._phase_generate_profiles

    def _phase2_then_cancel(*args, **kwargs):
        result = original_phase2(*args, **kwargs)
        request_cancel(run_id)
        return result

    monkeypatch.setattr(prepare_service, "_phase_generate_profiles", _phase2_then_cancel)

    with pytest.raises(PrepareCancelledError):
        _run(manager, run_id, _patch_phases)

    assert _patch_phases == ["phase1", "phase2"], "Phase 3 darf nicht mehr laufen"
    assert manager.state.status == SimulationStatus.CANCELLED_PARTIAL


# ---------------------------------------------------------------------------
# Szenario 3b (Review-Finding PR #1371, Befund 2): Cancel mitten in der
# Persona-Generierung MIT gesetztem quota_plan darf nicht als FAILED enden.
#
# Vorher lief ``_validate_persona_quota`` (tolerance=0, exakter Soll/Ist-
# Abgleich) VOR dem Cancel-Check nach Phase 2. Eine durch den Abbruch
# gekürzte Profilliste erfüllt die Quota fast nie — die Validierung warf
# eine pydantic ValidationError, die im generischen ``except Exception``
# landete und den FSM auf FAILED setzte statt auf CANCELLED_PARTIAL. Genau
# der Fall, für den das Feature existiert, wurde so zum harten Fehler.
# ---------------------------------------------------------------------------


def test_cancel_mid_persona_generation_mit_quota_plan_bleibt_cancelled_nicht_failed(
    run_id, _patch_phases, monkeypatch
):
    simulation_id = "sim_cancel_quota"
    manager = _FakeManager(_make_state(simulation_id))

    # Plan verlangt 5 Personas im Segment "Person" — die gekürzte
    # Rückgabe unten (2 Profile) würde die Quota-Validierung mit
    # tolerance=0 zwangsläufig scheitern lassen, liefe sie noch.
    quota_plan = PersonaQuotaPlan(targets={"Person": 5}, total=5)

    def _phase2_partial_then_cancel(*args, **kwargs):
        request_cancel(run_id)
        # Abbruch mitten in der as_completed-Schleife: gekürzte Liste,
        # keine Exception — spiegelt oasis_profile_generator.py.
        partial_profiles = [
            SimpleNamespace(segment="Person"),
            SimpleNamespace(segment="Person"),
        ]
        return partial_profiles, []

    monkeypatch.setattr(
        prepare_service, "_phase_generate_profiles", _phase2_partial_then_cancel
    )

    with pytest.raises(PrepareCancelledError):
        prepare_simulation(
            manager,
            simulation_id,
            "Requirement text",
            "document text",
            storage=MagicMock(),
            run_id=run_id,
            quota_plan=quota_plan,
        )

    assert manager.state.status == SimulationStatus.CANCELLED_PARTIAL, (
        "Ein Cancel mit gesetztem quota_plan darf nicht als FAILED enden — "
        f"tatsächlicher Status: {manager.state.status}"
    )


# ---------------------------------------------------------------------------
# Szenario 4: Baseline — kein Cancel
# ---------------------------------------------------------------------------


def test_kein_cancel_laeuft_normal_durch(run_id, _patch_phases):
    simulation_id = "sim_no_cancel"
    manager = _FakeManager(_make_state(simulation_id))

    result = _run(manager, run_id, _patch_phases)

    assert _patch_phases == ["phase1", "phase2", "phase3"]
    assert result.status == SimulationStatus.READY
    assert manager.state.status == SimulationStatus.READY


def test_kein_run_id_ignoriert_cancel_flag_auch_wenn_irgendwo_gesetzt(_patch_phases):
    """Ohne ``run_id`` kann der Orchestrator gar nicht prüfen — muss durchlaufen."""
    simulation_id = "sim_no_run_id"
    manager = _FakeManager(_make_state(simulation_id))

    result = prepare_simulation(
        manager,
        simulation_id,
        "Requirement text",
        "document text",
        storage=MagicMock(),
        run_id=None,
    )

    assert _patch_phases == ["phase1", "phase2", "phase3"]
    assert result.status == SimulationStatus.READY


# ---------------------------------------------------------------------------
# Szenario 5: FSM-Übergänge
# ---------------------------------------------------------------------------


def test_fsm_erlaubt_preparing_zu_cancelled_partial():
    assert_valid_transition(SimulationStatus.PREPARING, SimulationStatus.CANCELLED_PARTIAL)


def test_fsm_erlaubt_retry_aus_cancelled_partial():
    assert_valid_transition(SimulationStatus.CANCELLED_PARTIAL, SimulationStatus.PREPARING)


def test_fsm_verbietet_cancelled_partial_direkt_zu_ready():
    with pytest.raises(InvalidStatusTransition):
        assert_valid_transition(SimulationStatus.CANCELLED_PARTIAL, SimulationStatus.READY)


def test_fsm_erlaubt_weiterhin_cancelled_partial_zu_completed():
    """Bestehender simulation_run-Pfad darf durch die B2-Änderung nicht brechen."""
    assert_valid_transition(SimulationStatus.CANCELLED_PARTIAL, SimulationStatus.COMPLETED)


# ---------------------------------------------------------------------------
# Szenario 6: API-Ebene — RunRegistry-Endzustand
# ---------------------------------------------------------------------------


def test_run_prepare_cancel_branch_setzt_stopped_und_user_cancel(monkeypatch, tmp_path):
    """``_make_prepare_job.run_prepare`` fängt ``PrepareCancelledError`` ab und
    beendet den Run als ``stopped`` + ``termination_reason=user_cancel`` —
    dieselbe Reihenfolge (``complete_task`` vor dem Run-Update) wie
    ``report_generation.py``.
    """
    from app.api import simulation_prepare as api_mod
    from app.services.degradation_collector import DegradationCollector

    run_id = _unique_run_id()
    clear_cancel(run_id)

    # Realtime-Profildatei simulieren: Teilergebnis, das erhalten bleiben muss.
    sim_dir = tmp_path / "sim_cancel_api"
    sim_dir.mkdir()
    profile_file = sim_dir / "reddit_profiles.json"
    profile_file.write_text('[{"user_id": 0}]', encoding="utf-8")

    manager = MagicMock()
    manager.get_simulation.return_value = None

    def _raise_cancel(**kwargs):
        state = SimpleNamespace(simulation_id="sim_cancel_api")
        raise PrepareCancelledError(state)

    manager.prepare_simulation.side_effect = _raise_cancel

    task_manager = MagicMock()
    run_record = {"run_id": run_id}

    captured_updates: list[dict] = []
    monkeypatch.setattr(
        api_mod.run_registry,
        "update_run",
        lambda run_id, **kw: captured_updates.append({"run_id": run_id, **kw}),
    )
    monkeypatch.setattr(
        api_mod.ArtifactLocator,
        "simulation_artifacts",
        classmethod(lambda cls, sid: {"reddit_profiles": str(profile_file)}),
    )
    monkeypatch.setattr(
        api_mod.ArtifactLocator, "existing_paths", staticmethod(lambda artifacts: artifacts)
    )

    inputs = api_mod._PrepareInputs(
        simulation_requirement="Req",
        document_text="",
        entity_types=None,
        use_llm_for_profiles=True,
        parallel_profile_count=None,
        max_agents=None,
        quota_plan=None,
        agent_language_override=None,
    )

    run_prepare = api_mod._make_prepare_job(
        manager=manager,
        task_manager=task_manager,
        task_id="task-cancel-1",
        simulation_id="sim_cancel_api",
        inputs=inputs,
        storage=MagicMock(),
        llm_model="test-model",
        effective_llm_runtime=None,
        run_record=run_record,
    )

    request_cancel(run_id)
    run_prepare()

    # complete_task lief (Task-Ebene fertig), fail_task NICHT (kein Fehler).
    task_manager.complete_task.assert_called_once()
    task_manager.fail_task.assert_not_called()

    assert len(captured_updates) == 1
    update = captured_updates[0]
    assert update["run_id"] == run_id
    assert update["status"] == "stopped"
    assert update["termination_reason"] == "user_cancel"
    assert update["resume_capability"]["available"] is True

    # Die Profildatei existiert unangetastet weiter — kein Löschen/Rollback.
    assert profile_file.exists()
    assert profile_file.read_text(encoding="utf-8") == '[{"user_id": 0}]'

    # Cancel-Flag ist nach dem Abschluss gelöscht (Hygiene wie finish_cancelled_run).
    from app.services.sim.cancel_flag import is_cancel_requested

    assert is_cancel_requested(run_id) is False
