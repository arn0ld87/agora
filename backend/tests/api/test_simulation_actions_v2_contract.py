"""``GET /api/simulation/<id>/actions`` als SimActionPage (#1713 UI-2a).

Deckt die Umstellung von Offset- auf Cursor-Pagination, den action_type-Filter
(clientseitig, da ``SimulationRunner.get_all_actions`` ihn nicht kennt) und
die target_post_id-Ableitung je Aktionsart ab.
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
        action_args={"post_id": 42, "content": "Hallo Welt"},
    )
    base.update(overrides)
    return AgentAction(**base)


class TestActionTypeFilter:
    def test_filters_client_side_by_action_type(self, client) -> None:
        actions = [
            _action(action_type="CREATE_POST"),
            _action(action_type="LIKE_POST", action_args={"post_id": 42}),
        ]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(
                f"/api/simulation/{VALID_SIM_ID}/actions?action_type=LIKE_POST"
            )
        data = resp.get_json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["action_type"] == "LIKE_POST"

    def test_unknown_action_type_falls_back_to_other(self, client) -> None:
        actions = [_action(action_type="SOME_FUTURE_ACTION")]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        data = resp.get_json()["data"]
        assert data["items"][0]["action_type"] == "OTHER"


class TestTargetPostIdDerivation:
    def test_like_post_targets_post_id(self, client) -> None:
        actions = [_action(action_type="LIKE_POST", action_args={"post_id": 7})]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        item = resp.get_json()["data"]["items"][0]
        assert item["target_post_id"] == "7"

    def test_repost_targets_original_post_id_not_new_post_id(self, client) -> None:
        actions = [
            _action(
                action_type="REPOST",
                action_args={"new_post_id": 99, "original_post_id": 42},
            )
        ]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        item = resp.get_json()["data"]["items"][0]
        assert item["target_post_id"] == "42"

    def test_quote_post_targets_quoted_id(self, client) -> None:
        actions = [
            _action(
                action_type="QUOTE_POST",
                action_args={"new_post_id": 100, "quoted_id": 42, "quote_content": "x"},
            )
        ]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        item = resp.get_json()["data"]["items"][0]
        assert item["target_post_id"] == "42"

    def test_create_post_has_no_target(self, client) -> None:
        actions = [_action(action_type="CREATE_POST", action_args={"post_id": 1})]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        item = resp.get_json()["data"]["items"][0]
        assert item["target_post_id"] is None


class TestRoleConflictAndSuccess:
    def test_role_conflict_passed_through(self, client) -> None:
        actions = [_action(role_conflict="foreign_role")]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        item = resp.get_json()["data"]["items"][0]
        assert item["role_conflict"] == "foreign_role"

    def test_success_false_passed_through(self, client) -> None:
        actions = [_action(success=False)]
        with (
            patch(
                "app.api.simulation_run.SimulationRunner.get_all_actions",
                return_value=actions,
            ),
            patch("app.api.simulation_run.validate_simulation_id", return_value=True),
        ):
            resp = client.get(f"/api/simulation/{VALID_SIM_ID}/actions")
        item = resp.get_json()["data"]["items"][0]
        assert item["success"] is False
