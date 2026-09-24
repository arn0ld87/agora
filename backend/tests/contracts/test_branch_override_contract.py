"""Contract-Tests für die Branch-Override-Whitelist (Issue #887).

``branching_service.allowed_override_keys`` ist die einzige Stelle im Backend,
die entscheidet, welche Branch-Overrides akzeptiert werden. Bis #887 gab es
dafür keinen einzigen Test — die vorhandenen Branch-Tests
(``tests/api/test_simulation_endpoints.py``, ``tests/test_simulation_api_routes.py``)
decken nur den fehlenden ``branch_name`` ab.

Diese Suite hält drei Dinge fest:

1. **Wirkung je Key** — jeder erlaubte Override landet nachweisbar im
   Branch-Artefakt (Config, State oder Profil-Datei). "Wird nicht abgelehnt"
   reicht nicht: genau diese Lücke hat den in #886 beschriebenen Defekt
   unbemerkt bestehen lassen.
2. **Ablehnungspfad** — ein unbekannter Key wirft ``ValueError`` und wird über
   ``utils/api_responses.handle_api_errors`` zu HTTP 400.
3. **Whitelist als Ganzes** — das Set-Literal wird per AST gegen
   ``EXPECTED_OVERRIDE_KEYS`` gepinnt, damit auch ein *stilles Hinzufügen*
   eines Keys rot wird (verhaltensbasiert nicht erkennbar, der Key-Raum ist
   unendlich).

Issue #886 hat entschieden: ``ai_model_ref`` gehört in die Whitelist. Die
Wirkung ist unten in ``TestOverrideTakesEffect.test_ai_model_ref`` gepinnt;
die Ablehnung von ``ai_model_ref`` + ``llm_model`` läuft am Contract
(``app/contracts/branch_request_contract.py::BranchOverrides``), nicht mehr
hier — dieses Modul testet ausschließlich die dict-basierte
``branching_service.create_branch``-Schicht darunter.

Verortung in ``tests/contracts/``, weil dieses Verzeichnis im verpflichtenden
PR-Smoke-Gate und im Pre-Push-Gate läuft (``pytest tests/contracts/ -x -q``).
Die Whitelist ist ein API-Vertrag gegenüber dem Frontend
(``components/step4/ReportBranchControls.vue``) — ein Drift soll im Gate
auffallen, nicht erst im nächtlichen Full-Run.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, Set
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services import branching_service
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager, SimulationStatus

# ---------------------------------------------------------------------------
# Gepinnter Ist-Zustand (Issue #887, erweitert um ai_model_ref in #886)
# ---------------------------------------------------------------------------

EXPECTED_OVERRIDE_KEYS: Set[str] = {
    "llm_model",
    "language",
    "max_agents",
    "time_config",
    "enable_twitter",
    "enable_reddit",
    "persona_additions",
    "persona_removals",
    "ai_model_ref",
}

# Gegensätzliche Ausgangswerte, damit jeder Plattform-Override den Source-Wert
# tatsächlich umdrehen muss (siehe Docstring der ``source_id``-Fixture).
SOURCE_ENABLE_TWITTER = False
SOURCE_ENABLE_REDDIT = True

BASE_CONFIG: Dict[str, Any] = {
    "llm_model": "source-model",
    "language": "de",
    "max_agents": 10,
    "time_config": {"rounds": 3, "round_minutes": 60},
    "enable_twitter": SOURCE_ENABLE_TWITTER,
    "enable_reddit": SOURCE_ENABLE_REDDIT,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path, monkeypatch) -> SimulationManager:
    """Manager mit isoliertem Datenverzeichnis, In-Memory-Store und tmp-RunRegistry.

    ``create_branch`` schreibt am Ende einen Run ins ``RunRegistry``; dessen
    ``REGISTRY_DIR`` hängt zur Importzeit an ``Config.UPLOAD_FOLDER`` und würde
    sonst das echte ``backend/uploads/`` verschmutzen (Muster analog
    ``tests/services/test_run_registry_authority.py``).
    """
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
def source_id(manager: SimulationManager) -> str:
    """Eine branch-fähige Quell-Simulation: READY + persistierte ``simulation_config``.

    Der FSM-Pfad CREATED → PREPARING → READY wird explizit gefahren, statt
    ``state.status`` zu setzen — ``create_branch`` verlangt einen vorbereiteten
    Status und ``_set_status`` validiert gegen die Transitions-Tabelle.

    ``enable_twitter``/``enable_reddit`` werden explizit gesetzt und decken
    gegensätzliche Ausgangswerte ab. ``create_simulation`` hat für beide
    ``True`` als Default; ein Test, der auf ``True`` overridet, würde auch dann
    bestehen, wenn ``create_branch`` den Override ignoriert und schlicht vom
    Source erbt. Die Werte spiegeln ``BASE_CONFIG``, damit State und Config
    nicht auseinanderlaufen.
    """
    state = manager.create_simulation(
        project_id="proj-887",
        graph_id="graph-887",
        enable_twitter=SOURCE_ENABLE_TWITTER,
        enable_reddit=SOURCE_ENABLE_REDDIT,
    )
    manager._set_status(state, SimulationStatus.PREPARING)
    manager._set_status(state, SimulationStatus.READY)
    manager._store.write_json(state.simulation_id, "simulation_config", dict(BASE_CONFIG))
    return state.simulation_id


def branch_config(manager: SimulationManager, branch_id: str) -> Dict[str, Any]:
    return manager._store.read_json(branch_id, "simulation_config", default={}) or {}


# ---------------------------------------------------------------------------
# 1. Whitelist als Ganzes
# ---------------------------------------------------------------------------


def _whitelist_from_source() -> Set[str]:
    """Extrahiere das Set-Literal ``allowed_override_keys`` per AST.

    Die Whitelist ist eine *lokale* Variable in ``create_branch`` und damit
    nicht importierbar. AST statt Regex, damit Umformatierung (Zeilenumbrüche,
    Quote-Stil) den Test nicht bricht. Erkannt wird jede Zuweisung an den Namen
    ``allowed_override_keys`` mit einem Set-Literal aus String-Konstanten —
    egal ob lokal oder als Modul-Konstante.
    """
    source_path = Path(branching_service.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "allowed_override_keys" not in names:
            continue
        if not isinstance(node.value, ast.Set):
            pytest.fail(
                "allowed_override_keys ist kein Set-Literal mehr "
                f"({type(node.value).__name__}). Test an die neue Form anpassen — "
                "aber bewusst, nicht durch Löschen dieser Prüfung."
            )
        keys = set()
        for element in node.value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                pytest.fail(
                    "allowed_override_keys enthält einen nicht-konstanten Eintrag; "
                    "die Whitelist muss statisch prüfbar bleiben."
                )
            keys.add(element.value)
        return keys

    pytest.fail(
        "allowed_override_keys nicht in branching_service.py gefunden. Wurde die "
        "Whitelist verschoben oder umbenannt? Dann diesen Test mitziehen — die "
        "Whitelist darf nicht ungepinnt bleiben (Issue #887)."
    )


def test_whitelist_matches_pinned_expectation() -> None:
    """Hinzufügen ODER Entfernen eines Keys macht diesen Test rot.

    Bewusste Änderungen gehören hier nachgezogen — zusammen mit einem
    Wirkungs-Test in ``TestOverrideTakesEffect``.
    """
    assert _whitelist_from_source() == EXPECTED_OVERRIDE_KEYS


@pytest.mark.parametrize("key", sorted(EXPECTED_OVERRIDE_KEYS))
def test_every_pinned_key_is_accepted(
    manager: SimulationManager, source_id: str, key: str
) -> None:
    """Kein gepinnter Key darf am Validierungs-Guard scheitern."""
    branching_service.create_branch(
        manager, source_id, f"branch-{key}", overrides={key: None}
    )


# ---------------------------------------------------------------------------
# 2. Wirkung je erlaubtem Key
# ---------------------------------------------------------------------------


class TestOverrideTakesEffect:
    """Je ein Test pro Whitelist-Key: der Override landet im Branch-Artefakt."""

    def test_llm_model(self, manager: SimulationManager, source_id: str) -> None:
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"llm_model": "branch-model"}
        )
        assert branch_config(manager, branch.simulation_id)["llm_model"] == "branch-model"

    def test_language(self, manager: SimulationManager, source_id: str) -> None:
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"language": "en"}
        )
        assert branch_config(manager, branch.simulation_id)["language"] == "en"

    def test_max_agents(self, manager: SimulationManager, source_id: str) -> None:
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"max_agents": 42}
        )
        assert branch_config(manager, branch.simulation_id)["max_agents"] == 42

    @pytest.mark.parametrize("empty", [None, ""])
    def test_scalar_override_ignores_empty_values(
        self, manager: SimulationManager, source_id: str, empty: Any
    ) -> None:
        """``None``/``""`` sind Nicht-Overrides — der Source-Wert bleibt stehen.

        Bewusst gepinnt: das Frontend sendet leere Felder mit, ein Branch darf
        dadurch nicht sein Modell verlieren.
        """
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"llm_model": empty}
        )
        assert branch_config(manager, branch.simulation_id)["llm_model"] == "source-model"

    def test_time_config_merges_into_source(
        self, manager: SimulationManager, source_id: str
    ) -> None:
        """``time_config`` wird gemerged, nicht ersetzt."""
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"time_config": {"rounds": 9}}
        )
        time_config = branch_config(manager, branch.simulation_id)["time_config"]
        assert time_config["rounds"] == 9
        assert time_config["round_minutes"] == 60

    def test_enable_twitter(self, manager: SimulationManager, source_id: str) -> None:
        """Override dreht den Source-Wert um (Source: ``False``)."""
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"enable_twitter": True}
        )
        assert branch.enable_twitter is True
        assert branch_config(manager, branch.simulation_id)["enable_twitter"] is True

    def test_enable_reddit(self, manager: SimulationManager, source_id: str) -> None:
        """Override dreht den Source-Wert um (Source: ``True``)."""
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"enable_reddit": False}
        )
        assert branch.enable_reddit is False
        assert branch_config(manager, branch.simulation_id)["enable_reddit"] is False

    def test_platform_flags_are_inherited_without_override(
        self, manager: SimulationManager, source_id: str
    ) -> None:
        """Abgrenzung: ohne Override erbt der Branch beide Flags vom Source.

        Zusammen mit den beiden Tests darüber ist damit jede Richtung abgedeckt
        — Erben und Umdrehen —, sodass weder ein ignorierter Override noch ein
        fälschlich hartkodierter Wert durchrutscht.
        """
        branch = branching_service.create_branch(manager, source_id, "b")
        config = branch_config(manager, branch.simulation_id)
        assert branch.enable_twitter is SOURCE_ENABLE_TWITTER
        assert branch.enable_reddit is SOURCE_ENABLE_REDDIT
        assert config["enable_twitter"] is SOURCE_ENABLE_TWITTER
        assert config["enable_reddit"] is SOURCE_ENABLE_REDDIT

    def test_persona_removals(self, manager: SimulationManager, source_id: str) -> None:
        manager._store.write_json(
            source_id, "reddit_profiles", [{"username": "alice"}, {"username": "bob"}]
        )
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"persona_removals": ["bob"]}
        )
        profiles = manager._store.read_json(branch.simulation_id, "reddit_profiles", default=[])
        assert [p["username"] for p in profiles] == ["alice"]

    def test_persona_additions(self, manager: SimulationManager, source_id: str) -> None:
        manager._store.write_json(source_id, "reddit_profiles", [{"username": "alice"}])
        branch = branching_service.create_branch(
            manager,
            source_id,
            "b",
            overrides={"persona_additions": [{"platform": "reddit", "username": "carol"}]},
        )
        profiles = manager._store.read_json(branch.simulation_id, "reddit_profiles", default=[])
        assert [p["username"] for p in profiles] == ["alice", "carol"]

    def test_ai_model_ref(self, manager: SimulationManager, source_id: str) -> None:
        """Issue #886: die kanonische Referenz landet vollständig in der Config
        UND setzt das Legacy-Anzeigefeld ``llm_model`` auf ihre ``model_id``."""
        ref = {
            "provider_connection_id": "conn-branch",
            "model_id": "branch-model",
            "source": "explicit",
        }
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"ai_model_ref": ref}
        )
        config = branch_config(manager, branch.simulation_id)
        assert config["ai_model_ref"]["provider_connection_id"] == "conn-branch"
        assert config["ai_model_ref"]["model_id"] == "branch-model"
        assert config["llm_model"] == "branch-model"

    def test_ai_model_ref_overrides_a_stray_llm_model_key(
        self, manager: SimulationManager, source_id: str
    ) -> None:
        """Werden beide Keys gleichzeitig an ``create_branch`` durchgereicht
        (die API-Schicht lehnt das per Contract ab, ein Direktaufruf nicht),
        gewinnt die kanonische Referenz — die Config bleibt intern konsistent
        statt zwei widersprüchliche Modellangaben zu tragen."""
        ref = {"provider_connection_id": "conn-branch", "model_id": "branch-model"}
        branch = branching_service.create_branch(
            manager,
            source_id,
            "b",
            overrides={"llm_model": "stray-string", "ai_model_ref": ref},
        )
        config = branch_config(manager, branch.simulation_id)
        assert config["llm_model"] == "branch-model"

    def test_legacy_llm_model_clears_inherited_ai_model_ref(
        self, manager: SimulationManager, source_id: str
    ) -> None:
        """Codex-Fund PR #1560: trägt die Quelle schon eine ``ai_model_ref``,
        darf ein reiner ``llm_model``-Override sie nicht stehen lassen — sonst
        gewinnt zur Laufzeit die geerbte Referenz und der Override wirkt nicht."""
        source_config = branch_config(manager, source_id)
        source_config["ai_model_ref"] = {
            "provider_connection_id": "conn-source",
            "model_id": "source-model",
        }
        manager._store.write_json(source_id, "simulation_config", source_config)
        branch = branching_service.create_branch(
            manager, source_id, "b", overrides={"llm_model": "legacy-model"}
        )
        config = branch_config(manager, branch.simulation_id)
        assert config["llm_model"] == "legacy-model"
        assert "ai_model_ref" not in config

    def test_source_stays_untouched(self, manager: SimulationManager, source_id: str) -> None:
        """Overrides wirken auf den Branch, nie zurück auf die Quelle."""
        branching_service.create_branch(
            manager, source_id, "b", overrides={"llm_model": "branch-model", "max_agents": 42}
        )
        source_config = branch_config(manager, source_id)
        assert source_config["llm_model"] == "source-model"
        assert source_config["max_agents"] == 10


# ---------------------------------------------------------------------------
# 3. Ablehnungspfad
# ---------------------------------------------------------------------------


class TestUnknownOverrideIsRejected:
    @pytest.mark.parametrize(
        "unknown_key",
        [
            # llm_profile_id/model_id: verworfene Alternativkandidaten aus #886
            # (die Entscheidung fiel auf ai_model_ref, siehe TestOverrideTakesEffect).
            "llm_profile_id",
            "model_id",
            "totally_made_up",
        ],
    )
    def test_raises_value_error(
        self, manager: SimulationManager, source_id: str, unknown_key: str
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported branch overrides"):
            branching_service.create_branch(
                manager, source_id, "b", overrides={unknown_key: "x"}
            )

    def test_error_lists_every_unknown_key_sorted(
        self, manager: SimulationManager, source_id: str
    ) -> None:
        with pytest.raises(ValueError) as excinfo:
            branching_service.create_branch(
                manager,
                source_id,
                "b",
                overrides={"zeta": 1, "alpha": 2, "llm_model": "ok"},
            )
        assert str(excinfo.value) == "Unsupported branch overrides: alpha, zeta"

    def test_rejects_before_touching_the_source(
        self, manager: SimulationManager, source_id: str
    ) -> None:
        """Der Guard greift vor jeder Seiteneffekt-Operation — kein Branch entsteht."""
        before = len(manager.list_simulations(project_id="proj-887"))
        with pytest.raises(ValueError):
            branching_service.create_branch(
                manager, source_id, "b", overrides={"nope": 1}
            )
        assert len(manager.list_simulations(project_id="proj-887")) == before


def test_unknown_override_surfaces_as_http_400(monkeypatch, tmp_path) -> None:
    """End-to-End über ``handle_api_errors``: ValueError → HTTP 400.

    Der Whitelist-Guard läuft vor dem Existenz-Check der Simulation, deshalb
    genügt eine gültig formatierte ID ohne echten Datensatz. Seit #886
    validiert die Route ``overrides`` zuerst gegen den ``BranchOverrides``-
    Contract (unbekannte Top-Level-Keys fallen dort schon raus, nicht erst
    in ``branching_service.create_branch``) — der Testkey darf deshalb kein
    gültiges Contract-Feld sein.
    """
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations")
    )
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")

    response = app.test_client().post(
        "/api/simulation/sim_0123456789ab/branch",
        json={"branch_name": "b", "overrides": {"totally_made_up": "x"}},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "overrides ist ungültig" in str(payload)
