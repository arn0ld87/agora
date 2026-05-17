"""Tests für Pagination-Clamps an /actions und /run-status/detail.

Baustein C — Hardening PR 5
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp


VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


def _make_fake_actions(n: int = 5):
    actions = []
    for i in range(n):
        a = MagicMock()
        a.to_dict.return_value = {"action_id": i, "type": "post"}
        actions.append(a)
    return actions


def _make_run_state():
    rs = MagicMock()
    rs.current_round = 1
    rs.rounds = [MagicMock()]
    rs.to_dict.return_value = {
        "simulation_id": VALID_SIM_ID,
        "runner_status": "completed",
    }
    return rs


class TestActionsLimitClamp:
    def test_actions_limit_clamped_to_max_500(self, client):
        """?limit=10000 wird auf 500 geclampt — Antwort enthält höchstens 500 Einträge."""
        fake_actions = _make_fake_actions(5)
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_actions",
                return_value=fake_actions,
            ) as mock_get,
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?limit=10000"
            )

        assert resp.status_code == 200
        # Der Aufruf an get_actions muss mit limit=500 erfolgen (geclampt)
        call_kwargs = mock_get.call_args
        passed_limit = call_kwargs.kwargs.get("limit") or call_kwargs.args[1] if call_kwargs.args else None
        if passed_limit is None and call_kwargs.kwargs:
            passed_limit = call_kwargs.kwargs.get("limit")
        assert passed_limit == 500, f"limit wurde nicht auf 500 geclampt: {call_kwargs}"

    def test_actions_offset_clamped_to_zero_for_negative_input(self, client):
        """?offset=-5 führt zu offset=0 — keine 400, sondern stilles Clamp."""
        fake_actions = _make_fake_actions(3)
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_actions",
                return_value=fake_actions,
            ) as mock_get,
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?offset=-5"
            )

        assert resp.status_code == 200
        call_kwargs = mock_get.call_args
        passed_offset = call_kwargs.kwargs.get("offset")
        assert passed_offset == 0, f"offset wurde nicht auf 0 geclampt: {call_kwargs}"

    def test_actions_valid_limit_passed_through(self, client):
        """?limit=50 wird unverändert durchgereicht."""
        fake_actions = _make_fake_actions(2)
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_actions",
                return_value=fake_actions,
            ) as mock_get,
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?limit=50"
            )

        assert resp.status_code == 200
        call_kwargs = mock_get.call_args
        passed_limit = call_kwargs.kwargs.get("limit")
        assert passed_limit == 50


class TestRunStatusDetailPagination:
    def test_run_status_detail_returns_aggregate_plus_paginated_actions(self, client):
        """Response enthält actions_total (int) plus actions: list."""
        fake_all_actions = _make_fake_actions(10)
        fake_page_actions = _make_fake_actions(5)
        run_state = _make_run_state()

        with (
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
            patch(
                "app.api.simulation_run.SimulationRunner.get_run_state",
                return_value=run_state,
            ),
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=fake_all_actions,
            ),
            patch(
                "app.api.simulation_run.SimulationRunner.get_actions",
                return_value=fake_page_actions,
            ),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/run-status/detail")

        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)  # json_success wraps in {"success": True, "data": {...}}
        assert "actions_total" in data, f"actions_total fehlt: {list(data.keys())}"
        assert isinstance(data["actions_total"], int)
        assert "actions" in data, f"actions fehlt: {list(data.keys())}"
        assert isinstance(data["actions"], list)

    def test_run_status_detail_actions_paginate_with_offset_and_limit(self, client):
        """?offset=10&limit=20 wird an get_actions weitergereicht."""
        fake_all_actions = _make_fake_actions(30)
        fake_page_actions = _make_fake_actions(20)
        run_state = _make_run_state()

        with (
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
            patch(
                "app.api.simulation_run.SimulationRunner.get_run_state",
                return_value=run_state,
            ),
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=fake_all_actions,
            ),
            patch(
                "app.api.simulation_run.SimulationRunner.get_actions",
                return_value=fake_page_actions,
            ) as mock_get_actions,
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/run-status/detail?offset=10&limit=20"
            )

        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["actions"]) == 20

        call_kwargs = mock_get_actions.call_args
        passed_limit = call_kwargs.kwargs.get("limit")
        passed_offset = call_kwargs.kwargs.get("offset")
        assert passed_limit == 20, f"limit falsch: {call_kwargs}"
        assert passed_offset == 10, f"offset falsch: {call_kwargs}"

    def test_run_status_detail_idle_simulation_returns_empty_actions(self, client):
        """Wenn kein run_state: actions=[] und actions_total=0."""
        with (
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
            patch(
                "app.api.simulation_run.SimulationRunner.get_run_state",
                return_value=None,
            ),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/run-status/detail")

        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data.get("actions_total") == 0
        assert data.get("actions") == []
