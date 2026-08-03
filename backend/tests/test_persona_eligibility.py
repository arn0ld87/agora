"""Tests für den Persona-Eligibility-Filter (Issue #1034, Teilpunkt 1).

Deckt ab:
1. Harte Blockliste schließt Entitäten ohne menschlichen Träger aus
   ("USA"/Country, "Agora"/Product, "KI-Lernassistent"/Product), legitime
   Entitäten (Company, Person) bleiben erhalten.
2. Unbekannte Typen (z. B. "Behörde") passieren den Filter, werden aber
   protokolliert — keine harte Allowlist.
3. Ausschlussgründe sind pro Entität abrufbar.
4. Vollständige Leerung des Pools meldet einen blockierenden
   Degradations-Befund über die bestehende Infrastruktur aus #1029.
5. Beide Aufrufpfade (Preview in api/simulation_prepare.py und
   _phase_read_entities in services/prepare_service.py) rufen denselben
   Filter tatsächlich auf und reduzieren die Menge — ein späteres
   Entfernen eines der beiden Aufrufe macht den jeweiligen Test rot.
"""

from __future__ import annotations

import logging
import types
from unittest.mock import MagicMock

from app.services.degradation_collector import DegradationCollector
from app.services.entity_reader import EntityNode, FilteredEntities
from app.services.persona_eligibility import (
    EligibilityExclusion,
    filter_eligible_entities,
)


def _entity(name: str, entity_type: str) -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=["Entity", entity_type],
        summary="",
        attributes={},
    )


# ---------------------------------------------------------------------------
# 1. Blockliste schließt Nicht-Stakeholder aus, legitime Entitäten bleiben
# ---------------------------------------------------------------------------


def test_ineligible_entity_types_are_excluded():
    entities = [
        _entity("USA", "Country"),
        _entity("Agora", "Product"),
        _entity("KI-Lernassistent", "Product"),
        _entity("Beispiel GmbH", "Company"),
        _entity("Max Mustermann", "Person"),
    ]

    result = filter_eligible_entities(entities)

    eligible_names = {e.name for e in result.eligible}
    assert eligible_names == {"Beispiel GmbH", "Max Mustermann"}
    excluded_names = {exc.entity_name for exc in result.exclusions}
    assert excluded_names == {"USA", "Agora", "KI-Lernassistent"}


# ---------------------------------------------------------------------------
# 2. Unbekannte Typen passieren, werden aber protokolliert
# ---------------------------------------------------------------------------


def test_unknown_entity_type_passes_but_is_logged(caplog, monkeypatch):
    # ``get_logger`` setzt ``propagate = False`` auf jeder Ebene der
    # "agora.*"-Hierarchie — caplogs Root-Handler sieht sonst keine
    # Records (siehe test_graph_ontology_upload_atomicity.py::_capture_agora_logs).
    caplog.set_level(logging.DEBUG)
    for name, candidate in list(logging.root.manager.loggerDict.items()):
        if isinstance(candidate, logging.Logger) and (
            name == "agora" or name.startswith("agora.")
        ):
            monkeypatch.setattr(candidate, "propagate", True)
            monkeypatch.setattr(candidate, "level", logging.DEBUG)

    entities = [_entity("Bundesnetzagentur", "Behörde")]

    result = filter_eligible_entities(entities)

    assert [e.name for e in result.eligible] == ["Bundesnetzagentur"]
    assert result.exclusions == []
    assert any(
        "unbekannter entity_type" in record.getMessage()
        and "Bundesnetzagentur" in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# 3. Ausschlussgründe sind pro Entität abrufbar
# ---------------------------------------------------------------------------


def test_exclusion_reasons_are_available_per_entity():
    entities = [_entity("USA", "Country"), _entity("Max Mustermann", "Person")]

    result = filter_eligible_entities(entities)

    assert len(result.exclusions) == 1
    exclusion = result.exclusions[0]
    assert isinstance(exclusion, EligibilityExclusion)
    assert exclusion.entity_name == "USA"
    assert exclusion.entity_type == "Country"
    assert "Blockliste" in exclusion.reason


# ---------------------------------------------------------------------------
# 4. Vollständige Leerung ⇒ blockierender Degradations-Befund
# ---------------------------------------------------------------------------


def test_full_pool_exclusion_records_blocking_degradation():
    entities = [_entity("USA", "Country"), _entity("Agora", "Product")]
    collector = DegradationCollector()

    result = filter_eligible_entities(entities, degradations=collector)

    assert result.eligible == []
    report = collector.report()
    assert report.has_blocking
    blocking_events = [e for e in report.events if e.is_blocking]
    assert len(blocking_events) == 1
    assert blocking_events[0].context["entities_before"] == 2
    assert blocking_events[0].context["entities_after"] == 0


def test_partial_exclusion_does_not_record_degradation():
    entities = [_entity("USA", "Country"), _entity("Max Mustermann", "Person")]
    collector = DegradationCollector()

    filter_eligible_entities(entities, degradations=collector)

    assert not collector


# ---------------------------------------------------------------------------
# 5. Beide Aufrufpfade rufen denselben Filter auf und reduzieren die Menge
# ---------------------------------------------------------------------------


def _mixed_entity_pool():
    return [_entity("USA", "Country"), _entity("Max Mustermann", "Person")]


def test_phase_read_entities_reduces_via_eligibility_filter(monkeypatch):
    from app.services import prepare_service as ps_mod
    import app.services.persona_eligibility as pe_mod

    entities = _mixed_entity_pool()
    fake_filtered = FilteredEntities(
        entities=list(entities),
        entity_types={"Country", "Person"},
        total_count=2,
        filtered_count=2,
    )
    fake_reader = MagicMock()
    fake_reader.filter_defined_entities.return_value = fake_filtered
    monkeypatch.setattr(ps_mod, "EntityReader", lambda _storage: fake_reader)

    spy = MagicMock(wraps=pe_mod.filter_eligible_entities)
    monkeypatch.setattr(ps_mod, "filter_eligible_entities", spy)

    state = types.SimpleNamespace(graph_id="graph_1", entities_count=0, entity_types=[])
    result = ps_mod._phase_read_entities(
        state,
        storage=MagicMock(),
        defined_entity_types=None,
        max_agents=None,
    )

    assert spy.called
    assert result.filtered_count == 1
    assert [e.name for e in result.entities] == ["Max Mustermann"]
    assert state.entities_count == 1


def test_simulation_prepare_preview_path_reduces_via_eligibility_filter(monkeypatch):
    from unittest.mock import MagicMock as MM

    from flask import Flask

    from app.api import simulation_bp
    from app.api import simulation_prepare as sp_mod
    import app.services.persona_eligibility as pe_mod
    from app.contracts.llm_routing_contract import ResolvedRoute

    entities = _mixed_entity_pool()
    fake_filtered = FilteredEntities(
        entities=list(entities),
        entity_types={"Country", "Person"},
        total_count=2,
        filtered_count=2,
    )

    fake_state = MM()
    fake_state.project_id = "proj_123"
    fake_state.graph_id = "graph_123"
    fake_state.source_simulation_id = None
    fake_state.root_simulation_id = None
    fake_state.branch_name = None
    fake_state.branch_depth = 0
    fake_state.entities_count = 0
    fake_state.entity_types = []

    fake_project = MM()
    fake_project.simulation_requirement = "Discuss the project"

    fake_manager = MM()
    fake_manager.get_simulation.return_value = fake_state
    fake_manager.prepare_simulation.side_effect = lambda **kwargs: MM(
        to_simple_dict=lambda: {"simulation_id": "sim_0123456789ab", "status": "ready"}
    )

    class FakeTaskManager:
        def create_task(self, *args, **kwargs):
            return "task_prepare_1"

        def update_task(self, *args, **kwargs):
            return None

        def complete_task(self, *args, **kwargs):
            return None

        def fail_task(self, *args, **kwargs):
            return None

    class FakeRouter:
        def __init__(self, run_id: str):
            self.run_id = run_id

        def resolve(self, _stage_id: str):
            return ResolvedRoute(
                stage="persona_generation",
                provider_id="openai",
                model="gpt-4o-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=9,
            )

        def lock_stage(self, *_args, **_kwargs):
            return None

    def run_inline(self):
        self.run()

    spy = MagicMock(wraps=pe_mod.filter_eligible_entities)
    monkeypatch.setattr(sp_mod, "filter_eligible_entities", spy)

    monkeypatch.setattr(sp_mod, "SimulationManager", lambda: fake_manager)
    monkeypatch.setattr(sp_mod.ProjectManager, "get_project", lambda _pid: fake_project)
    monkeypatch.setattr(sp_mod.ProjectManager, "get_extracted_text", lambda _pid: "document text")
    monkeypatch.setattr(sp_mod, "get_simulation_storage", lambda: MM())
    monkeypatch.setattr(
        sp_mod,
        "EntityReader",
        lambda _storage: MM(filter_defined_entities=MM(return_value=fake_filtered)),
    )
    monkeypatch.setattr(sp_mod, "seed_run_stage_routing", lambda *a, **k: None)
    monkeypatch.setattr(sp_mod, "_check_simulation_prepared", lambda _sid: (False, {}))
    monkeypatch.setattr(sp_mod, "StageModelRouter", FakeRouter)
    monkeypatch.setattr(sp_mod, "resolve_route_api_key", lambda *_a, **_k: "sk-route")
    monkeypatch.setattr(
        sp_mod.run_registry,
        "create_run",
        lambda *a, **k: {"run_id": "run_prepare_1"},
    )
    monkeypatch.setattr("app.jobs.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)

    app = Flask(__name__)
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 1000
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions = {"neo4j_storage": MM(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    client = app.test_client()

    response = client.post(
        "/api/simulation/prepare",
        json={"simulation_id": "sim_0123456789ab"},
    )

    assert response.status_code == 200, response.get_json()
    assert spy.called
    body = response.get_json()
    assert body["data"]["expected_entities_count"] == 1


def test_phase_read_entities_reports_into_the_caller_collector(monkeypatch):
    """Der Befund muss im Sammler des Aufrufers landen.

    Erzeugt die Phase ihren eigenen ``DegradationCollector``, ist der nach
    der Rückkehr weg und die blockierende Meldung wirkungslos — sie sähe
    im Code trotzdem nach Absicherung aus. Genau diese Fehlerklasse
    (Wirkung geht eine Ebene weiter verloren) hat #1029 zweimal getroffen.
    """
    from app.services import prepare_service as ps_mod

    only_ineligible = [_entity("USA", "Country"), _entity("Agora", "Product")]
    fake_filtered = FilteredEntities(
        entities=list(only_ineligible),
        entity_types={"Country", "Product"},
        total_count=2,
        filtered_count=2,
    )
    fake_reader = MagicMock()
    fake_reader.filter_defined_entities.return_value = fake_filtered
    monkeypatch.setattr(ps_mod, "EntityReader", lambda _storage: fake_reader)

    collector = DegradationCollector()
    state = types.SimpleNamespace(graph_id="graph_1", entities_count=0, entity_types=[])

    ps_mod._phase_read_entities(
        state,
        storage=MagicMock(),
        defined_entity_types=None,
        max_agents=None,
        degradations=collector,
    )

    assert collector.has_blocking
    assert len(collector) == 1


def test_phase_generate_profiles_passes_collector_to_generator(monkeypatch, tmp_path):
    """``generate_profiles_from_entities`` muss den Sammler bekommen.

    Der Parameter existiert seit #1029 (Slice 12), wurde vom produktiven
    Prepare-Pfad aber nie gefüllt — ``_report_persona_degradation`` lief
    damit nie. Ohne diese Weitergabe bleibt die Meldung über regelbasierte
    Fallback-Profile dort tot.
    """
    from app.services import prepare_service as ps_mod

    captured: dict = {}

    class FakeGenerator:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate_profiles_from_entities(self, **kwargs):
            captured.update(kwargs)
            return []

        def save_profiles(self, **_kwargs):
            return None

    monkeypatch.setattr(ps_mod, "OasisProfileGenerator", FakeGenerator)

    state = types.SimpleNamespace(
        graph_id="graph_1",
        enable_reddit=False,
        enable_twitter=False,
        profiles_count=0,
    )
    filtered = types.SimpleNamespace(entities=[_entity("Max Mustermann", "Person")])
    collector = DegradationCollector()

    ps_mod._phase_generate_profiles(
        state,
        MagicMock(),
        filtered,
        str(tmp_path),
        llm_model=None,
        language="de",
        use_llm_for_profiles=False,
        parallel_profile_count=1,
        degradations=collector,
    )

    assert captured.get("degradations") is collector
