"""HTTP-level tests für GET /api/graph/<graph_id>/diff (Sub-Slice 22, Closes #74).

Testet den Endpoint mit gemocktem Container und StubStorage — kein Neo4j nötig.
Layer-0-Boundary: Responses werden gegen PydanticGraphDiff.model_validate() geprüft.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.contracts import GraphDiff as PydanticGraphDiff

GRAPH_ID = "abcdef012345abcdef012345abcdef01"


# ---------------------------------------------------------------------------
# Stub Storage (wiederverwenden aus test_temporal_graph.py — kein gemeinsamer
# Import, da wir die Fixture hier eigenständig halten wollen)
# ---------------------------------------------------------------------------


class _StubStorage:
    def __init__(self, edges: List[Dict[str, Any]] | None = None) -> None:
        self.edges: List[Dict[str, Any]] = edges or []
        self.backfill_calls = 0

    def get_edges_at_round(self, graph_id: str, round_num: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for e in self.edges:
            if e.get("graph_id") != graph_id:
                continue
            vfr = e.get("valid_from_round")
            vtr = e.get("valid_to_round")
            vfr_eff = 0 if vfr is None else vfr
            if vfr_eff > round_num:
                continue
            if vtr is not None and vtr <= round_num:
                continue
            out.append({k: v for k, v in e.items() if k != "graph_id"})
        return out

    def backfill_temporal_defaults(self, graph_id: Optional[str] = None) -> int:
        self.backfill_calls += 1
        return 0


def _make_edge(
    uuid: str,
    vfr: Optional[int] = 0,
    vtr: Optional[int] = None,
    reinforced: int = 1,
    source_id: str = "node-A",
    target_id: str = "node-B",
) -> Dict[str, Any]:
    return {
        "graph_id": GRAPH_ID,
        "uuid": uuid,
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": "FOLLOWS",
        "valid_from_round": vfr,
        "valid_to_round": vtr,
        "reinforced_count": reinforced,
        "weight": float(reinforced),
    }


# ---------------------------------------------------------------------------
# Flask-App-Fixture mit Container-Mock
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_stub(monkeypatch):
    """Flask-Testapp mit Container, der einen StubStorage enthält."""
    storage = _StubStorage(
        edges=[
            # Edge sichtbar in Runde 0 und 1
            _make_edge("edge-stable", vfr=0, source_id="A", target_id="B"),
            # Edge nur in Runde 1 hinzugekommen
            _make_edge("edge-new", vfr=1, source_id="B", target_id="C"),
            # Edge in Runde 0 da, in Runde 1 nicht mehr
            _make_edge("edge-gone", vfr=0, vtr=1, source_id="C", target_id="D"),
        ]
    )
    container = AgoraContainer(neo4j_storage=storage)  # type: ignore[arg-type]

    flask_app = Flask(__name__)
    flask_app.extensions["container"] = container
    flask_app.register_blueprint(graph_bp, url_prefix="/api/graph")

    yield flask_app, flask_app.test_client()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_diff_returns_200_with_valid_graph_diff_structure(app_with_stub):
    """GET /api/graph/<id>/diff?start_round=0&end_round=1 → 200, GraphDiff-Contract valide."""
    _, client = app_with_stub

    resp = client.get(f"/api/graph/{GRAPH_ID}/diff?start_round=0&end_round=1")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    data = payload["data"]
    # Layer-0-Boundary: vollständige Validation gegen das Pydantic-Modell
    diff = PydanticGraphDiff.model_validate(data)
    assert diff.graph_id == GRAPH_ID
    assert diff.comparison_type == "round-to-round"
    assert diff.snapshot_a is not None
    assert diff.snapshot_b is not None
    assert diff.metrics is not None


def test_diff_missing_params_returns_400(app_with_stub):
    """Fehlende Query-Parameter → 400 mit VALIDATION_FAILED."""
    _, client = app_with_stub

    # beide fehlen
    resp = client.get(f"/api/graph/{GRAPH_ID}/diff")
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "code" in payload
    assert payload["code"] == "validation_failed"

    # nur start_round fehlt
    resp2 = client.get(f"/api/graph/{GRAPH_ID}/diff?end_round=1")
    assert resp2.status_code == 400

    # nur end_round fehlt
    resp3 = client.get(f"/api/graph/{GRAPH_ID}/diff?start_round=0")
    assert resp3.status_code == 400


def test_diff_invalid_round_order_returns_400(app_with_stub):
    """start_round > end_round → 400."""
    _, client = app_with_stub

    resp = client.get(f"/api/graph/{GRAPH_ID}/diff?start_round=5&end_round=2")
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert payload["code"] == "validation_failed"


def test_diff_snapshot_a_b_have_expected_fields(app_with_stub):
    """Response enthält alle erwarteten Top-Level-Felder des GraphDiff-Contracts."""
    _, client = app_with_stub

    resp = client.get(f"/api/graph/{GRAPH_ID}/diff?start_round=0&end_round=1")
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    required_keys = {
        "graph_id",
        "snapshot_a_id",
        "snapshot_b_id",
        "created_at",
        "comparison_type",
        "snapshot_a",
        "snapshot_b",
        "edges_added",
        "edges_removed",
        "edges_reinforced",
        "edges_weakened",
        "metrics",
    }
    assert required_keys.issubset(data.keys()), (
        f"Fehlende Keys: {required_keys - data.keys()}"
    )

    # Metrics-Plausibilität
    metrics = data["metrics"]
    assert isinstance(metrics["total_edges_added"], int)
    assert isinstance(metrics["total_edges_removed"], int)
    assert isinstance(metrics["total_edges_reinforced"], int)
    assert isinstance(metrics["density_delta"], float)

    # snapshot_a_id und snapshot_b_id sind unterschiedlich, wenn start != end
    assert data["snapshot_a_id"] != data["snapshot_b_id"]


def test_diff_same_round_returns_empty_diff(app_with_stub):
    """start_round == end_round → keine added/removed, reinforced leer."""
    _, client = app_with_stub

    resp = client.get(f"/api/graph/{GRAPH_ID}/diff?start_round=0&end_round=0")
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["edges_added"] == []
    assert data["edges_removed"] == []
    assert data["edges_reinforced"] == []
    assert data["metrics"]["total_edges_added"] == 0
    assert data["metrics"]["total_edges_removed"] == 0
