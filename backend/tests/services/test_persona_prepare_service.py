"""Tests für ``persona_prepare_service.prepare_from_personas``.

Deckt das ZIEL "Simulation allein aus gespeicherten Personas vorbereiten"
ab: kein Dokument, keine Ontologie, kein Graph. Fixture-Muster (isoliertes
tmp-Datenverzeichnis, ``InMemoryArtifactStore``, tmp-``RunRegistry``) folgt
``tests/contracts/test_branch_override_contract.py``, das dieselbe
FSM-Vorlage (``CREATED -> PREPARING -> READY``) testet.

Kein Neo4j-Zugriff: ``SimulationManager`` wird mit ``InMemoryArtifactStore``
konstruiert, keine Route greift auf ``neo4j_storage`` oder einen echten
Graphen zu.
"""

from __future__ import annotations

import csv
import os

import pytest

from app.services import persona_prepare_service
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager, SimulationStatus


@pytest.fixture
def manager(tmp_path, monkeypatch) -> SimulationManager:
    """Manager mit isoliertem Datenverzeichnis, In-Memory-Store, tmp-RunRegistry."""
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations")
    )
    registry_dir = str(tmp_path / "run_registry")
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", registry_dir)
    RunRegistry._instance = None
    os.makedirs(registry_dir, exist_ok=True)
    yield SimulationManager(store=InMemoryArtifactStore())
    RunRegistry._instance = None


@pytest.fixture
def created_id(manager: SimulationManager) -> str:
    """Eine frisch angelegte Simulation ohne echten Graphen (``graph_id=""``).

    Die Simulation hat keine echte Wissensgraph-Anbindung — ``graph_id`` wird
    hier bewusst leer gelassen und von ``prepare_from_personas`` unverändert
    durchgereicht, statt einen künstlichen Wert zu erfinden.
    """
    state = manager.create_simulation(project_id="proj-1", graph_id="")
    return state.simulation_id


MINIMAL_PERSONA = {"username": "alice", "name": "Alice"}


class TestSuccessfulPrepare:
    def test_reaches_ready(self, manager: SimulationManager, created_id: str) -> None:
        state = persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA]
        )
        assert state.status == SimulationStatus.READY

    def test_persisted_state_is_ready(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA]
        )
        reloaded = manager.get_simulation(created_id)
        assert reloaded is not None
        assert reloaded.status == SimulationStatus.READY

    def test_counters_and_config_generated_are_set(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        state = persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA, {"username": "bob"}]
        )
        assert state.entities_count == 2
        assert state.profiles_count == 2
        assert state.config_generated is True

    def test_simulation_config_is_written_and_readable(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA]
        )
        config = manager._store.read_json(created_id, "simulation_config", default=None)
        assert config is not None
        assert config["simulation_id"] == created_id
        # Keine echte Simulation hat einen Graphen — graph_id bleibt, was die
        # Simulation beim Anlegen mitbekommen hat (hier: "").
        assert config["graph_id"] == ""

    def test_twitter_csv_written_alongside_reddit_json(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA]
        )
        sim_dir = manager._get_simulation_dir(created_id)
        csv_path = os.path.join(sim_dir, "twitter_profiles.csv")
        assert os.path.exists(csv_path)
        with open(csv_path, "r", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"

    def test_run_registry_gets_completed_prepare_run(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA]
        )
        runs = RunRegistry().list_runs(entity_id=created_id)
        assert len(runs) == 1
        assert runs[0]["run_type"] == "simulation_prepare"
        assert runs[0]["status"] == "completed"


class TestFieldGapsAreFilled:
    """Ein Bibliothekseintrag ohne age/gender/mbti/persona_kind darf die
    geschriebene Profildatei trotzdem nicht ohne diese Keys verlassen —
    OASIS indiziert ``agent_info[i]["mbti"]``/["age"]/["gender"] ungeschützt.
    """

    SPARSE_PERSONA = {"username": "sparse_carol"}

    def test_reddit_profile_has_all_required_keys(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [self.SPARSE_PERSONA]
        )
        profiles = manager._store.read_json(created_id, "reddit_profiles", default=[])
        assert len(profiles) == 1
        profile = profiles[0]
        for key in ("user_id", "age", "gender", "mbti", "persona_kind", "karma", "created_at"):
            assert key in profile, f"Feld {key!r} fehlt im geschriebenen Profil"

    def test_gap_filled_fields_have_safe_defaults(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [self.SPARSE_PERSONA]
        )
        profile = manager._store.read_json(created_id, "reddit_profiles", default=[])[0]
        assert profile["user_id"] == 1
        assert isinstance(profile["user_id"], int)
        assert profile["age"] == ""
        assert profile["mbti"] == ""
        assert profile["persona_kind"] == "individual"
        assert isinstance(profile["karma"], int)

    def test_populated_fields_are_kept_as_is(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        rich_persona = {
            "username": "rich_dave",
            "age": 42,
            "gender": "male",
            "mbti": "INTJ",
            "persona_kind": "collective",
            "karma": 555,
        }
        persona_prepare_service.prepare_from_personas(manager, created_id, [rich_persona])
        profile = manager._store.read_json(created_id, "reddit_profiles", default=[])[0]
        assert profile["age"] == 42
        assert profile["gender"] == "male"
        assert profile["mbti"] == "INTJ"
        assert profile["persona_kind"] == "collective"
        assert profile["karma"] == 555

    def test_duplicate_usernames_are_deduplicated(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        """Dedupe ist case-insensitiv (Vergleich), der Suffix behält aber die
        Original-Schreibweise des zweiten Eintrags — gleiches Verhalten wie
        ``add_simulation_profile``."""
        persona_prepare_service.prepare_from_personas(
            manager,
            created_id,
            [{"username": "eve"}, {"username": "Eve"}],
        )
        profiles = manager._store.read_json(created_id, "reddit_profiles", default=[])
        usernames = {p["username"] for p in profiles}
        assert usernames == {"eve", "Eve_1"}


class TestEmptyPersonaListFails:
    def test_raises_value_error(self, manager: SimulationManager, created_id: str) -> None:
        with pytest.raises(ValueError, match="personas darf nicht leer sein"):
            persona_prepare_service.prepare_from_personas(manager, created_id, [])

    def test_does_not_change_simulation_status(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        with pytest.raises(ValueError):
            persona_prepare_service.prepare_from_personas(manager, created_id, [])
        state = manager.get_simulation(created_id)
        assert state is not None
        assert state.status == SimulationStatus.CREATED


class TestGuardsAroundStatusAndExistence:
    def test_unknown_simulation_id_raises(self, manager: SimulationManager) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            persona_prepare_service.prepare_from_personas(
                manager, "sim_does_not_exist", [MINIMAL_PERSONA]
            )

    def test_non_created_status_is_rejected(
        self, manager: SimulationManager, created_id: str
    ) -> None:
        persona_prepare_service.prepare_from_personas(
            manager, created_id, [MINIMAL_PERSONA]
        )
        # Simulation ist jetzt READY — ein zweiter Aufruf darf nicht
        # stillschweigend erneut vorbereiten.
        with pytest.raises(ValueError, match="CREATED"):
            persona_prepare_service.prepare_from_personas(
                manager, created_id, [MINIMAL_PERSONA]
            )
