"""HTTP-level tests for the GraphML export endpoint (Slice 5.3)."""

from __future__ import annotations

from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer


GID = "abcdef0123456789abcdef0123456789"


def _graph_payload():
    return {
        "graph_id": GID,
        "nodes": [
            {
                "uuid": "node-1",
                "name": "Alice",
                "type": "Person",
                "attributes": {"role": "lead"},
            },
            {
                "uuid": "node-2",
                "name": "Bob",
                "type": "Person",
            },
        ],
        "edges": [
            {
                "uuid": "edge-1",
                "source_uuid": "node-1",
                "target_uuid": "node-2",
                "name": "knows",
                "fact_type": "knows",
                "valid_from_round": 0,
                "valid_to_round": None,
                "episode_ids": ["ep-1", "ep-2"],
            }
        ],
        "node_count": 2,
        "edge_count": 1,
    }


@pytest.fixture
def env(monkeypatch):
    storage = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=storage)

    payload = _graph_payload()
    storage.get_graph_data = MagicMock(return_value=payload)

    app = Flask(__name__)
    app.extensions = {"container": container}
    app.register_blueprint(graph_bp, url_prefix="/api/graph")

    yield {
        "client": app.test_client(),
        "storage": storage,
        "payload": payload,
    }


def test_export_rejects_invalid_graph_id(env):
    response = env["client"].get("/api/graph/not-valid/export?format=graphml")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_export_rejects_unknown_format(env):
    response = env["client"].get(f"/api/graph/{GID}/export?format=svg")
    assert response.status_code == 400
    assert response.get_json()["code"] == "unsupported_format"


def test_export_404_when_graph_empty(env):
    env["storage"].get_graph_data = MagicMock(return_value={
        "graph_id": GID,
        "nodes": [],
        "edges": [],
        "node_count": 0,
        "edge_count": 0,
    })
    response = env["client"].get(f"/api/graph/{GID}/export?format=graphml")
    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


def test_export_returns_graphml_attachment(env):
    response = env["client"].get(f"/api/graph/{GID}/export?format=graphml")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    disposition = response.headers.get("Content-Disposition", "")
    assert f"agora-graph-{GID}.graphml" in disposition

    # Parse the GraphML XML — must contain the two nodes and one edge.
    root = ET.fromstring(response.data)
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    nodes = root.findall(".//g:node", ns)
    edges = root.findall(".//g:edge", ns)
    assert len(nodes) == 2
    assert len(edges) == 1

    node_ids = sorted(n.attrib["id"] for n in nodes)
    assert node_ids == ["node-1", "node-2"]

    edge = edges[0]
    assert edge.attrib["source"] == "node-1"
    assert edge.attrib["target"] == "node-2"


def test_export_format_default_is_graphml(env):
    response = env["client"].get(f"/api/graph/{GID}/export")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
