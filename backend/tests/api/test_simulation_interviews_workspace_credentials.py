"""Workspace-Credential-Pfad der Direkt-Interviews (#1805, F5).

Seit die ``run_id`` durchgereicht wird, löst ``_default_client_factory`` das
Credential über ``workspace_credential_id_for_run(run_id)`` auf. Zwei Fälle:

- Workspace-Lauf mit Credential: der Client wird mit der Verbindung des Laufs
  und dem Workspace-Schlüssel gebaut, nie mit der globalen Konfiguration.
- Workspace-Lauf ohne Credential: sauberer, strukturierter Fehler (kein 500,
  kein stiller Rückfall auf den Operator-Schlüssel).
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services.run_registry import RunRegistry
from app.services.sim import interview_direct
from app.services.simulation_runner import SimulationRunner

SIM_ID = "sim_0123456789ab"
WORKSPACE_A = UUID("11111111-1111-4111-8111-111111111111")
BASE_URL = "https://api.openai.com/v1"
MODEL = "gpt-4.1-mini"

PROFILES: List[Dict[str, Any]] = [{"user_id": 0, "name": "Agent 0", "bio": "Rolle"}]
SIM_CONFIG: Dict[str, Any] = {
    "simulation_id": SIM_ID,
    "simulation_requirement": "Wie lässt sich das Onboarding verbessern?",
    "language": "de",
    "llm_model": MODEL,
    "llm_base_url": BASE_URL,
}


class _RecordingClient:
    instances: List["_RecordingClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        type(self).instances.append(self)

    def chat(self, messages, **kwargs):
        return "Ich sehe das kritisch."


@pytest.fixture
def workspace_env(monkeypatch, tmp_path):
    """Workspace-Lauf: Credential-Auflösung, Connection-Lookup und Client gedoubelt."""
    _RecordingClient.instances = []
    monkeypatch.setattr("app.llm.client.LLMClient", _RecordingClient)
    monkeypatch.setattr(
        "app.services.llm_routing_seed.workspace_credential_id_for_run",
        lambda _run_id: WORKSPACE_A,
    )
    (tmp_path / SIM_ID).mkdir()
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    store = MagicMock()
    store.read_json.side_effect = lambda sid, name, default=None: {
        "reddit_profiles": PROFILES,
        "simulation_config": SIM_CONFIG,
    }.get(name, default)
    with patch.object(interview_direct, "_store", return_value=store):
        yield tmp_path


def _resolve(monkeypatch, result):
    seen: Dict[str, Any] = {}

    def fake(base_url, *, workspace_id):
        seen.update(base_url=base_url, workspace_id=workspace_id)
        return result

    monkeypatch.setattr("app.llm.factory.resolve_connection_for_base_url", fake)
    return seen


# ---------------------------------------------------------------------------
# Direktpfad
# ---------------------------------------------------------------------------


def test_workspace_run_with_credential_builds_client_with_run_connection(
    workspace_env, monkeypatch
):
    seen = _resolve(monkeypatch, ("workspace-key", "openai", "api_key"))

    result = interview_direct.interview_agent_direct(
        SIM_ID, 0, "Was meinst du?", run_state_dir=str(workspace_env), run_id="run-ws"
    )

    assert result["success"] is True
    assert seen == {"base_url": BASE_URL, "workspace_id": WORKSPACE_A}
    [client] = _RecordingClient.instances
    assert client.kwargs == {
        "model": MODEL,
        "base_url": BASE_URL,
        "api_key": "workspace-key",
        "route_provider_id": "openai",
        "api_key_source": "workspace_store",
        "use_active_config": False,
        "allow_api_key_fallback": False,
        "timeout": 60.0,
        "run_id": "run-ws",
    }


def test_workspace_run_without_credential_is_structured_error_not_global_fallback(
    workspace_env, monkeypatch
):
    _resolve(monkeypatch, (None, "openai", "api_key"))

    result = interview_direct.interview_agent_direct(
        SIM_ID, 0, "Was meinst du?", run_state_dir=str(workspace_env), run_id="run-ws"
    )

    assert result["success"] is False
    assert "Workspace provider credential is missing" in result["error"]
    assert result["result"]["response"] is None
    # Kein Client, weder mit dem Operator- noch mit einem anderen Schlüssel.
    assert _RecordingClient.instances == []


# ---------------------------------------------------------------------------
# Endpunkt: kein 500
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, workspace_env):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.direct_interviews_available",
        staticmethod(lambda _sid: True),
    )
    RunRegistry().create_run(
        "simulation_run", SIM_ID, linked_ids={"simulation_id": SIM_ID}
    )
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


def _post(client):
    return client.post(
        "/api/simulation/interview",
        json={"simulation_id": SIM_ID, "agent_id": 0, "prompt": "Was meinst du?"},
    )


def test_endpoint_with_workspace_credential_answers(client, monkeypatch):
    _resolve(monkeypatch, ("workspace-key", "openai", "api_key"))

    response = _post(client)

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    [instance] = _RecordingClient.instances
    assert instance.kwargs["api_key"] == "workspace-key"
    assert instance.kwargs["run_id"]


def test_endpoint_with_missing_workspace_credential_is_not_a_500(client, monkeypatch):
    _resolve(monkeypatch, (None, "openai", "api_key"))

    response = _post(client)

    # Legacy-Envelope der Interview-Endpunkte: HTTP 200, Fehler in success/error.
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is False
    assert "Workspace provider credential is missing" in payload["error"]
    assert _RecordingClient.instances == []


def test_endpoint_with_unresolvable_credential_scope_is_a_400_not_a_500(
    client, monkeypatch
):
    def _scope_error(_run_id):
        raise ValueError("Run credential scope cannot be validated")

    monkeypatch.setattr(
        "app.services.llm_routing_seed.workspace_credential_id_for_run", _scope_error
    )

    response = _post(client)

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "credential scope" in payload["error"]
    assert _RecordingClient.instances == []
