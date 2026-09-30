"""``GET /api/simulation/<id>/rounds`` — RoundSummary je Runde+Plattform
(#1713 UI-2a).

Anders als ``/timeline`` (ein kombinierter Eintrag je Runde) liefert dieser
Endpoint einen Eintrag je (round_num, platform)-Paar.
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


def _action(**overrides) -> AgentAction:
    base = dict(
        round_num=1,
        timestamp="2026-09-29T09:00:00+00:00",
        platform="reddit",
        agent_id=1,
        agent_name="Mara Lindner",
        action_type="CREATE_POST",
        action_args={"post_id": 1, "content": "x"},
    )
    base.update(overrides)
    return AgentAction(**base)


class TestSimulationRounds:
    def test_splits_by_round_and_platform(self, client) -> None:
        actions = [
            _action(round_num=1, platform="reddit", action_type="CREATE_POST"),
            _action(round_num=1, platform="reddit", action_type="CREATE_COMMENT"),
            _action(round_num=1, platform="twitter", action_type="CREATE_POST"),
            _action(round_num=2, platform="reddit", action_type="LIKE_POST"),
        ]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/rounds")

        assert resp.status_code == 200
        rounds = resp.get_json()["data"]["rounds"]
        assert len(rounds) == 3  # (1,reddit) (1,twitter) (2,reddit)

        r1_reddit = next(r for r in rounds if r["round_num"] == 1 and r["platform"] == "reddit")
        assert r1_reddit["action_counts"]["CREATE_POST"] == 1
        assert r1_reddit["action_counts"]["CREATE_COMMENT"] == 1

        r1_twitter = next(r for r in rounds if r["round_num"] == 1 and r["platform"] == "twitter")
        assert r1_twitter["action_counts"]["CREATE_POST"] == 1

        r2_reddit = next(r for r in rounds if r["round_num"] == 2 and r["platform"] == "reddit")
        assert r2_reddit["action_counts"]["LIKE_POST"] == 1

    def test_sorted_by_round_then_platform(self, client) -> None:
        actions = [
            _action(round_num=2, platform="twitter"),
            _action(round_num=1, platform="twitter"),
            _action(round_num=1, platform="reddit"),
        ]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/rounds")

        rounds = resp.get_json()["data"]["rounds"]
        keys = [(r["round_num"], r["platform"]) for r in rounds]
        assert keys == [(1, "reddit"), (1, "twitter"), (2, "twitter")]

    def test_empty_simulation_returns_empty_rounds(self, client) -> None:
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=[],
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/rounds")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["rounds"] == []

    def test_invalid_simulation_id_rejected(self, client) -> None:
        resp = client.get("/api/simulation/not-a-sim-id/rounds")
        assert resp.status_code in (400, 404)

    def test_unknown_action_type_grouped_as_other(self, client) -> None:
        actions = [_action(action_type="SOME_FUTURE_ACTION")]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/rounds")
        rounds = resp.get_json()["data"]["rounds"]
        assert rounds[0]["action_counts"]["OTHER"] == 1
