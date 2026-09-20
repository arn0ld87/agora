"""Tests für Prepare-Resume nach Prozessunterbrechung (Issue #1472c).

Isolationsstrategie wie ``test_prepare_cancel.py``: der Orchestrator
(``prepare_service.prepare_simulation``) läuft mit einem ``_FakeManager``
und einer echten ``EntityReader``-Instanz gegen einen Storage-Stub, der
Knoten in konfigurierbarer, zwischen zwei Aufrufen UNTERSCHIEDLICHER
Reihenfolge liefert — das simuliert exakt den fehlenden ``ORDER BY`` im
Lesepfad (siehe ``prepare_entities.py::_cap_entities_across_types``), der
diesen Slice überhaupt nötig macht: ein naiver Resume, der Phase 1 erneut
liest, würde bei anderer Knotenreihenfolge eine ANDERE Cap-Auswahl treffen.

Abgedeckte Szenarien:
  1  Unterbrechung nach N Personas, dann Resume: die finale
     Generierungsliste (Auswahl + Reihenfolge) ist BYTGENAU identisch mit
     einem ununterbrochenen Lauf — trotz unterschiedlicher Lesereihenfolge
     beim zweiten Read. Kernszenario des Issues.
  2  Bereits generierte Personas werden beim Resume NICHT erneut per LLM
     erzeugt — belegt über einen Aufruf-Zähler auf
     ``generate_profile_from_entity``.
  3  Ohne verwertbaren Checkpoint (keiner vorhanden, oder Parameter
     weichen ab) ist kein Resume möglich — ``checkpoint_is_resumable``
     liefert ``False``, ein regulärer FAILED-Lauf bleibt FAILED.
  4  Ein Schreibfehler beim Checkpoint bricht die Vorbereitung sichtbar ab
     (Exception propagiert, Status FAILED) statt still weiterzulaufen.
  5  FSM: PREPARING -> INTERRUPTED und INTERRUPTED -> PREPARING sind
     erlaubt; INTERRUPTED ist kein Terminalzustand.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import prepare_checkpoint, prepare_service
from app.services.prepare_service import prepare_simulation
from app.services.simulation_manager import SimulationStatus
from app.services.simulation_state_machine import (
    TERMINAL_STATES,
    assert_valid_transition,
    is_valid_transition,
)


# ---------------------------------------------------------------------------
# Fixtures / Helfer
# ---------------------------------------------------------------------------


def _raw_node(name: str, uuid: str, entity_type: str) -> dict:
    return {
        "uuid": uuid,
        "name": name,
        "labels": ["Entity", entity_type],
        "summary": f"Zusammenfassung für {name}",
        "attributes": {},
    }


class _OrderedStorage:
    """Storage-Stub: liefert konfigurierbare Knotenreihenfolgen pro Aufruf.

    Simuliert den fehlenden ``ORDER BY`` des echten Lesepfads — jeder
    Aufruf von ``get_filtered_entities_with_edges`` kann eine andere
    Knotenreihenfolge liefern, genau wie ein erneuter Neo4j-Read.
    """

    def __init__(self, orders: list[list[dict]]) -> None:
        self._orders = orders
        self.call_count = 0

    def get_filtered_entities_with_edges(
        self, *, graph_id: str, defined_entity_types, enrich_with_edges: bool
    ) -> dict:
        order = self._orders[min(self.call_count, len(self._orders) - 1)]
        self.call_count += 1
        return {"entities": order, "total_count": len(order)}


class _FakeManager:
    """Minimaler Manager-Stub, echte FSM-Validierung wie ``test_prepare_cancel.py``."""

    def __init__(self, state: SimpleNamespace, sim_dir: Path) -> None:
        self.state = state
        self._sim_dir = sim_dir

    def _load_simulation_state(self, simulation_id: str) -> SimpleNamespace:
        assert simulation_id == self.state.simulation_id
        return self.state

    def _set_status(self, state: SimpleNamespace, new_status: SimulationStatus) -> None:
        assert_valid_transition(state.status, new_status)
        state.status = new_status

    def _get_simulation_dir(self, simulation_id: str) -> str:
        self._sim_dir.mkdir(parents=True, exist_ok=True)
        return str(self._sim_dir)

    def _save_simulation_state(self, state: SimpleNamespace) -> None:
        pass


def _make_state(simulation_id: str, graph_id: str, *, status=SimulationStatus.CREATED) -> SimpleNamespace:
    return SimpleNamespace(
        simulation_id=simulation_id,
        project_id="proj-1",
        graph_id=graph_id,
        status=status,
        entities_count=0,
        profiles_count=0,
        entity_types=[],
        persona_floor=None,
        error=None,
        enable_reddit=True,
        enable_twitter=False,
        config_generated=False,
        config_reasoning="",
    )


@pytest.fixture(autouse=True)
def _stub_settings_and_phase3(monkeypatch):
    """Phase 3 (LLM-Config) und die Parallelitäts-Auflösung sind für diesen
    Slice irrelevant — analog ``test_prepare_cancel.py`` gestubbt, damit nur
    Phase 1+2 (die vom Checkpoint betroffenen Phasen) real laufen.
    """
    monkeypatch.setattr(
        prepare_service, "_get_settings", lambda: SimpleNamespace(effective_value=lambda k: "1")
    )

    def _phase3_stub(manager, state, *args, **kwargs):
        state.config_generated = True
        return None

    monkeypatch.setattr(prepare_service, "_phase_generate_config", _phase3_stub)


@pytest.fixture()
def _phase2_spy(monkeypatch):
    """Zeichnet jeden ``_phase_generate_profiles``-Aufruf auf (Profile +
    finale Generierungsliste), ohne das echte Verhalten zu verändern.
    """
    captured: list[tuple[list, list]] = []
    original = prepare_service._phase_generate_profiles

    def _spy(*args, **kwargs):
        result = original(*args, **kwargs)
        captured.append(result)
        return result

    monkeypatch.setattr(prepare_service, "_phase_generate_profiles", _spy)
    return captured


def _run(manager: _FakeManager, simulation_id: str, storage: Any, **kwargs) -> SimpleNamespace:
    return prepare_simulation(
        manager,
        simulation_id,
        "Requirement text",
        "document text",
        storage=storage,
        use_llm_for_profiles=False,
        parallel_profile_count=1,
        **kwargs,
    )


# Sechs Entities über zwei Typen — max_agents=4 zwingt
# ``_cap_entities_across_types`` zum Round-Robin und macht die
# Lesereihenfolge auswahlrelevant (siehe Moduldocstring).
_S1, _S2, _S3, _S4 = (
    _raw_node("Stakeholder 1", "s1", "Stakeholder"),
    _raw_node("Stakeholder 2", "s2", "Stakeholder"),
    _raw_node("Stakeholder 3", "s3", "Stakeholder"),
    _raw_node("Stakeholder 4", "s4", "Stakeholder"),
)
_I1, _I2 = (
    _raw_node("Institution 1", "i1", "Institution"),
    _raw_node("Institution 2", "i2", "Institution"),
)

# Attempt 1 (Baseline, ununterbrochen): Lesereihenfolge [S1,S2,S3,S4,I1,I2].
# Round-Robin-Cap(max=4): Runde 0 nimmt je 1 pro Typ (S1, I1), Runde 1 das
# nächste (S2, I2) -> Auswahl [S1, I1, S2, I2], Reserve [S3, S4].
_ORDER_BASELINE = [_S1, _S2, _S3, _S4, _I1, _I2]
_EXPECTED_SELECTION = ["s1", "i1", "s2", "i2"]

# Attempt 2 (Resume): bewusst ANDERE Lesereihenfolge — simuliert den
# fehlenden ORDER BY. Ein Resume, der Phase 1 neu berechnet, würde hier
# [S4, I2, S3, I1] auswählen statt [S1, I1, S2, I2] — echter Quoten-Drift.
_ORDER_SHUFFLED = [_S4, _S3, _I2, _S2, _S1, _I1]


# ---------------------------------------------------------------------------
# Szenario 1+2: Kein Quoten-Drift, keine doppelte Persona-Erzeugung
# ---------------------------------------------------------------------------


def test_resume_reproduces_baseline_selection_without_regenerating_done_profiles(
    tmp_path, monkeypatch, _phase2_spy
):
    # --- Baseline: ununterbrochener Lauf --------------------------------
    baseline_storage = _OrderedStorage([_ORDER_BASELINE])
    baseline_state = _make_state("sim-baseline", "graph-x")
    baseline_manager = _FakeManager(baseline_state, tmp_path / "baseline")

    baseline_result = _run(baseline_manager, "sim-baseline", baseline_storage, max_agents=4)

    assert baseline_result.status == SimulationStatus.READY
    baseline_profiles, baseline_expanded = _phase2_spy[0]
    assert [e.uuid for e in baseline_expanded] == _EXPECTED_SELECTION
    assert [e.get_entity_type() for e in baseline_expanded] == [
        "Stakeholder", "Institution", "Stakeholder", "Institution",
    ]

    # --- Checkpoint vorbereiten: simuliert "nach 2 von 4 Personas
    # unterbrochen" — die ersten beiden Profile aus dem Baseline-Lauf
    # gelten als bereits generiert.
    resume_sim_dir = tmp_path / "resume"
    resume_sim_dir.mkdir()
    partial = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-resume",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=_EXPECTED_SELECTION,
        reserve_entity_uuids=["s3", "s4"],
        expanded_entity_uuids=_EXPECTED_SELECTION,
        entities_count=4,
        entity_types=["Stakeholder", "Institution"],
    )
    for index in (0, 1):
        partial = partial.with_completed_profile(
            index, prepare_checkpoint.profile_to_dict(baseline_profiles[index])
        )
    prepare_checkpoint.save_checkpoint(str(resume_sim_dir), partial)

    # --- Aufruf-Zähler: belegt, dass für Index 0/1 KEIN LLM-/Generierungs-
    # Aufruf mehr erfolgt (Szenario 2).
    call_log: list[str] = []
    from app.services.oasis_profile_generator import OasisProfileGenerator

    original_generate = OasisProfileGenerator.generate_profile_from_entity

    def _counting_generate(self, *args, **kwargs):
        entity = kwargs.get("entity") or args[0]
        call_log.append(entity.uuid)
        return original_generate(self, *args, **kwargs)

    monkeypatch.setattr(
        OasisProfileGenerator, "generate_profile_from_entity", _counting_generate
    )

    # --- Resume: gleiche Parameter, ANDERE Lesereihenfolge ---------------
    resume_storage = _OrderedStorage([_ORDER_SHUFFLED])
    resume_state = _make_state(
        "sim-resume", "graph-x", status=SimulationStatus.INTERRUPTED
    )
    resume_manager = _FakeManager(resume_state, resume_sim_dir)

    resume_result = _run(resume_manager, "sim-resume", resume_storage, max_agents=4)

    assert resume_result.status == SimulationStatus.READY
    resume_profiles, resume_expanded = _phase2_spy[1]

    # Kern des Tests: identische Auswahl UND Reihenfolge trotz
    # unterschiedlicher Lesereihenfolge beim Resume-Read.
    assert [e.uuid for e in resume_expanded] == _EXPECTED_SELECTION
    assert [e.get_entity_type() for e in resume_expanded] == [
        "Stakeholder", "Institution", "Stakeholder", "Institution",
    ]

    # Nur die beiden NICHT gecheckpointeten Indizes (s2, i2) wurden neu
    # generiert — s1/i1 kamen unverändert aus dem Checkpoint.
    assert sorted(call_log) == sorted(["s2", "i2"])
    assert resume_profiles[0].source_entity_uuid == baseline_profiles[0].source_entity_uuid
    assert resume_profiles[0].name == baseline_profiles[0].name
    assert resume_profiles[1].source_entity_uuid == baseline_profiles[1].source_entity_uuid

    # Checkpoint ist nach erfolgreichem Abschluss aufgeräumt.
    assert prepare_checkpoint.load_checkpoint(str(resume_sim_dir)) is None


# ---------------------------------------------------------------------------
# Szenario 3: Kein verwertbarer Checkpoint -> kein Resume-Angebot
# ---------------------------------------------------------------------------


def test_checkpoint_is_resumable_false_without_completed_profiles():
    empty = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=["s1"],
        reserve_entity_uuids=[],
        expanded_entity_uuids=["s1"],
        entities_count=1,
        entity_types=["Stakeholder"],
    )
    assert prepare_checkpoint.checkpoint_is_resumable(
        empty,
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
    ) is False

    assert prepare_checkpoint.checkpoint_is_resumable(
        None,
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
    ) is False


def test_checkpoint_is_resumable_false_on_parameter_mismatch():
    checkpoint = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=["s1"],
        reserve_entity_uuids=[],
        expanded_entity_uuids=["s1"],
        entities_count=1,
        entity_types=["Stakeholder"],
    ).with_completed_profile(0, {"user_id": 0, "user_name": "u", "name": "n", "bio": "b", "persona": "p"})

    # max_agents weicht ab -> nicht mehr verwertbar.
    assert prepare_checkpoint.checkpoint_is_resumable(
        checkpoint,
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=8,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
    ) is False


def test_resolve_interruption_status_ohne_checkpoint_bleibt_failed(tmp_path):
    assert prepare_checkpoint.resolve_interruption_status(str(tmp_path)) == "failed"


def test_resolve_interruption_status_mit_verwertbarem_checkpoint_ist_interrupted(tmp_path):
    checkpoint = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=None,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=["s1"],
        reserve_entity_uuids=[],
        expanded_entity_uuids=["s1"],
        entities_count=1,
        entity_types=["Stakeholder"],
    ).with_completed_profile(0, {"user_id": 0, "user_name": "u", "name": "n", "bio": "b", "persona": "p"})
    prepare_checkpoint.save_checkpoint(str(tmp_path), checkpoint)

    assert prepare_checkpoint.resolve_interruption_status(str(tmp_path)) == "interrupted"


# ---------------------------------------------------------------------------
# Szenario 4: Checkpoint-Schreibfehler bricht sichtbar ab
# ---------------------------------------------------------------------------


def test_checkpoint_write_failure_propagiert(tmp_path):
    checkpoint = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=None,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=["s1"],
        reserve_entity_uuids=[],
        expanded_entity_uuids=["s1"],
        entities_count=1,
        entity_types=["Stakeholder"],
    )
    # Zielpfad ist eine bestehende DATEI statt eines Verzeichnisses — jeder
    # Schreibversuch darunter muss fehlschlagen (kein stilles Schlucken).
    blocked_dir = tmp_path / "not_a_directory"
    blocked_dir.write_text("blockiert das Verzeichnis")

    with pytest.raises(OSError):
        prepare_checkpoint.save_checkpoint(str(blocked_dir), checkpoint)


def test_prepare_simulation_bricht_sichtbar_ab_wenn_checkpoint_schreiben_fehlschlaegt(
    tmp_path, monkeypatch
):
    storage = _OrderedStorage([[_S1, _I1]])
    state = _make_state("sim-io-fail", "graph-x")
    manager = _FakeManager(state, tmp_path / "io_fail")

    def _boom(*args, **kwargs):
        raise OSError("Disk voll (simuliert)")

    monkeypatch.setattr(prepare_checkpoint, "write_json_atomic", _boom)

    with pytest.raises(OSError):
        _run(manager, "sim-io-fail", storage, max_agents=2)

    assert state.status == SimulationStatus.FAILED


# ---------------------------------------------------------------------------
# Szenario 5: FSM
# ---------------------------------------------------------------------------


def test_fsm_erlaubt_preparing_zu_interrupted():
    assert_valid_transition(SimulationStatus.PREPARING, SimulationStatus.INTERRUPTED)


def test_fsm_erlaubt_retry_aus_interrupted():
    assert_valid_transition(SimulationStatus.INTERRUPTED, SimulationStatus.PREPARING)


def test_fsm_interrupted_ist_nicht_terminal():
    assert SimulationStatus.INTERRUPTED not in TERMINAL_STATES


def test_fsm_verbietet_interrupted_direkt_zu_ready():
    assert is_valid_transition(SimulationStatus.INTERRUPTED, SimulationStatus.READY) is False
