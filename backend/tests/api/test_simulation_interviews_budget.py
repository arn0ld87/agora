"""Interviews aus der Oberflaeche laufen durchs Run-Budget der Simulation (#1805).

Variante A: ein UI-Interview wird dem ``simulation_run``-Job der Simulation
zugerechnet. Der API-Layer loest die ``run_id`` ueber ``linked_ids.simulation_id``
auf und reicht sie an Runner/Client/Direktpfad durch. Ein erreichtes hartes
Budget kommt als HTTP 409 ``budget_exceeded`` an, nie als ``success: true``.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services.run_budget import BudgetExceededError
from app.services.run_registry import RunRegistry
from app.services.sim import interview_client, interview_direct
from app.services.simulation_runner import SimulationRunner

SIM_ID = "sim_0123456789ab"

PROFILES: List[Dict[str, Any]] = [
    {
        "user_id": 1,
        "username": "lena_k",
        "name": "Lena Krüger",
        "bio": "Product Ownerin in einem mittelständischen SaaS-Team",
        "persona": "Skeptisch gegenüber neuen Tools.",
        "age": 38,
        "country": "DE",
        "profession": "Product Ownerin",
        "interested_topics": ["SaaS"],
    },
]
SIM_CONFIG: Dict[str, Any] = {
    "simulation_id": SIM_ID,
    "simulation_requirement": "Wie lässt sich das Onboarding verbessern?",
    "language": "de",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


@pytest.fixture(autouse=True)
def _backend_available(monkeypatch):
    """Direktpfad ist verfuegbar (geschlossene Umgebung, Personas persistiert)."""
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.direct_interviews_available",
        staticmethod(lambda _sid: True),
    )


def _create_simulation_run() -> str:
    run = RunRegistry().create_run(
        "simulation_run", SIM_ID, linked_ids={"simulation_id": SIM_ID}
    )
    return run["run_id"]


def _capture(monkeypatch, method: str) -> Dict[str, Any]:
    captured: Dict[str, Any] = {}

    def _fake(**kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return {"success": True, "result": {"results": {}}}

    monkeypatch.setattr(
        f"app.api.simulation_interviews.SimulationRunner.{method}",
        staticmethod(_fake),
    )
    return captured


def _post(client, endpoint: str):
    bodies = {
        "": {"simulation_id": SIM_ID, "agent_id": 1, "prompt": "Was meinst du?"},
        "/batch": {
            "simulation_id": SIM_ID,
            "interviews": [{"agent_id": 1, "prompt": "Was meinst du?"}],
        },
        "/all": {"simulation_id": SIM_ID, "prompt": "Was meinst du?"},
    }
    return client.post(f"/api/simulation/interview{endpoint}", json=bodies[endpoint])


ENDPOINTS = [
    ("", "interview_agent"),
    ("/batch", "interview_agents_batch"),
    ("/all", "interview_all_agents"),
]


# ---------------------------------------------------------------------------
# 1. Aufloesung und Durchreichung der run_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("endpoint", "method"), ENDPOINTS)
def test_run_id_of_simulation_run_is_passed_to_runner(client, monkeypatch, endpoint, method):
    run_id = _create_simulation_run()
    captured = _capture(monkeypatch, method)

    response = _post(client, endpoint)

    assert response.status_code == 200
    assert captured["run_id"] == run_id


@pytest.mark.parametrize(("endpoint", "method"), ENDPOINTS)
def test_other_run_types_of_the_simulation_are_not_resolved(
    client, monkeypatch, endpoint, method
):
    """Nur der ``simulation_run``-Job traegt das Budget — kein Report-Run."""
    RunRegistry().create_run(
        "report_generate", SIM_ID, linked_ids={"simulation_id": SIM_ID}
    )
    captured = _capture(monkeypatch, method)

    response = _post(client, endpoint)

    assert response.status_code == 200
    assert captured["run_id"] is None


# ---------------------------------------------------------------------------
# 2. Altbestand ohne Job: unbudgetiert wie bisher, aber sichtbar protokolliert
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("endpoint", "method"), ENDPOINTS)
def test_without_simulation_run_interview_stays_unbudgeted_with_warning(
    client, monkeypatch, endpoint, method
):
    captured = _capture(monkeypatch, method)
    fake_logger = MagicMock()
    monkeypatch.setattr("app.api.simulation_interviews.logger", fake_logger)

    response = _post(client, endpoint)

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert captured["run_id"] is None
    fake_logger.warning.assert_called_once()
    message = fake_logger.warning.call_args.args[0]
    assert "interview_unbudgeted" in message
    assert fake_logger.warning.call_args.args[1] == SIM_ID


# ---------------------------------------------------------------------------
# 3. Budgetabbruch: harter, strukturierter Fehler (HTTP 409)
# ---------------------------------------------------------------------------


def _raise_budget(**_kwargs: Any) -> Dict[str, Any]:
    raise BudgetExceededError("tokens", 21_000_000, 20_000_000)


def _assert_budget_exceeded_envelope(response) -> None:
    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "budget_exceeded"
    assert payload["error"]
    assert payload["termination_reason"] == "budget_tokens"
    assert payload["dimension"] == "tokens"
    assert payload["observed"] == 21_000_000
    assert payload["threshold"] == 20_000_000
    # Keine Antwort-Daten, kein Fallback-Text.
    assert "data" not in payload


@pytest.mark.parametrize(("endpoint", "method"), ENDPOINTS)
def test_budget_exceeded_is_409_with_code(client, monkeypatch, endpoint, method):
    _create_simulation_run()
    monkeypatch.setattr(
        f"app.api.simulation_interviews.SimulationRunner.{method}",
        staticmethod(_raise_budget),
    )

    _assert_budget_exceeded_envelope(_post(client, endpoint))


class _FakeLLMClient:
    """Zeichnet die Konstruktor-Kwargs auf; ``chat`` antwortet oder bricht ab."""

    instances: List["_FakeLLMClient"] = []
    raise_budget = False

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.run_id = kwargs.get("run_id")
        type(self).instances.append(self)

    def chat(self, messages, **kwargs):
        if type(self).raise_budget:
            raise BudgetExceededError("tokens", 21_000_000, 20_000_000)
        return "Ich sehe das kritisch."


def _store_mock() -> MagicMock:
    store = MagicMock()

    def read_json(simulation_id, name, default=None):
        if name == "reddit_profiles":
            return PROFILES
        if name == "simulation_config":
            return SIM_CONFIG
        return default

    store.read_json.side_effect = read_json
    store.exists.side_effect = lambda simulation_id, name: name in (
        "reddit_profiles",
        "simulation_config",
    )
    return store


@pytest.fixture
def direct_path(monkeypatch, tmp_path):
    """Echter Runner/Client/Direktpfad, nur LLM-Client und Artefaktspeicher gedoubelt."""
    (tmp_path / SIM_ID).mkdir()
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    _FakeLLMClient.instances = []
    _FakeLLMClient.raise_budget = False
    monkeypatch.setattr("app.llm.client.LLMClient", _FakeLLMClient)
    with patch.object(interview_direct, "_store", return_value=_store_mock()):
        yield _FakeLLMClient


def test_direct_path_builds_llm_client_with_resolved_run_id_for_single(client, direct_path):
    run_id = _create_simulation_run()

    response = _post(client, "")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert [c.run_id for c in direct_path.instances] == [run_id]


def test_direct_path_builds_llm_client_with_resolved_run_id_for_batch(client, direct_path):
    run_id = _create_simulation_run()

    response = _post(client, "/batch")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert [c.run_id for c in direct_path.instances] == [run_id]


def test_direct_path_without_job_builds_client_without_run_id(client, direct_path):
    response = _post(client, "")

    assert response.status_code == 200
    assert [c.kwargs.get("run_id") for c in direct_path.instances] == [None]


def test_direct_path_budget_exceeded_single_is_409(client, direct_path):
    _create_simulation_run()
    direct_path.raise_budget = True

    _assert_budget_exceeded_envelope(_post(client, ""))


def test_direct_path_budget_exceeded_batch_is_409(client, direct_path):
    _create_simulation_run()
    direct_path.raise_budget = True

    _assert_budget_exceeded_envelope(_post(client, "/batch"))


# ---------------------------------------------------------------------------
# 4. interview_all_agents reicht run_id durch Runner und Client bis zum Batch
# ---------------------------------------------------------------------------


def test_runner_interview_all_agents_forwards_run_id(monkeypatch):
    captured: Dict[str, Any] = {}

    def _fake(simulation_id, prompt, platform, timeout, **kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr("app.services.simulation_runner._interview_all_agents_fn", _fake)

    SimulationRunner.interview_all_agents(
        simulation_id=SIM_ID, prompt="x", run_id="run-all-1"
    )

    assert captured["run_id"] == "run-all-1"


def test_client_interview_all_agents_forwards_run_id_to_batch(monkeypatch, tmp_path):
    (tmp_path / SIM_ID).mkdir()
    monkeypatch.setattr(interview_client, "_store", lambda: _store_mock_with_agents())
    monkeypatch.setattr(interview_client, "load_simulation_profiles", lambda _d: PROFILES)
    monkeypatch.setattr(
        interview_client,
        "align_config_to_profiles",
        lambda config, _profiles: (config, []),
    )
    captured: Dict[str, Any] = {}

    def _fake_batch(**kwargs: Any) -> Dict[str, Any]:
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(interview_client, "interview_agents_batch", _fake_batch)

    interview_client.interview_all_agents(
        SIM_ID, "x", run_state_dir=str(tmp_path), run_id="run-all-2"
    )

    assert captured["run_id"] == "run-all-2"
    assert captured["interviews"] == [{"agent_id": 1, "prompt": "x"}]


def _store_mock_with_agents() -> MagicMock:
    store = MagicMock()
    store.exists.return_value = True
    store.read_json.return_value = {**SIM_CONFIG, "agent_configs": [{"agent_id": 1}]}
    return store
