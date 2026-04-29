"""HTTP-level tests for the metrics CSV export (Slice 5.2)."""

from __future__ import annotations

import csv
import io
from typing import List

import pytest
from flask import Flask

from app.api import simulation_bp
from app.container import AgoraContainer
from app.services.simulation_runner import AgentAction, SimulationRunner


SIM_ID = "sim_abcdef123456"


def _action(round_num: int, agent_id: int, target: int, action_type: str = "FOLLOW") -> AgentAction:
    arg_key = "followee_id" if action_type == "FOLLOW" else "author_id"
    return AgentAction(
        round_num=round_num,
        timestamp=f"2026-04-29T10:{round_num:02d}:00",
        platform="twitter",
        agent_id=agent_id,
        agent_name=f"agent_{agent_id}",
        action_type=action_type,
        action_args={arg_key: target},
    )


@pytest.fixture
def env(monkeypatch):
    actions: List[AgentAction] = []
    # Two tight clusters {1,2,3} and {4,5,6} plus bridge agent 7 follows
    # both sides — enough to produce >= 2 dominant clusters.
    actions.append(_action(0, 1, 2))
    actions.append(_action(0, 2, 3))
    actions.append(_action(0, 3, 1))
    actions.append(_action(0, 4, 5))
    actions.append(_action(0, 5, 6))
    actions.append(_action(0, 6, 4))
    actions.append(_action(0, 7, 1))
    actions.append(_action(0, 7, 4))

    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        classmethod(lambda cls, simulation_id, platform=None: actions),
    )

    app = Flask(__name__)
    app.extensions = {"container": AgoraContainer()}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")

    yield app.test_client()


def _read_csv(body: bytes) -> List[List[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8"))))


def test_export_rejects_invalid_simulation_id(env):
    response = env.get("/api/simulation/not-a-valid-id/metrics/export?format=csv")
    assert response.status_code == 400


def test_export_rejects_unknown_format(env):
    response = env.get(f"/api/simulation/{SIM_ID}/metrics/export?format=xml")
    assert response.status_code == 400


def test_export_rejects_unknown_view(env):
    response = env.get(f"/api/simulation/{SIM_ID}/metrics/export?view=foo")
    assert response.status_code == 400


def test_export_rejects_invalid_window(env):
    response = env.get(f"/api/simulation/{SIM_ID}/metrics/export?window_size_rounds=abc")
    assert response.status_code == 400


def test_export_summary_csv_default(env):
    response = env.get(f"/api/simulation/{SIM_ID}/metrics/export")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    disposition = response.headers.get("Content-Disposition", "")
    assert f"agora-metrics-{SIM_ID}-summary.csv" in disposition

    rows = _read_csv(response.data)
    assert rows[0] == [
        "simulation_id",
        "window_size_rounds",
        "total_agents",
        "total_interactions",
        "echo_chamber_index",
        "cluster_count",
    ]
    assert rows[1][0] == SIM_ID
    assert int(rows[1][2]) >= 6  # all unique agents seen
    assert int(rows[1][3]) >= 8  # interactions counted
    assert int(rows[1][5]) >= 1  # at least one cluster


def test_export_clusters_csv(env):
    response = env.get(f"/api/simulation/{SIM_ID}/metrics/export?view=clusters")
    assert response.status_code == 200
    rows = _read_csv(response.data)
    assert rows[0] == ["cluster_id", "size", "agent_ids"]
    # Body rows must each have an int size and at least one agent id.
    assert len(rows) >= 2
    for row in rows[1:]:
        assert int(row[1]) >= 1
        assert row[2]  # non-empty agent_ids list


def test_export_bridges_csv(env):
    response = env.get(f"/api/simulation/{SIM_ID}/metrics/export?view=bridges")
    assert response.status_code == 200
    rows = _read_csv(response.data)
    assert rows[0] == ["rank", "agent_id"]
    # bridge_agents may legitimately be empty if topology is too small;
    # if rows exist, ranks must be 1-indexed monotonic ints.
    if len(rows) > 1:
        ranks = [int(r[0]) for r in rows[1:]]
        assert ranks == list(range(1, len(ranks) + 1))
