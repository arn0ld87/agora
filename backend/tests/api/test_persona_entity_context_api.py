"""API-Tests fuer GET /<sim>/profiles/<username>/entity-context (Issue #69).

Testet:
1. 200 fuer bekannte Persona mit source_entity_uuid (graph-Pfad)
2. 404 fuer unbekannte Persona
3. 400 fuer ungueltige simulation_id
4. 200 mit source='fallback' fuer Legacy-Profil ohne source_entity_uuid
5. 200 mit source='fallback' wenn Graph-Lookup fehlschlaegt
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts import PersonaEntityContext
from app.services.artifact_store import InMemoryArtifactStore

SIM_ID = "sim_aabbccdd0011"
USERNAME = "max_muster"

# Profil MIT source_entity_uuid (normaler Pfad)
_PROFILE_WITH_ENTITY = {
    "user_id": 1,
    "username": USERNAME,
    "name": "Max Mustermann",
    "bio": "Tech-Enthusiast aus Berlin.",
    "persona": "Max ist neugierig und technikaffin.",
    "karma": 1200,
    "created_at": "2024-01-15",
    "source_entity_uuid": "ent-uuid-abc123",
    "source_entity_type": "PERSON",
    "review_status": "approved",
    "review_notes": None,
    "reviewed_at": None,
}

# Profil OHNE source_entity_uuid (Legacy)
_PROFILE_LEGACY = {
    "user_id": 2,
    "username": "legacy_user",
    "name": "Legacy User",
    "bio": "Ein alter Account.",
    "persona": "legacy_user nutzt Reddit seit Jahren.",
    "karma": 500,
    "created_at": "2023-06-01",
    "review_status": "approved",
    "review_notes": None,
    "reviewed_at": None,
}

# Minimaler node-dict wie er von storage.get_node() zurueckkommt
_NODE_DICT = {
    "uuid": "ent-uuid-abc123",
    "name": "Max Mustermann",
    "labels": ["PERSON"],
    "summary": "Berliner Startup-Gruender.",
    "attributes": {"city": "Berlin", "age": 38},
    "created_at": None,
}


def _make_app(store: InMemoryArtifactStore, storage_mock) -> Flask:
    """Erstellt eine minimale Flask-App mit Blueprint und Mocks."""
    flask_app = Flask(__name__)
    flask_app.extensions["artifact_store"] = store
    flask_app.extensions["neo4j_storage"] = storage_mock
    flask_app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return flask_app


def _make_store(*profiles) -> InMemoryArtifactStore:
    store = InMemoryArtifactStore()
    store.write_json(SIM_ID, "reddit_profiles", list(profiles))
    return store


@pytest.fixture()
def storage_with_node():
    """GraphStorage-Mock, der _NODE_DICT und keine Edges liefert."""
    mock = MagicMock(name="GraphStorage")
    mock.get_node.return_value = _NODE_DICT
    mock.get_node_edges.return_value = []
    return mock


@pytest.fixture()
def storage_node_not_found():
    """GraphStorage-Mock, bei dem get_node immer None zurueckgibt."""
    mock = MagicMock(name="GraphStorage")
    mock.get_node.return_value = None
    mock.get_node_edges.return_value = []
    return mock


# ---------------------------------------------------------------------------
# Test 1: 200 fuer bekannte Persona mit source_entity_uuid
# ---------------------------------------------------------------------------


def test_get_entity_context_returns_200_for_known_persona(storage_with_node):
    store = _make_store(_PROFILE_WITH_ENTITY)
    app = _make_app(store, storage_with_node)

    with app.test_client() as client:
        resp = client.get(
            f"/api/simulation/{SIM_ID}/profiles/{USERNAME}/entity-context"
        )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["success"] is True
    payload = data["data"]

    # Muss gegen den Pydantic-Contract validierbar sein
    ctx = PersonaEntityContext.model_validate(payload)
    assert ctx.username == USERNAME
    assert ctx.simulation_id == SIM_ID
    assert ctx.entity_uuid == "ent-uuid-abc123"
    assert ctx.source == "graph"
    assert ctx.entity_label == "Max Mustermann"
    assert ctx.entity_type == "PERSON"
    assert ctx.entity_properties == {"city": "Berlin", "age": 38}


# ---------------------------------------------------------------------------
# Test 2: 404 fuer unbekannte Persona
# ---------------------------------------------------------------------------


def test_get_entity_context_404_for_unknown_persona(storage_with_node):
    store = _make_store()  # leerer Store — keine Profile
    app = _make_app(store, storage_with_node)

    with app.test_client() as client:
        resp = client.get(
            f"/api/simulation/{SIM_ID}/profiles/ghost_user/entity-context"
        )

    assert resp.status_code == 404
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "not_found"


# ---------------------------------------------------------------------------
# Test 3: 400 fuer ungueltige simulation_id
# ---------------------------------------------------------------------------


def test_get_entity_context_invalid_simulation_id_400(storage_with_node):
    store = _make_store()
    app = _make_app(store, storage_with_node)

    with app.test_client() as client:
        # Slashes in simulation_id sind ungueltig
        resp = client.get(
            "/api/simulation/invalid/../profiles/x/entity-context"
        )

    # Flask gibt 404 auf ungematchten Pfad oder 400 auf validate_simulation_id
    assert resp.status_code in (400, 404)
    if resp.status_code == 400:
        data = resp.get_json()
        assert data["code"] == "invalid_id"


def test_get_entity_context_bogus_sim_id_400(storage_with_node):
    """simulation_id mit Leerzeichen / Sonderzeichen schlaegt validate_simulation_id fehl."""
    store = _make_store()
    app = _make_app(store, storage_with_node)

    with app.test_client() as client:
        resp = client.get(
            "/api/simulation/not%20valid%21/profiles/x/entity-context"
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "invalid_id"


# ---------------------------------------------------------------------------
# Test 4: 200 mit source='fallback' fuer Legacy-Profil ohne source_entity_uuid
# ---------------------------------------------------------------------------


def test_get_entity_context_legacy_profile_fallback(storage_with_node):
    store = _make_store(_PROFILE_LEGACY)
    app = _make_app(store, storage_with_node)

    with app.test_client() as client:
        resp = client.get(
            f"/api/simulation/{SIM_ID}/profiles/legacy_user/entity-context"
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    payload = data["data"]

    ctx = PersonaEntityContext.model_validate(payload)
    assert ctx.source == "fallback"
    assert ctx.entity_uuid == ""
    assert ctx.entity_properties == {}
    assert ctx.relationships == []
    # storage.get_node sollte NICHT aufgerufen werden fuer Legacy-Profiles
    storage_with_node.get_node.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: 200 mit source='fallback' wenn Graph-Lookup fehlschlaegt
# ---------------------------------------------------------------------------


def test_get_entity_context_graph_lookup_failure_fallback(storage_node_not_found):
    store = _make_store(_PROFILE_WITH_ENTITY)
    app = _make_app(store, storage_node_not_found)

    with app.test_client() as client:
        resp = client.get(
            f"/api/simulation/{SIM_ID}/profiles/{USERNAME}/entity-context"
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    payload = data["data"]

    ctx = PersonaEntityContext.model_validate(payload)
    assert ctx.source == "fallback"
    assert ctx.entity_uuid == "ent-uuid-abc123"  # UUID bleibt erhalten
    assert ctx.entity_properties == {}
    assert ctx.relationships == []


# ---------------------------------------------------------------------------
# Test 6: 500 wenn neo4j_storage nicht initialisiert
# ---------------------------------------------------------------------------


def test_get_entity_context_500_when_storage_none():
    store = _make_store(_PROFILE_WITH_ENTITY)
    flask_app = Flask(__name__)
    flask_app.extensions["artifact_store"] = store
    flask_app.extensions["neo4j_storage"] = None  # explizit None
    flask_app.register_blueprint(simulation_bp, url_prefix="/api/simulation")

    with flask_app.test_client() as client:
        resp = client.get(
            f"/api/simulation/{SIM_ID}/profiles/{USERNAME}/entity-context"
        )

    assert resp.status_code == 500
    data = resp.get_json()
    assert data["success"] is False
    assert data["code"] == "internal_error"


# ---------------------------------------------------------------------------
# Test 7: Relationships werden korrekt gemappt
# ---------------------------------------------------------------------------


def test_get_entity_context_includes_relationships():
    """Wenn get_node_edges Edges liefert, werden sie als EntityRelationship zurueckgegeben."""
    # Edge-Format aus neo4j_mappings.edge_to_dict
    edge = {
        "uuid": "edge-001",
        "name": "WORKS_AT",
        "fact": "Max arbeitet bei Acme GmbH.",
        "source_node_uuid": "ent-uuid-abc123",
        "target_node_uuid": "org-uuid-xyz",
        "attributes": {},
        "created_at": None,
    }
    target_node = {
        "uuid": "org-uuid-xyz",
        "name": "Acme GmbH",
        "labels": ["Organization"],
        "summary": "Ein Berliner Technologieunternehmen.",
        "attributes": {},
    }

    mock = MagicMock(name="GraphStorage")
    # get_node: erstes call fuer source, zweites fuer target
    mock.get_node.side_effect = [_NODE_DICT, target_node]
    mock.get_node_edges.return_value = [edge]

    store = _make_store(_PROFILE_WITH_ENTITY)
    app = _make_app(store, mock)

    with app.test_client() as client:
        resp = client.get(
            f"/api/simulation/{SIM_ID}/profiles/{USERNAME}/entity-context"
        )

    assert resp.status_code == 200
    ctx = PersonaEntityContext.model_validate(resp.get_json()["data"])
    assert len(ctx.relationships) == 1
    rel = ctx.relationships[0]
    assert rel.relation_type == "WORKS_AT"
    assert rel.target_uuid == "org-uuid-xyz"
    assert rel.target_label == "Acme GmbH"
    assert rel.target_type == "Organization"
