"""Regressionstests für Slice 2B (Befunde 5.1, 5.2, 5.3).

5.1: Checkpoint bei aktivem Cancel nicht vorzeitig löschen
5.2: Fallback-Profile mit segment, generation_source, generation_error und identity_binding anreichern
5.3A: Synthetische Skeptiker erhalten identity_binding und _persist_identity_bindings wird aufgerufen
5.3B: prepare_from_personas persistiert identity_bindings und manifest unterstützt Dictionaries
5.3C: _backfill_rejected_slots ruft on_profile_saved-Callback auf
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.contracts.persona_identity_contract import (
    PersonaIdentityBinding,
    PersonaIdentityBindingManifest,
)
from app.services.oasis_profile_batch_results import (
    _backfill_rejected_slots,
    _consume_thread_results,
    _entity_binding,
)
from app.services.oasis_profile_generator import OasisAgentProfile
from app.services.persona_identity_binding import build_identity_binding_manifest
from app.services.persona_prepare_service import prepare_from_personas
from app.services.prepare_checkpoint import new_checkpoint
from app.services.prepare_service_helpers import _phase_generate_profiles
from app.services.prepare_skeptic_profiles import (
    _phase_profile_synthetic_skeptics,
    build_skeptic_profiles,
)
from app.services.sim.cancel_flag import clear_cancel, request_cancel
from app.services.simulation_manager import SimulationStatus


# ============================================================================
# 5.1: Checkpoint preservation on cancellation
# ============================================================================

def test_checkpoint_preserved_on_cancel(tmp_path):
    """Befund 5.1: Checkpoint wird NICHT gelöscht, wenn Cancel angefordert wurde."""
    sim_id = "sim_cancel_test"
    run_id = "run_cancel_test"
    sim_dir = str(tmp_path / sim_id)
    os.makedirs(sim_dir, exist_ok=True)

    state = SimpleNamespace(
        simulation_id=sim_id,
        run_id=run_id,
        project_id="proj-1",
        graph_id="graph-1",
        status=SimulationStatus.PREPARING,
        entities_count=0,
        profiles_count=0,
        persona_floor=None,
        enable_reddit=False,
        enable_twitter=False,
        entity_types=[],
    )
    storage = MagicMock()
    filtered = SimpleNamespace(entities=[])

    try:
        request_cancel(run_id)

        with (
            patch("app.services.prepare_service.compute_persona_target", return_value=SimpleNamespace(persona_target_count=0)),
            patch("app.services.prepare_service.default_dach_industry_quota", return_value=None),
            patch("app.services.prepare_service._resolve_llm_connection", return_value=(None, None, "ollama")),
            patch("app.services.prepare_service.OasisProfileGenerator"),
            patch("app.services.prepare_service_helpers._build_profile_checkpoint_hooks", return_value=({}, None, [])),
            patch("app.services.prepare_service._persist_identity_bindings"),
            patch("app.services.prepare_checkpoint.clear_checkpoint") as mock_clear,
        ):
            _phase_generate_profiles(
                state,
                storage,
                filtered,
                sim_dir,
                llm_model="test-model",
                language="de",
                use_llm_for_profiles=False,
                parallel_profile_count=1,
                run_id=run_id,
            )

            # Checkpoint darf bei aktivem Cancel NICHT gelöscht werden
            mock_clear.assert_not_called()
    finally:
        clear_cancel(run_id)


def test_checkpoint_cleared_when_not_cancelled(tmp_path):
    """Befund 5.1 Gegenprobe: Checkpoint wird normal gelöscht, wenn kein Cancel aktiv ist."""
    sim_id = "sim_nocancel_test"
    run_id = "run_nocancel_test"
    sim_dir = str(tmp_path / sim_id)
    os.makedirs(sim_dir, exist_ok=True)

    state = SimpleNamespace(
        simulation_id=sim_id,
        run_id=run_id,
        project_id="proj-1",
        graph_id="graph-1",
        status=SimulationStatus.PREPARING,
        entities_count=0,
        profiles_count=0,
        persona_floor=None,
        enable_reddit=False,
        enable_twitter=False,
        entity_types=[],
    )
    storage = MagicMock()
    filtered = SimpleNamespace(entities=[])

    with (
        patch("app.services.prepare_service.compute_persona_target", return_value=SimpleNamespace(persona_target_count=0)),
        patch("app.services.prepare_service.default_dach_industry_quota", return_value=None),
        patch("app.services.prepare_service._resolve_llm_connection", return_value=(None, None, "ollama")),
        patch("app.services.prepare_service.OasisProfileGenerator"),
        patch("app.services.prepare_service_helpers._build_profile_checkpoint_hooks", return_value=({}, None, [])),
        patch("app.services.prepare_service._persist_identity_bindings"),
        patch("app.services.prepare_checkpoint.clear_checkpoint") as mock_clear,
    ):
        _phase_generate_profiles(
            state,
            storage,
            filtered,
            sim_dir,
            llm_model="test-model",
            language="de",
            use_llm_for_profiles=False,
            parallel_profile_count=1,
            run_id=run_id,
        )

        # Checkpoint MUSS regulär gelöscht werden
        mock_clear.assert_called_once_with(sim_id)


# ============================================================================
# 5.2: Fallback profile enrichment & validation
# ============================================================================

def test_fallback_profile_enrichment_and_entity_binding():
    """Befund 5.2: Fallback-Profile enthalten segment, generation_source, error und binding."""
    entity = SimpleNamespace(
        name="Dr. Max Mustermann",
        uuid="ent-1234",
        entity_type="Citizen",
        get_entity_type=lambda: "Citizen",
        segment="Öffentlicher Dienst",
        summary="Beamter im Ministerium",
        attributes={"full_name": "Dr. Max Mustermann", "amt": "Ministerialrat"},
        affiliation="Bund",
    )

    binding = _entity_binding(None, entity)
    assert binding is not None
    assert binding["origin"] == "source_person"
    assert binding["source_name"] == "Dr. Max Mustermann"
    assert binding["source_entity_uuid"] == "ent-1234"

    generator = SimpleNamespace(
        _generate_username=lambda name: "max_m",
        _cancel_checkpoint=lambda c, t, p: False,
        run_id=None,
    )

    future = MagicMock()
    future.result.side_effect = RuntimeError("LLM request timed out")

    profiles = [None]
    profile_generation_errors = []

    with patch("concurrent.futures.ThreadPoolExecutor") as mock_exec_class:
        mock_executor = MagicMock()
        mock_exec_class.return_value.__enter__.return_value = mock_executor
        mock_executor.submit.return_value = future

        with patch("concurrent.futures.as_completed", return_value=[future]):
            def process_result(idx, prof, err):
                profiles[idx] = prof
                if err:
                    profile_generation_errors.append((idx, err))

            _consume_thread_results(
                generator,
                lambda idx, ent: None,
                [entity],
                1,
                process_result,
                [0],
                1,
            )

    fb_profile = profiles[0]
    assert fb_profile is not None
    assert fb_profile.segment == "Öffentlicher Dienst"
    assert fb_profile.generation_source == "rule_based"
    assert "LLM request timed out" in (fb_profile.generation_error or "")
    assert fb_profile.identity_binding is not None
    assert fb_profile.identity_binding["source_entity_uuid"] == "ent-1234"

    from app.contracts import PersonaQuotaPlan
    from app.services.prepare_quota import _validate_persona_quota

    plan = PersonaQuotaPlan(
        total=1,
        targets={"Öffentlicher Dienst": 1},
    )
    _validate_persona_quota(plan, [fb_profile])


# ============================================================================
# 5.3A: Skeptic profiles identity binding & persistence
# ============================================================================

def test_skeptic_profiles_have_identity_binding_and_persisted(tmp_path):
    """Befund 5.3A: Synthetische Skeptiker erhalten identity_binding und werden persistiert."""
    sim_id = "sim_skeptic_test"
    sim_dir = str(tmp_path / sim_id)
    os.makedirs(sim_dir, exist_ok=True)

    config = {
        "contested_question": {"statement": "Soll die Kernkraft wiedereingeführt werden?"},
        "agent_configs": [
            {
                "agent_id": 10,
                "entity_uuid": "synthetic-skeptic-10",
                "entity_name": "Skeptiker 10",
                "entity_type": "Kollektiv",
            },
            {
                "agent_id": 11,
                "entity_uuid": "synthetic-skeptic-11",
                "entity_name": "Skeptiker 11",
                "entity_type": "Kollektiv",
            },
        ],
    }

    skeptics = build_skeptic_profiles(
        config=config,
        existing_profiles=[],
        language="de",
    )

    assert len(skeptics) == 2
    for sk in skeptics:
        assert sk.identity_binding is not None
        assert sk.identity_binding["origin"] == "synthetic_supplement"
        assert sk.identity_binding["source_name"] == sk.name
        assert sk.persona_kind == "collective"
        assert sk.generation_source == "rule_based"

    existing_profile = OasisAgentProfile(
        user_id=1,
        user_name="existing_user",
        name="Existing User",
        bio="Existing User Bio",
        persona="Existing persona text",
        identity_binding=PersonaIdentityBinding(
            origin="synthetic_supplement",
            source_name="Existing User",
        ).model_dump(mode="json"),
    )

    state = SimpleNamespace(
        simulation_id=sim_id,
        status=SimulationStatus.PREPARING,
        profiles_count=1,
        entities_count=1,
        enable_reddit=False,
        enable_twitter=False,
    )

    with patch("app.services.prepare_service._persist_identity_bindings") as mock_persist:
        all_profs = _phase_profile_synthetic_skeptics(
            state=state,
            sim_dir=sim_dir,
            profiles=[existing_profile],
            config=config,
            language="de",
        )

        mock_persist.assert_called_once()
        args, kwargs = mock_persist.call_args
        persisted_profiles = args[2]
        assert len(persisted_profiles) == 3  # 1 bestehendes + 2 skeptiker
        assert len(all_profs) == 3


# ============================================================================
# 5.3B: Library personas identity binding persistence & dict support
# ============================================================================

def test_build_identity_binding_manifest_with_dicts_and_objects():
    """Befund 5.3B: Manifest-Builder unterstützt Dictionaries und Objekte."""
    sim_id = "sim_manifest_test"

    obj_profile = OasisAgentProfile(
        user_id=1,
        user_name="user_one",
        name="User One",
        bio="Bio 1",
        persona="Persona 1",
        persona_kind="individual",
        identity_binding={
            "origin": "synthetic_supplement",
            "source_name": "User One",
        },
    )

    dict_profile = {
        "user_id": 2,
        "username": "user_two",
        "name": "User Two",
        "bio": "Bio 2",
        "persona": "Persona 2",
        "persona_kind": "individual",
        "identity_binding": {
            "origin": "synthetic_supplement",
            "source_name": "User Two",
        },
    }

    no_binding_profile = {
        "user_id": 3,
        "username": "user_three",
    }

    manifest = build_identity_binding_manifest(
        sim_id, [obj_profile, dict_profile, no_binding_profile, None]
    )

    assert isinstance(manifest, PersonaIdentityBindingManifest)
    assert manifest.simulation_id == sim_id
    assert len(manifest.entries) == 2
    assert manifest.entries[0].user_id == 1
    assert manifest.entries[0].user_name == "user_one"
    assert manifest.entries[1].user_id == 2
    assert manifest.entries[1].user_name == "user_two"


def test_prepare_from_personas_persists_identity_bindings(tmp_path):
    """Befund 5.3B: prepare_from_personas schreibt persona_identity_bindings.json."""
    sim_id = "sim_lib_test"
    sim_dir = str(tmp_path / sim_id)
    os.makedirs(sim_dir, exist_ok=True)

    state = SimpleNamespace(
        simulation_id=sim_id,
        project_id="proj-1",
        graph_id="graph-1",
        status=SimulationStatus.CREATED,
        entities_count=0,
        profiles_count=0,
        entity_types=[],
        config_generated=False,
        persona_set_id=None,
        enable_twitter=False,
        enable_reddit=False,
        max_days=3,
        num_agents=1,
    )

    class _Store:
        def __init__(self):
            self.files = {}

        def write_json(self, simulation_id, artifact, data):
            self.files[f"{simulation_id}/{artifact}"] = data

    store = _Store()

    class _Manager:
        def __init__(self):
            self._store = store

        def get_simulation(self, sid):
            return state

        def _set_status(self, st, status):
            st.status = status

        def _get_simulation_dir(self, sid):
            return sim_dir

    personas = [
        {
            "username": "anna_k",
            "name": "Anna K.",
            "bio": "Softwareentwicklerin aus Berlin mit Fokus auf KI.",
            "persona": "Anna K. ist eine 34-jährige Entwicklerin.",
            "identity_binding": {
                "origin": "synthetic_supplement",
                "source_name": "Anna K.",
            },
        }
    ]

    manager = _Manager()
    with patch("app.services.persona_prepare_service._register_run"):
        result_state = prepare_from_personas(
            manager=manager,
            simulation_id=sim_id,
            personas=personas,
        )

    assert result_state.status == SimulationStatus.READY
    manifest_path = os.path.join(sim_dir, "persona_identity_bindings.json")
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["simulation_id"] == sim_id
    assert len(data["entries"]) == 1
    assert data["entries"][0]["user_name"] == "anna_k"


# ============================================================================
# 5.3C: Backfill on_profile_saved hook
# ============================================================================

def test_backfill_rejected_slots_calls_on_profile_saved():
    """Befund 5.3C: _backfill_rejected_slots ruft on_profile_saved auf."""
    generator = SimpleNamespace(
        _build_demographic_slots=lambda ents: [MagicMock()],
        generate_profile_from_entity=MagicMock(),
    )
    rejected_profile = None
    new_profile = OasisAgentProfile(
        user_id=0,
        user_name="new_user",
        name="New User",
        bio="Bio",
        persona="Persona",
    )

    generator.generate_profile_from_entity.return_value = new_profile

    on_profile_saved = MagicMock()

    profiles = [rejected_profile]
    reserve_entity = SimpleNamespace(
        name="Reserve 1",
        uuid="res-1",
        get_entity_type=lambda: "Citizen",
    )

    _backfill_rejected_slots(
        generator,
        profiles=profiles,
        entities=[SimpleNamespace(get_entity_type=lambda: "Citizen")],
        reserve_entities=[reserve_entity],
        use_llm=True,
        rejected=[],
        on_profile_saved=on_profile_saved,
    )

    assert profiles[0] == new_profile
    on_profile_saved.assert_called_once_with(0, new_profile, reserve_entity)


def test_backfill_rejected_slots_error_in_callback_handled():
    """Befund 5.3C: Exception im on_profile_saved-Callback bringt Backfill nicht zum Absturz."""
    generator = SimpleNamespace(
        _build_demographic_slots=lambda ents: [MagicMock()],
        generate_profile_from_entity=MagicMock(),
    )
    new_profile = OasisAgentProfile(
        user_id=0,
        user_name="safe_user",
        name="Safe User",
        bio="Bio",
        persona="Persona",
    )
    generator.generate_profile_from_entity.return_value = new_profile

    failing_callback = MagicMock(side_effect=OSError("Disk write failed in hook"))

    profiles = [None]
    reserve_entity = SimpleNamespace(
        name="Reserve 2",
        uuid="res-2",
        get_entity_type=lambda: "Citizen",
    )

    _backfill_rejected_slots(
        generator,
        profiles=profiles,
        entities=[SimpleNamespace(get_entity_type=lambda: "Citizen")],
        reserve_entities=[reserve_entity],
        use_llm=True,
        rejected=[],
        on_profile_saved=failing_callback,
    )

    assert profiles[0] == new_profile
    failing_callback.assert_called_once_with(0, new_profile, reserve_entity)


# ============================================================================
# Finding 1: Checkpoint entity substitution and reserve consumption
# ============================================================================

def test_checkpoint_with_completed_profile_substitutes_entity_and_consumes_reserve():
    """Finding 1: with_completed_profile aktualisiert expanded_entity_uuids und bereinigt reserve_entity_uuids."""
    cp = new_checkpoint(
        simulation_id="sim_f1_test",
        graph_id="graph_f1",
        defined_entity_types=None,
        max_agents=2,
        persona_floor=2,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=["prim-1", "prim-2"],
        reserve_entity_uuids=["res-1", "res-2"],
        expanded_entity_uuids=["prim-1", "prim-2"],
        entities_count=2,
        entity_types=["Citizen"],
        demographic_slots=[{"age": "20-29"}, {"age": "30-39"}],
    )

    profile_dict = {"user_id": 1, "name": "Res 1 Agent"}
    updated_cp = cp.with_completed_profile(1, profile_dict, entity_uuid="res-1")

    # Index 1 muss nun auf die Ersatz-UUID zeigen
    assert updated_cp.expanded_entity_uuids == ["prim-1", "res-1"]
    # Der verbrauchte Nachrücker darf nicht mehr in reserve_entity_uuids stehen
    assert updated_cp.reserve_entity_uuids == ["res-2"]
    assert "res-1" not in updated_cp.reserve_entity_uuids
    assert updated_cp.completed_profiles["1"] == profile_dict


def test_resume_preserves_backfill_substitution_and_prevents_duplicate_reserve_draw():
    """Finding 1: Resume rekonstruiert die substituierte Entity und filtert verbrauchte Reserve-Kandidaten."""
    from app.services.prepare_entities_merge import (
        _lookup_expanded_entities_from_checkpoint,
        _phase_read_entities_from_checkpoint,
    )

    sim_id = "sim_resume_f1"
    # Checkpoint, bei dem Slot 1 aus der Reserve (res-1) nachbesetzt wurde.
    # Selbst wenn reserve_entity_uuids im Altbestand res-1 noch enthielte:
    cp = new_checkpoint(
        simulation_id=sim_id,
        graph_id="graph_f1",
        defined_entity_types=None,
        max_agents=2,
        persona_floor=2,
        use_llm_for_profiles=False,
        effective_quota_plan=None,
        primary_entity_uuids=["prim-1", "prim-2"],
        reserve_entity_uuids=["res-1", "res-2"],
        expanded_entity_uuids=["prim-1", "res-1"],
        entities_count=2,
        entity_types=["Citizen"],
        demographic_slots=[{"age": "20-29"}, {"age": "30-39"}],
    )

    ent_prim1 = SimpleNamespace(uuid="prim-1", name="Prim 1", get_entity_type=lambda: "Citizen", affiliation=None)
    ent_prim2 = SimpleNamespace(uuid="prim-2", name="Prim 2", get_entity_type=lambda: "Citizen", affiliation=None)
    ent_res1 = SimpleNamespace(uuid="res-1", name="Res 1", get_entity_type=lambda: "Citizen", affiliation=None)
    ent_res2 = SimpleNamespace(uuid="res-2", name="Res 2", get_entity_type=lambda: "Citizen", affiliation=None)

    pool = [ent_prim1, ent_prim2, ent_res1, ent_res2]

    mock_storage = MagicMock()
    mock_reader = MagicMock()
    mock_reader.filter_defined_entities.return_value = SimpleNamespace(entities=pool)

    with (
        patch("app.services.prepare_entities_merge._legacy.EntityReader", return_value=mock_reader),
        patch("app.services.prepare_entities_merge._legacy.filter_eligible_entities", return_value=SimpleNamespace(eligible=pool, exclusions=None)),
    ):
        state = SimpleNamespace(simulation_id=sim_id, entities_count=0, entity_types=[])

        # 1. Phase 1 Resume: reserve_entities darf den verbrauchten res-1 NICHT mehr enthalten!
        filtered = _phase_read_entities_from_checkpoint(state, mock_storage, cp)
        assert filtered is not None
        assert len(filtered.entities) == 2  # prim-1, prim-2
        reserve_uuids = [e.uuid for e in filtered.reserve_entities]
        assert "res-1" not in reserve_uuids
        assert reserve_uuids == ["res-2"]

        # 2. Phase 2 Precomputed Entities: Slot 1 muss genau die Ersatz-Entity (res-1) tragen!
        expanded = _lookup_expanded_entities_from_checkpoint(mock_storage, cp)
        assert expanded is not None
        assert len(expanded) == 2
        assert expanded[0].uuid == "prim-1"
        assert expanded[1].uuid == "res-1"
