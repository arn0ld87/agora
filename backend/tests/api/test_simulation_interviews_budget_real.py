"""Interview-Endpunkte gegen den echten Budget-Enforcer und Ledger (#1805, F2/F4).

``test_simulation_interviews_budget.py`` wirft ``BudgetExceededError`` von Hand.
Hier arbeiten ``RunBudgetEnforcer``, ``RunRegistry`` und der Ledger echt; nur der
LLM-Provider ist gedoubelt. Der Test-Client fährt dasselbe Paar wie
``LLMClient._budget_check``/``_provider_attempt``: ``check_before_call`` vor dem
Aufruf, Ledger-Event nach dem Aufruf, ``record_after_call`` im ``finally``.

Direktpfad: Persona-Antworten entstehen im Flask-Prozess. Der IPC-Pfad braucht
einen lebenden OASIS-Worker und wird hier nicht gefahren; sein Vorab-Guard
(``_report_budget_guard``) hat unten einen eigenen Test mit echtem Enforcer.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.interview_budget_exceeded_contract import (
    InterviewBudgetExceededResponse,
)
from app.services.run_budget import BudgetExceededError, RunBudgetEnforcer, load_warnings
from app.services.run_registry import RunRegistry
from app.services.run_usage_ledger import reset_usage_cache
from app.services.sim import interview_client, interview_direct
from app.services.simulation_runner import SimulationRunner

SIM_ID = "sim_0123456789ab"

PROFILES: List[Dict[str, Any]] = [
    {"user_id": i, "username": f"agent_{i}", "name": f"Agent {i}", "bio": "Rolle"}
    for i in range(3)
]
SIM_CONFIG: Dict[str, Any] = {
    "simulation_id": SIM_ID,
    "simulation_requirement": "Wie lässt sich das Onboarding verbessern?",
    "language": "de",
}

_ledger_lock = threading.Lock()


class _LedgerLLMClient:
    """LLM-Client-Double, das den echten Enforcer wie ``LLMClient`` bedient."""

    run_dirs: Path

    def __init__(self, **kwargs: Any) -> None:
        self.run_id = kwargs.get("run_id")

    def chat(self, messages, **kwargs):
        enforcer = RunBudgetEnforcer.for_run(self.run_id) if self.run_id else None
        if enforcer is not None:
            enforcer.check_before_call()
        try:
            if self.run_id:
                _append_event(type(self).run_dirs, self.run_id, prompt_tokens=600)
            return "Ich sehe das kritisch."
        finally:
            if enforcer is not None:
                enforcer.record_after_call()


def _append_event(run_dirs: Path, run_id: str, *, prompt_tokens: int) -> None:
    event = {
        "stage": "interview",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "base_url_sanitized": "https://api.openai.com",
        "timestamp": 1_700_000_000.0,
        "latency_ms": 10.0,
        "success": True,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": 500,
    }
    with _ledger_lock:
        run_dir = run_dirs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "llm_call_events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        reset_usage_cache()


def _create_job(budget: Dict[str, Any] | None) -> str:
    run = RunRegistry().create_run(
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
        metadata={"budget": budget} if budget else {},
    )
    return run["run_id"]


def _store_mock() -> MagicMock:
    store = MagicMock()

    def read_json(simulation_id, name, default=None):
        if name == "reddit_profiles":
            return PROFILES
        if name == "simulation_config":
            return SIM_CONFIG
        return default

    store.read_json.side_effect = read_json
    return store


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


@pytest.fixture
def run_dirs(tmp_path, monkeypatch) -> Path:
    """Ledger-Verzeichnis isolieren; Direktpfad ohne lebenden Worker."""
    dirs = tmp_path / "runs"
    dirs.mkdir()
    for target in (
        "app.services.run_budget.ArtifactLocator.run_dir",
        "app.services.run_usage_ledger.ArtifactLocator.run_dir",
    ):
        monkeypatch.setattr(target, staticmethod(lambda run_id: str(dirs / run_id)))
    reset_usage_cache()

    state_dir = tmp_path / "sim_state"
    (state_dir / SIM_ID).mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(state_dir))
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.direct_interviews_available",
        staticmethod(lambda _sid: True),
    )
    _LedgerLLMClient.run_dirs = dirs
    monkeypatch.setattr("app.llm.client.LLMClient", _LedgerLLMClient)
    with patch.object(interview_direct, "_store", return_value=_store_mock()):
        yield dirs
    reset_usage_cache()


def _post_single(client):
    return client.post(
        "/api/simulation/interview",
        json={"simulation_id": SIM_ID, "agent_id": 0, "prompt": "Was meinst du?"},
    )


def _post_batch(client, agents: int = 3):
    return client.post(
        "/api/simulation/interview/batch",
        json={
            "simulation_id": SIM_ID,
            "interviews": [
                {"agent_id": i, "prompt": "Was meinst du?"} for i in range(agents)
            ],
        },
    )


def _history_count(client) -> int:
    response = client.post(
        "/api/simulation/interview/history", json={"simulation_id": SIM_ID}
    )
    assert response.status_code == 200
    return response.get_json()["data"]["count"]


def _assert_contract_body(payload: Dict[str, Any]) -> InterviewBudgetExceededResponse:
    """Body ist exakt der Vertrag: ``extra="forbid"`` fängt jedes Zusatzfeld."""
    assert payload["success"] is False
    assert payload["code"] == "budget_exceeded"
    assert "data" not in payload
    return InterviewBudgetExceededResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# F2: echter Enforcer, harte Limits erschoepft -> 409 budget_exceeded
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("post", [_post_single, _post_batch], ids=["single", "batch"])
def test_exhausted_hard_call_limit_is_409(client, run_dirs, post):
    run_id = _create_job({"max_llm_calls": 2, "enforcement": "hard"})
    _append_event(run_dirs, run_id, prompt_tokens=10)
    _append_event(run_dirs, run_id, prompt_tokens=10)

    response = post(client)

    assert response.status_code == 409
    body = _assert_contract_body(response.get_json())
    assert body.dimension == "calls"
    assert body.termination_reason == "budget_calls"
    assert (body.observed, body.threshold) == (2, 2)
    assert body.persisted_count == 0
    assert _history_count(client) == 0
    # Die harte Warnung steht im Manifest des Simulationsjobs.
    assert [(w.dimension, w.severity) for w in load_warnings(run_id)] == [("calls", "hard")]


@pytest.mark.parametrize("post", [_post_single, _post_batch], ids=["single", "batch"])
def test_exhausted_hard_token_limit_is_409(client, run_dirs, post):
    run_id = _create_job({"max_tokens": 1000, "enforcement": "hard"})
    _append_event(run_dirs, run_id, prompt_tokens=600)  # 600 + 500 = 1100 Tokens

    response = post(client)

    assert response.status_code == 409
    body = _assert_contract_body(response.get_json())
    assert body.dimension == "tokens"
    assert body.termination_reason == "budget_tokens"
    assert (body.observed, body.threshold) == (1100, 1000)
    assert body.persisted_count == 0
    assert _history_count(client) == 0


def test_within_budget_interview_runs_and_is_booked(client, run_dirs):
    run_id = _create_job({"max_llm_calls": 5, "enforcement": "hard"})

    response = _post_single(client)

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    enforcer = RunBudgetEnforcer.for_run(run_id)
    assert enforcer is not None
    assert enforcer.consumed().llm_calls == 1
    assert _history_count(client) == 1


def test_job_without_budget_config_runs_and_logs_structured_warning(
    client, run_dirs, monkeypatch
):
    """Kein Budget am Job: Interview läuft, die Lücke ist sichtbar (F3)."""
    run_id = _create_job(None)
    fake_logger = MagicMock()
    monkeypatch.setattr("app.api.simulation_interviews.logger", fake_logger)

    response = _post_single(client)

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert RunBudgetEnforcer.for_run(run_id) is None
    fake_logger.warning.assert_called_once()
    call = fake_logger.warning.call_args
    assert "interview_unbudgeted" in call.args[0]
    assert "reason=no_budget_config" in call.args[0]
    assert call.args[1:] == (SIM_ID, run_id)
    assert _history_count(client) == 1


# ---------------------------------------------------------------------------
# F4: Teilpersistenz im Direkt-Batch ist sichtbar (persisted_count)
# ---------------------------------------------------------------------------


def test_batch_budget_hit_after_first_call_reports_persisted_answer(client, run_dirs):
    """Drei Agenten, das Budget reicht fuer genau einen Aufruf.

    Die Antwort des einen Agenten ist gespeichert und verbucht; die 409-Antwort
    enthaelt keine Teilantworten, nennt aber ``persisted_count == 1``.
    """
    run_id = _create_job({"max_llm_calls": 1, "enforcement": "hard"})

    response = _post_batch(client, agents=3)

    assert response.status_code == 409
    body = _assert_contract_body(response.get_json())
    assert body.dimension == "calls"
    assert body.persisted_count == 1
    assert _history_count(client) == 1
    enforcer = RunBudgetEnforcer.for_run(run_id)
    assert enforcer is not None
    assert enforcer.consumed().llm_calls == 1


# ---------------------------------------------------------------------------
# IPC-Pfad: Vorab-Guard mit echtem Enforcer
# ---------------------------------------------------------------------------


def test_ipc_guard_with_real_enforcer_blocks_exhausted_budget(run_dirs):
    run_id = _create_job({"max_llm_calls": 1, "enforcement": "hard"})
    _append_event(run_dirs, run_id, prompt_tokens=10)

    with pytest.raises(BudgetExceededError) as excinfo:
        with interview_client._report_budget_guard(run_id):
            pytest.fail("Guard darf den IPC-Versuch nicht durchlassen")

    assert excinfo.value.dimension == "calls"
    assert excinfo.value.persisted_count == 0


def test_ipc_guard_with_real_enforcer_lets_open_budget_through(run_dirs):
    run_id = _create_job({"max_llm_calls": 3, "enforcement": "hard"})

    with interview_client._report_budget_guard(run_id):
        pass  # kein Fehler; Reservierung wird im finally freigegeben
