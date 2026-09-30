"""Tests für Pagination-Clamps an /actions und /run-status/detail.

Baustein C — Hardening PR 5
#1713 UI-2a: /actions liefert seither ``SimActionPage`` (Cursor statt
Offset) — ``TestActionsLimitClamp`` nutzt echte ``AgentAction``-Fixtures
und patcht ``get_all_actions`` (nicht mehr ``get_actions``), damit die
Konvertierung nach ``SimActionRecord`` gueltige Daten sieht.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services.sim.run_state_store import AgentAction


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


def _make_agent_actions(n: int) -> list[AgentAction]:
    return [
        AgentAction(
            round_num=1,
            timestamp="2026-09-29T09:00:00+00:00",
            platform="reddit",
            agent_id=1,
            agent_name="Mara Lindner",
            action_type="CREATE_POST",
            action_args={"post_id": i, "content": f"Post {i}"},
        )
        for i in range(n)
    ]


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
        """?limit=10000 wird auf 500 geclampt — die Seite enthält höchstens 500 Einträge."""
        fake_actions = _make_agent_actions(600)
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=fake_actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?limit=10000"
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["items"]) == 500, f"limit wurde nicht auf 500 geclampt: {len(data['items'])}"
        assert data["next_cursor"] == "500"

    def test_actions_invalid_cursor_clamped_to_zero(self, client):
        """Ungültiger/negativer cursor führt zu Offset 0 — keine 400, stilles Clamp."""
        fake_actions = _make_agent_actions(3)
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=fake_actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?cursor=-5"
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["items"]) == 3
        assert data["next_cursor"] is None

    def test_actions_valid_limit_passed_through(self, client):
        """?limit=50 begrenzt die Seite auf 50 Einträge."""
        fake_actions = _make_agent_actions(120)
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=fake_actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?limit=50"
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["items"]) == 50
        assert data["next_cursor"] == "50"


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

    def test_run_status_detail_drops_legacy_all_actions_count(self, client):
        """`all_actions_count` ist ein redundantes Duplikat von `actions_total`.

        Vor dem Fix lieferte der Endpoint beide Felder mit demselben Wert, was
        die Paginierungs-Architektur verschleiert (Aggregat vs. Detail-Seite).
        Per `grep -rn all_actions_count frontend/src` wird das Feld im Frontend
        nicht gelesen — also wird es hier hart entfernt.
        """
        fake_all_actions = _make_fake_actions(7)
        fake_page_actions = _make_fake_actions(4)
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
        data = body.get("data", body)
        assert "actions_total" in data, f"actions_total fehlt: {list(data.keys())}"
        assert data["actions_total"] == 7
        assert "all_actions_count" not in data, (
            f"all_actions_count ist redundant und soll weg: {list(data.keys())}"
        )
