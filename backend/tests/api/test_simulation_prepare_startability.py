"""Regression fuer konkurrierende Prepare-Laeufe derselben Simulation."""

import threading
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_prepare as mod
from app.services.simulation_manager import SimulationStatus


def test_preparing_simulation_rejects_second_prepare_before_run_creation() -> None:
    app = Flask(__name__)
    state = MagicMock(status=SimulationStatus.PREPARING)

    with app.test_request_context(), pytest.raises(mod._PrepareRejected) as excinfo:
        mod._ensure_prepare_startable(state)

    response, status = excinfo.value.response
    payload = response.get_json()
    assert status == 409
    assert payload["code"] == "simulation_prepare_in_progress"


def test_prepare_start_window_is_serialized_per_simulation(monkeypatch) -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    calls = 0
    calls_guard = threading.Lock()

    def fake_start(_data, _simulation_id, _ai_model_ref):
        nonlocal calls
        with calls_guard:
            calls += 1
            call_number = calls
        if call_number == 1:
            first_entered.set()
            assert release_first.wait(timeout=1)
        else:
            second_entered.set()
        return "ok"

    monkeypatch.setattr(mod, "_prepare_simulation_under_start_lock", fake_start)
    app = Flask(__name__)
    results: list[str] = []

    def invoke() -> None:
        with app.test_request_context(
            json={"simulation_id": "sim_0123456789ab"}
        ):
            results.append(mod.prepare_simulation())

    first = threading.Thread(target=invoke)
    second = threading.Thread(target=invoke)
    first.start()
    assert first_entered.wait(timeout=1)
    second.start()
    assert not second_entered.wait(timeout=0.1)

    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_entered.is_set()
    assert results == ["ok", "ok"]
