"""Profil-Routing in ``POST /api/simulation/prepare`` (Issue #888).

Vorher las ``simulation_prepare.py`` ``llm_profile_id`` nur als
Fallback-*Unterdrücker*: ein mitgeschicktes Profil übersprang den
P5.3-Projekt-Fallback, löste aber selbst nichts auf — ``expand_profile_in_data``
reagiert ausschließlich auf ein ``llm_model`` mit ``profile:``-Präfix. Damit
kehrte das Feld seine eigene Absicht um; der Standardfall (Projekt hat ein
Profil, User lässt die Modellauswahl auf "default", das Frontend sendet
``llm_profile_id`` mit und ``llm_model`` gar nicht) landete still im
Server-Default-Modell.

Diese Suite pinnt beide Hälften der Korrektur:

1. **Routing über den kanonischen Pfad** — die Profil-ID wird an
   ``seed_run_stage_routing(llm_profile_id=...)`` durchgereicht, nicht lokal zu
   ``llm_model`` expandiert. Nur dessen Profil-Branch löst die aktivierte
   ``ProviderConnection`` auf und koppelt sie an deren gebundenes Secret
   (SSoT, Issue #817). Eine lokale Expansion würde Endpoint und Key aus dem
   Legacy-Profil einbrennen und nach einer Rotation auf veraltete Credentials
   zeigen. Präzedenz: explizites Modell → Request-Profil → Projekt-Profil.
2. **Re-Prepare-Semantik** — der "bereits vorbereitet"-Kurzschluss hängt an der
   *expliziten* Client-Wahl, nicht an ``llm_model_override``. Sonst würde er für
   jedes Projekt mit hinterlegtem Profil nie mehr greifen und jedes Betreten von
   Step 2 eine volle Neu-Vorbereitung auslösen. Ein Request-Profil, das vom
   Projekt-Default *abweicht*, zählt dabei sehr wohl als explizite Wahl.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.simulation_manager import SimulationStatus

VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client(monkeypatch):
    # AGORA_AUTH_TOKEN steht via load_dotenv() in app/config.py prozessweit in
    # os.environ; sobald irgendein Test create_app() ruft, hängt der
    # Blueprint-Guard dauerhaft an simulation_bp und diese Suite bekäme 401.
    # Open-Mode erzwingen (Muster aus tests/api/test_simulation_endpoints.py) —
    # hier geht es um Routing, nicht um Auth.
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "")
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 1000
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


@pytest.fixture
def prepare_env(monkeypatch):
    """Verdrahtet ``/prepare`` so, dass nur das Modell-Routing beobachtet wird.

    ``observed`` hält fest, womit der Endpoint in ``seed_run_stage_routing`` geht:
    ``profile`` (die durchgereichte ``llm_profile_id``), ``model``
    (``llm_model_override``) und ``prepared_checked`` (ob der "bereits
    vorbereitet"-Kurzschluss lief).

    ``seed_run_stage_routing`` wird abgegriffen statt ``prepare_simulation``: dort
    steht das Routing-Argument vor der Router-Auflösung, die es im Test-Fixture
    ohnehin überschreibt. Der Profil-Branch selbst ist in
    ``tests/services/test_llm_routing_seed.py`` abgedeckt.
    """
    observed: dict = {"profile": None, "model": None, "prepared_checked": False}

    project = SimpleNamespace(
        simulation_requirement="Discuss the project",
        llm_profile_id=None,
    )
    state = SimpleNamespace(
        status=SimulationStatus.CREATED,
        project_id="proj_123",
        graph_id="graph_123",
        source_simulation_id=None,
        root_simulation_id=None,
        branch_name=None,
        branch_depth=0,
        entities_count=1,
        entity_types=["Person"],
    )

    manager = MagicMock()
    manager.get_simulation.return_value = state
    manager.prepare_simulation.side_effect = lambda **_kwargs: MagicMock(
        to_simple_dict=lambda: {"simulation_id": VALID_SIM_ID, "status": "ready"}
    )

    filtered = MagicMock()
    filtered.filtered_count = 1
    filtered.entity_types = {"Person"}

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

    def capture_seed(_run_id, _stage, *, llm_model_override=None, llm_runtime=None,
                     llm_profile_id=None):
        observed["model"] = llm_model_override
        observed["profile"] = llm_profile_id

    def capture_prepared_check(_simulation_id):
        observed["prepared_checked"] = True
        return False, {}

    def run_inline(self):
        self.run()

    prefix = "app.api.simulation_prepare"
    monkeypatch.setattr(f"{prefix}.SimulationManager", lambda: manager)
    monkeypatch.setattr(f"{prefix}.ProjectManager.get_project", lambda _pid: project)
    monkeypatch.setattr(f"{prefix}.ProjectManager.get_extracted_text", lambda _pid: "document text")
    monkeypatch.setattr(f"{prefix}.get_simulation_storage", lambda: MagicMock())
    monkeypatch.setattr(
        f"{prefix}.EntityReader",
        lambda _storage: MagicMock(filter_defined_entities=MagicMock(return_value=filtered)),
    )
    monkeypatch.setattr(f"{prefix}.seed_run_stage_routing", capture_seed)
    monkeypatch.setattr(f"{prefix}._check_simulation_prepared", capture_prepared_check)
    monkeypatch.setattr(f"{prefix}.StageModelRouter", FakeRouter)
    monkeypatch.setattr(f"{prefix}.resolve_route_api_key", lambda *_a, **_k: "sk-route")
    monkeypatch.setattr(
        f"{prefix}.run_registry.create_run", lambda *a, **k: {"run_id": "run_prepare_1"}
    )
    monkeypatch.setattr(
        # Der RunLifecycle markiert seit #1183 jeden Fensterabbruch strikt als
        # failed (#844) — der gestubbte Run braucht deshalb auch ein
        # erfolgreiches update_run, sonst würde jeder Fehlerpfad-Test hier
        # fälschlich im 500-Persistenzfehler enden.
        f"{prefix}.run_registry.update_run", lambda *a, **k: {"run_id": "run_prepare_1"}
    )
    monkeypatch.setattr("app.jobs.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)

    return SimpleNamespace(observed=observed, project=project, monkeypatch=monkeypatch)


def _post(client, **payload):
    body = {"simulation_id": VALID_SIM_ID}
    body.update(payload)
    return client.post("/api/simulation/prepare", json=body)


# ---------------------------------------------------------------------------
# 1. Routing über den kanonischen Profil-Pfad
# ---------------------------------------------------------------------------


def test_request_profile_is_forwarded_to_the_canonical_seed_path(client, prepare_env):
    """Der Kern des Defekts: ``llm_profile_id`` allein muss routen.

    Vor #888 kam hier weder ein Modell noch eine Profil-ID an und die
    Vorbereitung lief auf dem Server-Default-Modell. Die ID geht bewusst
    *unexpandiert* durch, damit ``seed_run_stage_routing`` die ProviderConnection
    auflösen und deren Secret binden kann.
    """
    response = _post(client, llm_profile_id="prof-abc")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["profile"] == "prof-abc"
    assert prepare_env.observed["model"] is None


def test_project_profile_is_forwarded_when_request_sends_none(client, prepare_env):
    """P5.3-Fallback bleibt erhalten: Projekt-Profil greift ohne Request-Profil."""
    prepare_env.project.llm_profile_id = "prof-project"

    response = _post(client)

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["profile"] == "prof-project"


def test_request_profile_beats_project_profile(client, prepare_env):
    """Single-Run-Override: das Request-Profil schlägt den Projekt-Default."""
    prepare_env.project.llm_profile_id = "prof-project"

    response = _post(client, llm_profile_id="prof-request")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["profile"] == "prof-request"


def test_explicit_model_beats_every_profile(client, prepare_env):
    """Explizite Modellwahl schlägt Request- und Projekt-Profil.

    Dann darf auch keine Profil-ID mehr durchgereicht werden, sonst konkurrierten
    zwei Routing-Anweisungen um dieselbe Stage.
    """
    prepare_env.project.llm_profile_id = "prof-project"

    response = _post(client, llm_profile_id="prof-request", llm_model="gpt-4o-mini")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["model"] == "gpt-4o-mini"
    assert prepare_env.observed["profile"] is None


def test_default_placeholder_does_not_count_as_explicit_choice(client, prepare_env):
    """``llm_model="default"`` ist die UI-Platzhalterwahl, keine Modellwahl."""
    response = _post(client, llm_profile_id="prof-abc", llm_model="default")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["profile"] == "prof-abc"


def test_legacy_profile_token_in_llm_model_is_still_expanded(client, prepare_env):
    """Legacy-Pfad: ``llm_model="profile:<id>"`` wird weiterhin lokal expandiert.

    ``HeroNewRun.vue`` schickt Profile historisch als Pseudo-Modell im
    ``llm_model``-Feld; ``seed_run_stage_routing`` kennt nur das separate Feld.
    Ohne ``expand_profile_in_data`` ginge der Token als Modellname an den
    LLM-Client.
    """
    profile = SimpleNamespace(
        model_name="claude-sonnet-5", provider="openai", api_key=None, base_url=None
    )
    store = MagicMock()
    store.get.side_effect = lambda pid, **_kw: profile if pid == "prof-legacy" else None
    prepare_env.monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profiles_store", lambda: store
    )

    response = _post(client, llm_model="profile:prof-legacy")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["model"] == "claude-sonnet-5"


def test_unresolvable_profile_surfaces_as_http_400(client, prepare_env):
    """Unauflösbares Profil wird abgelehnt, nicht stillschweigend eingereiht.

    ``seed_run_stage_routing`` wirft für ein unbekanntes Profil bzw. eine fehlende
    aktivierte ProviderConnection ``ValueError`` (siehe
    ``services/llm_routing_seed.py``, dort auch getestet); ``@handle_api_errors``
    macht daraus HTTP 400. Vor der Umstellung auf den kanonischen Pfad lief in
    diesem Fall der literale Modellname ``profile:<id>`` in die Queue.
    """
    def raise_unknown_profile(*_args, llm_profile_id=None, **_kwargs):
        raise ValueError(f"LLM-Profil {llm_profile_id!r} nicht gefunden")

    prepare_env.monkeypatch.setattr(
        "app.api.simulation_prepare.seed_run_stage_routing", raise_unknown_profile
    )

    response = _post(client, llm_profile_id="prof-missing")

    assert response.status_code == 400, response.get_json()
    assert "nicht gefunden" in str(response.get_json())


# ---------------------------------------------------------------------------
# 2. Re-Prepare-Semantik
# ---------------------------------------------------------------------------


class TestAlreadyPreparedShortCircuit:
    """Der Kurzschluss hängt an der expliziten Client-Wahl, nicht am Profil."""

    def test_project_profile_still_checks_prepared_state(self, client, prepare_env):
        """Regressionsbremse: sonst kostet jedes Betreten von Step 2 einen vollen Lauf."""
        prepare_env.project.llm_profile_id = "prof-project"

        response = _post(client)

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is True

    def test_request_profile_equal_to_project_default_still_checks(self, client, prepare_env):
        """Dasselbe Profil erneut zu schicken bleibt der billige Revisit.

        Genau dieser Fall ist der Frontend-Alltag: ``Step2EnvSetup.vue`` sendet
        ``props.projectData.llm_profile_id`` mit, also immer den Projekt-Default.
        """
        prepare_env.project.llm_profile_id = "prof-project"

        response = _post(client, llm_profile_id="prof-project")

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is True

    def test_differing_request_profile_skips_prepared_check(self, client, prepare_env):
        """Ein abweichendes Request-Profil ist eine explizite Wahl.

        Ohne diesen Zweig käme der Endpoint mit ``already_prepared`` zurück und die
        Personas blieben die des vorherigen Modells — im Widerspruch zur Präzedenz
        "Request-Profil schlägt Projekt-Profil".
        """
        prepare_env.project.llm_profile_id = "prof-project"

        response = _post(client, llm_profile_id="prof-request")

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is False
        assert prepare_env.observed["profile"] == "prof-request"

    def test_request_profile_without_project_default_skips_prepared_check(
        self, client, prepare_env
    ):
        """Kein Projekt-Default gesetzt: jedes Request-Profil ist eine Abweichung."""
        response = _post(client, llm_profile_id="prof-request")

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is False

    def test_explicit_model_skips_prepared_check(self, client, prepare_env):
        """Unverändert: eine explizite Modellwahl erzwingt die Neu-Vorbereitung."""
        response = _post(client, llm_model="gpt-4o-mini")

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is False

    def test_explicit_runtime_provider_skips_prepared_check(self, client, prepare_env):
        """Ein echter Client-Provider-Override erzwingt weiterhin die Neu-Vorbereitung."""
        response = _post(
            client,
            llm_provider={
                "provider": "custom_openai",
                "base_url": "http://localhost:11434/v1",
                "api_key": "sk-test",
            },
        )

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is False

    def test_force_regenerate_skips_prepared_check(self, client, prepare_env):
        prepare_env.project.llm_profile_id = "prof-project"

        response = _post(client, force_regenerate=True)

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is False

    def test_already_prepared_returns_short_circuit_envelope(
        self, client, prepare_env, monkeypatch
    ):
        """Ist die Sim vorbereitet, antwortet der Endpoint ohne neuen Lauf."""
        prepare_env.project.llm_profile_id = "prof-project"
        monkeypatch.setattr(
            "app.api.simulation_prepare._check_simulation_prepared",
            lambda _sim_id: (True, {"profiles": 12}),
        )

        response = _post(client)

        assert response.status_code == 200, response.get_json()
        payload = response.get_json()["data"]
        assert payload["already_prepared"] is True
        assert prepare_env.observed["profile"] is None
