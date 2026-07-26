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

1. **Routing** — ``llm_profile_id`` wird aufgelöst; Request-Profil schlägt
   Projekt-Profil, eine explizite Modellwahl schlägt beide.
2. **Re-Prepare-Semantik** — der "bereits vorbereitet"-Kurzschluss hängt an der
   *expliziten* Client-Wahl, nicht mehr an ``llm_model_override``. Sonst würde
   er für jedes Projekt mit hinterlegtem Profil nie mehr greifen und jedes
   Betreten von Step 2 eine volle Neu-Vorbereitung auslösen.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.llm_routing_contract import ResolvedRoute

VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client(monkeypatch):
    # @require_scope greift, sobald AGORA_AUTH_TOKEN gesetzt ist — die Variable
    # leakt aus Nachbar-Suites in den Gesamtlauf. Open-Mode erzwingen (Muster aus
    # tests/api/test_simulation_endpoints.py); diese Suite prüft Routing, nicht Auth.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
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

    Liefert ein Dict mit ``resolved`` (das ``llm_model``, mit dem der Endpoint in
    ``seed_run_stage_routing`` geht — also das Ergebnis der Profil-Auflösung) und
    ``prepared_checked`` (ob der "bereits vorbereitet"-Kurzschluss lief).

    Bewusst wird ``seed_run_stage_routing`` abgegriffen statt
    ``prepare_simulation``: dort steht ``llm_model_override`` vor der
    Router-Auflösung, die es im Test-Fixture ohnehin überschreibt.
    """
    observed: dict = {"resolved": None, "prepared_checked": False}

    project = SimpleNamespace(
        simulation_requirement="Discuss the project",
        llm_profile_id=None,
    )
    state = SimpleNamespace(
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

    def capture_seed(_run_id, _stage, *, llm_model_override=None, llm_runtime=None):
        observed["resolved"] = llm_model_override

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
    monkeypatch.setattr("app.jobs.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)

    return SimpleNamespace(observed=observed, project=project, monkeypatch=monkeypatch)


def _stub_profile(prepare_env, profile_id: str, model_name: str) -> None:
    """Lässt ``expand_profile_in_data`` genau ein Profil auflösen."""
    profile = SimpleNamespace(
        model_name=model_name,
        provider="openai",
        api_key=None,
        base_url=None,
    )
    store = MagicMock()
    store.get.side_effect = lambda pid, **_kw: profile if pid == profile_id else None
    prepare_env.monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profiles_store", lambda: store
    )


def _post(client, **payload):
    body = {"simulation_id": VALID_SIM_ID}
    body.update(payload)
    return client.post("/api/simulation/prepare", json=body)


# ---------------------------------------------------------------------------
# 1. Routing
# ---------------------------------------------------------------------------


def test_request_profile_is_resolved_to_its_model(client, prepare_env):
    """Der Kern des Defekts: ``llm_profile_id`` allein muss routen.

    Vor #888 blieb ``llm_model`` hier leer und die Vorbereitung lief auf dem
    Server-Default-Modell.
    """
    _stub_profile(prepare_env, "prof-abc", "claude-sonnet-5")

    response = _post(client, llm_profile_id="prof-abc")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["resolved"] == "claude-sonnet-5"


def test_project_profile_is_resolved_when_request_sends_none(client, prepare_env):
    """P5.3-Fallback bleibt erhalten: Projekt-Profil greift ohne Request-Profil."""
    prepare_env.project.llm_profile_id = "prof-project"
    _stub_profile(prepare_env, "prof-project", "gemini-2.5-flash")

    response = _post(client)

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["resolved"] == "gemini-2.5-flash"


def test_request_profile_beats_project_profile(client, prepare_env):
    """Single-Run-Override: das Request-Profil schlägt den Projekt-Default."""
    prepare_env.project.llm_profile_id = "prof-project"
    _stub_profile(prepare_env, "prof-request", "claude-sonnet-5")

    response = _post(client, llm_profile_id="prof-request")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["resolved"] == "claude-sonnet-5"


def test_explicit_model_beats_every_profile(client, prepare_env):
    """Explizite Modellwahl schlägt Request- und Projekt-Profil."""
    prepare_env.project.llm_profile_id = "prof-project"
    _stub_profile(prepare_env, "prof-request", "claude-sonnet-5")

    response = _post(client, llm_profile_id="prof-request", llm_model="gpt-4o-mini")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["resolved"] == "gpt-4o-mini"


def test_default_placeholder_does_not_count_as_explicit_choice(client, prepare_env):
    """``llm_model="default"`` ist die UI-Platzhalterwahl, keine Modellwahl."""
    _stub_profile(prepare_env, "prof-abc", "claude-sonnet-5")

    response = _post(client, llm_profile_id="prof-abc", llm_model="default")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["resolved"] == "claude-sonnet-5"


def test_unresolvable_profile_does_not_break_the_request(client, prepare_env):
    """Unbekanntes Profil: ``expand_profile_in_data`` ist ein No-op, kein 500.

    Der ``profile:``-Token bleibt dann als ``llm_model`` stehen — bewusst
    unverändertes Bestandsverhalten des Resolvers, hier nur festgehalten.
    """
    _stub_profile(prepare_env, "prof-known", "claude-sonnet-5")

    response = _post(client, llm_profile_id="prof-missing")

    assert response.status_code == 200, response.get_json()
    assert prepare_env.observed["resolved"] == "profile:prof-missing"


# ---------------------------------------------------------------------------
# 2. Re-Prepare-Semantik
# ---------------------------------------------------------------------------


class TestAlreadyPreparedShortCircuit:
    """Der Kurzschluss hängt an der expliziten Client-Wahl, nicht am Profil."""

    def test_profile_derived_model_still_checks_prepared_state(self, client, prepare_env):
        """Regressionsbremse: sonst kostet jedes Betreten von Step 2 einen vollen Lauf."""
        prepare_env.project.llm_profile_id = "prof-project"
        _stub_profile(prepare_env, "prof-project", "gemini-2.5-flash")

        response = _post(client)

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is True

    def test_request_profile_still_checks_prepared_state(self, client, prepare_env):
        _stub_profile(prepare_env, "prof-abc", "claude-sonnet-5")

        response = _post(client, llm_profile_id="prof-abc")

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is True

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

    def test_profile_derived_provider_block_is_not_an_override(self, client, prepare_env):
        """Abgrenzung zum Test darüber: der Provider-Block aus dem Profil zählt nicht.

        ``expand_profile_in_data`` schreibt Provider/Key/Base-URL aus dem Profil in
        ``data['llm_provider']``. Ohne die Unterscheidung "kam vom Client" wäre das
        von einem echten Override ununterscheidbar und der Kurzschluss tot.
        """
        prepare_env.project.llm_profile_id = "prof-project"
        _stub_profile(prepare_env, "prof-project", "gemini-2.5-flash")

        response = _post(client)

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is True

    def test_force_regenerate_skips_prepared_check(self, client, prepare_env):
        prepare_env.project.llm_profile_id = "prof-project"
        _stub_profile(prepare_env, "prof-project", "gemini-2.5-flash")

        response = _post(client, force_regenerate=True)

        assert response.status_code == 200, response.get_json()
        assert prepare_env.observed["prepared_checked"] is False

    def test_already_prepared_returns_short_circuit_envelope(
        self, client, prepare_env, monkeypatch
    ):
        """Ist die Sim vorbereitet, antwortet der Endpoint ohne neuen Lauf."""
        prepare_env.project.llm_profile_id = "prof-project"
        _stub_profile(prepare_env, "prof-project", "gemini-2.5-flash")
        monkeypatch.setattr(
            "app.api.simulation_prepare._check_simulation_prepared",
            lambda _sim_id: (True, {"profiles": 12}),
        )

        response = _post(client)

        assert response.status_code == 200, response.get_json()
        payload = response.get_json()["data"]
        assert payload["already_prepared"] is True
        assert prepare_env.observed["resolved"] is None
