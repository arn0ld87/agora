"""GET /api/report/<id>/evidence liefert abgeleitete Sprungkennungen (Issue #1804).

Die Kennungen entstehen im Lesepfad aus ``raw`` und ``producer_key`` und werden
nie gespeichert — die persistierte Evidence-Map bleibt unverändert, und die
Ableitung gilt damit auch für Altberichte.
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest
from flask import Flask

from app.api import report_bp
from app.contracts.report_contract import EvidenceMapResponseModel
from app.services.evidence_identity import build_evidence_id

REPORT_ID = "report_abcdef123456"
NODE_UUID = "3f2b9c1e-8a4d-4f6b-9c7e-1a2b3c4d5e6f"
TIMESTAMP = "2026-08-02T15:02:16.055352"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _record(key: str, kind: str, source_kind: str, **extra) -> dict:
    return {
        "evidence_id": build_evidence_id(REPORT_ID, source_kind, key),
        "producer_key": key,
        "type": kind,
        "source": "simulation_actions" if kind == "agent_action" else "report_tool",
        "snippet": "Beleg",
        "source_kind": source_kind,
        **extra,
    }


def _persisted_map() -> dict:
    """Gespeicherte v3-Map, so wie der Schreibpfad sie ablegt: ohne origin_*-Schlüssel."""
    post_key = f"simulation-action:twitter:3:7:CREATE_POST:{TIMESTAMP}"
    comment_key = f"simulation-action:reddit:2:4:CREATE_COMMENT:{TIMESTAMP}"
    like_key = f"simulation-action:twitter:3:7:LIKE_POST:{TIMESTAMP}"
    node_key = f"graph-node:{NODE_UUID}"
    records = [
        _record(
            post_key, "agent_action", "agent_action", voice_key="agent:7",
            raw={"platform": "twitter", "action_type": "CREATE_POST", "action_args": {"content": "x", "post_id": 12}},
        ),
        _record(
            comment_key, "agent_action", "agent_action", voice_key="agent:4",
            raw={"platform": "reddit", "action_type": "CREATE_COMMENT", "action_args": {"comment_id": 5}},
        ),
        _record(
            like_key, "agent_action", "agent_action", voice_key="agent:7",
            raw={"platform": "twitter", "action_type": "LIKE_POST", "action_args": {"post_id": 8}},
        ),
        _record(node_key, "entity_summary", "graph_relation", raw={"uuid": NODE_UUID, "name": "Stadt"}),
        _record("graph-fact:abc", "graph_fact", "graph_relation", raw="Ein Faktentext"),
    ]
    return {
        "schema_version": 3,
        "report_id": REPORT_ID,
        "simulation_id": "sim_0123456789ab",
        "evidence_index": {r["evidence_id"]: r for r in records},
        "global_evidence_refs": [],
        "sections": [],
    }


def _get(client, evidence_map: dict):
    with (
        patch("app.api.report.validate_report_id", return_value=True),
        patch("app.api.report.ReportManager.get_evidence_map", return_value=evidence_map),
    ):
        return client.get(f"/api/report/{REPORT_ID}/evidence")


def _by_key(body: dict) -> dict:
    return {r["producer_key"]: r for r in body["data"]["evidence_index"].values()}


def test_route_delivers_derived_origin_ids_per_evidence_type(client) -> None:
    resp = _get(client, _persisted_map())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    records = _by_key(body)
    assert records[f"simulation-action:twitter:3:7:CREATE_POST:{TIMESTAMP}"]["origin_post_id"] == "twitter:12"
    assert (
        records[f"simulation-action:reddit:2:4:CREATE_COMMENT:{TIMESTAMP}"]["origin_post_id"]
        == "reddit:comment:5"
    )
    assert records[f"graph-node:{NODE_UUID}"]["origin_node_uuids"] == [NODE_UUID]
    # Antwort bleibt vertragsgueltig.
    EvidenceMapResponseModel.model_validate(body)


def test_route_leaves_origin_fields_out_where_nothing_is_unique(client) -> None:
    records = _by_key(_get(client, _persisted_map()).get_json())

    like = records[f"simulation-action:twitter:3:7:LIKE_POST:{TIMESTAMP}"]
    fact = records["graph-fact:abc"]
    for record in (like, fact):
        assert "origin_post_id" not in record
        assert "origin_node_uuids" not in record


def test_route_does_not_touch_the_persisted_map(client) -> None:
    persisted = _persisted_map()
    before = copy.deepcopy(persisted)

    assert _get(client, persisted).status_code == 200

    assert persisted == before


def test_map_without_origin_keys_stays_valid(client) -> None:
    """Ein Bestand ohne die Felder bleibt gueltig; die Felder sind rein additiv."""
    persisted = _persisted_map()
    for record in persisted["evidence_index"].values():
        assert "origin_post_id" not in record
    assert _get(client, persisted).status_code == 200
