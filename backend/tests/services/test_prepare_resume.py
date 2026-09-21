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
def artifact_store(monkeypatch, tmp_path):
    """Isolierter Artefakt-Store je Test.

    Der Prepare-Checkpoint geht seit Issue #13 nicht mehr direkt über
    ``json_io``, sondern über den ``SimulationArtifactStore``. Ohne diese
    Fixture schriebe jeder Test in das echte Simulationsverzeichnis.
    """
    from app.services import artifact_store as artifact_store_module

    store = artifact_store_module.LocalFilesystemArtifactStore(
        simulations_root=str(tmp_path / "simulations")
    )
    monkeypatch.setattr(artifact_store_module, "resolve_default_store", lambda: store)
    monkeypatch.setattr(prepare_checkpoint, "resolve_default_store", lambda: store)
    return store


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
        # Codex-Finding P1 (PR #1539): fixierter Slot-Plan, sonst nicht
        # resumable (siehe ``checkpoint_is_resumable``).
        demographic_slots=[
            {"age": 30, "gender": "female", "mbti": "INTJ"},
            {"age": 40, "gender": "male", "mbti": "ENTP"},
            {"age": 25, "gender": "nonbinary", "mbti": "INFP"},
            {"age": 55, "gender": "female", "mbti": "ESTJ"},
        ],
    )
    for index in (0, 1):
        partial = partial.with_completed_profile(
            index, prepare_checkpoint.profile_to_dict(baseline_profiles[index])
        )
    prepare_checkpoint.save_checkpoint("sim-resume", partial)

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
    assert prepare_checkpoint.load_checkpoint("sim-resume") is None


def test_resume_reuses_demographic_slot_plan_instead_of_reshuffling(
    tmp_path, monkeypatch, _phase2_spy
):
    """Ein Resume darf den demografischen Slot-Plan nicht neu würfeln.

    Codex-Finding P1 (PR #1539): ``_build_demographic_slots`` mischt
    Alters-/Gender-/MBTI-Slots bei jedem Lauf zufällig. Ohne fixierten Plan
    im Checkpoint würden die aus dem Checkpoint übernommenen Profile ihre
    ursprünglichen Slots behalten, während die fehlenden Indizes Slots aus
    einer NEUEN Mischung bekämen — ein teilweise fortgesetzter Lauf könnte
    damit die vorgegebene demografische Gesamtverteilung verletzen.

    Konkret geprüft: (1) ``_build_demographic_slots`` wird beim Resume kein
    einziges Mal aufgerufen — der Plan kommt vollständig aus dem
    Checkpoint —, und (2) die NEU generierten Slots (Index 2/3) sind nach
    dem Resume identisch mit dem Baseline-Lauf.
    """
    from app.services.oasis_profile_generator import OasisProfileGenerator

    slot_call_log: list[int] = []
    original_build_slots = OasisProfileGenerator._build_demographic_slots

    def _counting_build_slots(self, entities):
        slot_call_log.append(len(entities))
        return original_build_slots(self, entities)

    monkeypatch.setattr(
        OasisProfileGenerator, "_build_demographic_slots", _counting_build_slots
    )

    # --- Baseline: ununterbrochener Lauf --------------------------------
    baseline_storage = _OrderedStorage([_ORDER_BASELINE])
    baseline_state = _make_state("sim-baseline-slots", "graph-x")
    baseline_manager = _FakeManager(baseline_state, tmp_path / "baseline-slots")

    baseline_result = _run(
        baseline_manager, "sim-baseline-slots", baseline_storage, max_agents=4
    )
    assert baseline_result.status == SimulationStatus.READY
    baseline_profiles, _ = _phase2_spy[0]

    # Genau einmal gewürfelt -- für alle vier Entities in einem Rutsch.
    assert slot_call_log == [4]

    # --- Checkpoint vorbereiten: 2 von 4 Personas gelten als fertig,
    # Slot-Plan spiegelt exakt die Baseline-Mischung.
    resume_sim_dir = tmp_path / "resume-slots"
    resume_sim_dir.mkdir()
    partial = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-resume-slots",
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
        demographic_slots=[
            {"age": p.age, "gender": p.gender, "mbti": p.mbti}
            for p in baseline_profiles
        ],
    )
    for index in (0, 1):
        partial = partial.with_completed_profile(
            index, prepare_checkpoint.profile_to_dict(baseline_profiles[index])
        )
    prepare_checkpoint.save_checkpoint("sim-resume-slots", partial)

    # --- Resume: andere Lesereihenfolge, Slot-Aufruf-Zähler zurückgesetzt.
    slot_call_log.clear()
    resume_storage = _OrderedStorage([_ORDER_SHUFFLED])
    resume_state = _make_state(
        "sim-resume-slots", "graph-x", status=SimulationStatus.INTERRUPTED
    )
    resume_manager = _FakeManager(resume_state, resume_sim_dir)

    resume_result = _run(
        resume_manager, "sim-resume-slots", resume_storage, max_agents=4
    )
    assert resume_result.status == SimulationStatus.READY
    resume_profiles, _ = _phase2_spy[1]

    # Kern des Tests: kein einziger neuer Würfelvorgang beim Resume.
    assert slot_call_log == []

    # Die neu generierten Slots (Index 2/3) entsprechen exakt der
    # Baseline-Mischung -- keine abweichende Verteilung trotz Unterbrechung.
    for index in (2, 3):
        assert resume_profiles[index].age == baseline_profiles[index].age
        assert resume_profiles[index].gender == baseline_profiles[index].gender
        assert resume_profiles[index].mbti == baseline_profiles[index].mbti


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


def test_checkpoint_is_resumable_false_on_language_or_model_mismatch():
    """Ein Checkpoint aus einer anderen Sprach-/Modellroute ist nicht resumable.

    Codex-Finding P2 (PR #1539): ``llm_model``/``language`` werden bei jedem
    ``/prepare``-Aufruf neu aufgelöst und bestimmen die Persona-Sprache bzw.
    die LLM-Handschrift genauso wie die Cap-/Quota-Parameter. Ohne diese
    Prüfung würde ein Resume alte Checkpoint-Profile (z. B. deutsch) mit
    neuen aus einer anderen Route (z. B. englisch oder anderes Modell)
    mischen.
    """
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
        llm_model="gpt-4o",
        language="de",
        demographic_slots=[{"age": 30, "gender": "female", "mbti": "INTJ"}],
    ).with_completed_profile(0, {"user_id": 0, "user_name": "u", "name": "n", "bio": "b", "persona": "p"})

    # Sprache weicht ab -> nicht mehr verwertbar.
    assert prepare_checkpoint.checkpoint_is_resumable(
        checkpoint,
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        llm_model="gpt-4o",
        language="en",
    ) is False

    # Modell weicht ab -> nicht mehr verwertbar.
    assert prepare_checkpoint.checkpoint_is_resumable(
        checkpoint,
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        llm_model="claude-cli",
        language="de",
    ) is False

    # Beide identisch -> weiterhin resumable.
    assert prepare_checkpoint.checkpoint_is_resumable(
        checkpoint,
        simulation_id="sim-x",
        graph_id="graph-x",
        defined_entity_types=None,
        max_agents=4,
        persona_floor=4,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        llm_model="gpt-4o",
        language="de",
    ) is True


def test_resolve_interruption_status_ohne_checkpoint_bleibt_failed(artifact_store):
    assert prepare_checkpoint.resolve_interruption_status("sim-x") == "failed"


def test_resolve_interruption_status_mit_verwertbarem_checkpoint_ist_interrupted(artifact_store):
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
    prepare_checkpoint.save_checkpoint("sim-x", checkpoint)

    assert prepare_checkpoint.resolve_interruption_status("sim-x") == "interrupted"


# ---------------------------------------------------------------------------
# Szenario 4: Checkpoint-Schreibfehler bricht sichtbar ab
# ---------------------------------------------------------------------------


def test_checkpoint_write_failure_propagiert(artifact_store, monkeypatch):
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

    def _boom(*args, **kwargs):
        raise OSError("Disk voll (simuliert)")

    # Der Fehler kommt aus dem Artefakt-Store, nicht aus einem blockierten
    # Pfad: der Store ist die einzige Schreibstelle, und genau von dort muss
    # ein I/O-Fehler ungefiltert durchschlagen.
    monkeypatch.setattr(artifact_store, "write_json", _boom)

    with pytest.raises(OSError):
        prepare_checkpoint.save_checkpoint("sim-x", checkpoint)


def test_prepare_simulation_bricht_sichtbar_ab_wenn_checkpoint_schreiben_fehlschlaegt(
    tmp_path, monkeypatch, artifact_store
):
    storage = _OrderedStorage([[_S1, _I1]])
    state = _make_state("sim-io-fail", "graph-x")
    manager = _FakeManager(state, tmp_path / "io_fail")

    def _boom(*args, **kwargs):
        raise OSError("Disk voll (simuliert)")

    monkeypatch.setattr(artifact_store, "write_json", _boom)

    with pytest.raises(OSError):
        _run(manager, "sim-io-fail", storage, max_agents=2)

    assert state.status == SimulationStatus.FAILED


# ---------------------------------------------------------------------------
# Szenario 6 (Codex-Finding P3, PR #1539): force_regenerate verwirft Checkpoint
# ---------------------------------------------------------------------------


def test_force_regenerate_verwirft_checkpoint_und_generiert_alles_neu(
    tmp_path, monkeypatch, _phase2_spy
):
    """``force_regenerate=True`` darf keine Profile aus einem alten Checkpoint erben.

    Codex-Finding P3 (PR #1539): ohne Weiterreichung des Flags bis zum
    Checkpoint-Pfad übernähme ein zu den aktuellen Parametern passender
    alter Checkpoint stillschweigend Teilergebnisse, obwohl der Aufrufer
    ausdrücklich eine vollständige Neugenerierung verlangt hat — ein
    gebrochenes Versprechen an den Aufrufer.
    """
    sim_dir = tmp_path / "force"
    sim_dir.mkdir()
    partial = prepare_checkpoint.new_checkpoint(
        simulation_id="sim-force",
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
            index,
            {
                "user_id": index,
                "user_name": f"alt_{index}",
                "name": f"Alt {index}",
                "bio": "b",
                "persona": "p",
            },
        )
    prepare_checkpoint.save_checkpoint("sim-force", partial)

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

    storage = _OrderedStorage([_ORDER_BASELINE])
    state = _make_state("sim-force", "graph-x")
    manager = _FakeManager(state, sim_dir)

    result = _run(manager, "sim-force", storage, max_agents=4, force_regenerate=True)

    assert result.status == SimulationStatus.READY
    force_profiles, force_expanded = _phase2_spy[0]

    # Alle vier Slots wurden neu generiert -- keiner kam unveraendert aus
    # dem alten Checkpoint (der zwei Alt-Profile mit dem Namen "Alt 0"/
    # "Alt 1" trug).
    assert sorted(call_log) == sorted(_EXPECTED_SELECTION)
    assert [e.uuid for e in force_expanded] == _EXPECTED_SELECTION
    assert all(profile.name not in {"Alt 0", "Alt 1"} for profile in force_profiles)

    # Ein neuer Checkpoint wurde angelegt und nach erfolgreichem Abschluss
    # wieder aufgeräumt -- kein Rest vom force-regenerate-Versuch.
    assert prepare_checkpoint.load_checkpoint("sim-force") is None


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
