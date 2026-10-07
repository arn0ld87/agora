"""Endpunkt-Tests für ``app.api.graph_edit`` (Issue #1808, ADR-0022)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.contracts.simulation_record_contract import SimulationRecord
from app.storage.neo4j_edit import GraphEditConflict, GraphEditNotFound

GID = "abcdef0123456789abcdef0123456789"
U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
U2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
NOW = "2026-10-07T10:00:00+00:00"


def _node(uuid_: str = U1, name: str = "Alex", etype: str = "Person", origin: str | None = "manual"):
    return {
        "uuid": uuid_, "name": name, "labels": [etype], "entity_type": etype,
        "summary": f"{name} ({etype})", "attributes": {}, "created_at": NOW,
        "provenance": {"origin": origin, "changed_at": NOW if origin else None, "episode_count": 0},
    }


def _edge(uuid_: str = U2, origin: str | None = "manual", fact: str = "A kennt B."):
    return {
        "uuid": uuid_, "name": "KENNT", "fact": fact, "source_node_uuid": U1,
        "target_node_uuid": U2, "attributes": {}, "created_at": NOW, "valid_at": None,
        "invalid_at": None, "expired_at": None, "valid_from_round": None, "valid_to_round": None,
        "reinforced_count": 1, "episode_ids": [],
        "provenance": {"origin": origin, "changed_at": NOW if origin else None, "episode_count": 0},
    }


class _Storage:
    """In-Memory-Ersatz mit der Eindeutigkeit, die der API-Vertrag zusichert."""

    def __init__(self) -> None:
        self.ontology = {"entity_types": [{"name": "Person"}, {"name": "Organization"}]}
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.relations: Dict[str, Dict[str, Any]] = {}
        self.embed_calls = 0

    def get_ontology(self, graph_id):
        return self.ontology

    def edit_property_keys(self):
        return "embedding", "fact_embedding"

    def edit_embed_texts(self, texts):
        self.embed_calls += 1
        return [[0.1] for _ in texts]

    def edit_create_entity(self, **kw):
        if kw["entity_uuid"] in self.entities:
            return self.entities[kw["entity_uuid"]], False
        for existing in self.entities.values():
            if (existing["name"].lower(), existing["entity_type"]) == (
                kw["name"].lower(), kw["entity_type"],
            ):
                raise GraphEditConflict("Eine Entität mit diesem Namen und Typ existiert bereits")
        node = _node(kw["entity_uuid"], kw["name"], kw["entity_type"])
        self.entities[kw["entity_uuid"]] = node
        return node, True

    def edit_get_entity(self, graph_id, entity_uuid):
        return self.entities.get(entity_uuid)

    def edit_update_entity(self, **kw):
        node = dict(self.entities[kw["entity_uuid"]])
        node["name"] = kw["name"] or node["name"]
        node["provenance"] = {"origin": "edited", "changed_at": NOW, "episode_count": 0}
        self.entities[kw["entity_uuid"]] = node
        return node

    def edit_delete_entity(self, graph_id, entity_uuid):
        if entity_uuid not in self.entities:
            raise GraphEditNotFound(entity_uuid)
        del self.entities[entity_uuid]
        return 1

    def edit_merge_entities(self, **kw):
        return {"node": _node(kw["target_uuid"], origin="edited"),
                "merged_source_uuids": kw["source_uuids"], "rewired": 2, "dropped": 1}

    def edit_create_relation(self, **kw):
        if kw["relation_uuid"] in self.relations:
            return self.relations[kw["relation_uuid"]], False
        edge = _edge(kw["relation_uuid"], fact=kw["fact"])
        self.relations[kw["relation_uuid"]] = edge
        return edge, True

    def edit_get_relation(self, graph_id, relation_uuid):
        return self.relations.get(relation_uuid)

    def edit_update_relation(self, **kw):
        edge = dict(self.relations[kw["relation_uuid"]])
        edge["fact"] = kw["fact"] or edge["fact"]
        edge["provenance"] = {"origin": "edited", "changed_at": NOW, "episode_count": 0}
        self.relations[kw["relation_uuid"]] = edge
        return edge

    def edit_delete_relation(self, graph_id, relation_uuid):
        if relation_uuid not in self.relations:
            raise GraphEditNotFound(relation_uuid)
        del self.relations[relation_uuid]


class _SimRepo:
    def __init__(self, *records: SimulationRecord) -> None:
        self._records = list(records)

    def list(self, project_id=None):
        return list(self._records)


@pytest.fixture
def storage():
    return _Storage()


@pytest.fixture
def client(monkeypatch, storage):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    # Kein Simulationsbestand, keine Migration, sofern ein Test nichts anderes setzt
    monkeypatch.setattr("app.services.graph_lock._default_repository", lambda: _SimRepo())
    monkeypatch.setattr("app.services.graph_lock._default_project_lister", lambda: [])
    monkeypatch.setattr("app.api.graph_edit.embedding_migration_active", lambda: False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {"container": AgoraContainer(neo4j_storage=storage), "neo4j_storage": storage}
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return app.test_client()


def _create_body(**kw):
    body = {"client_request_id": str(uuid.uuid4()), "name": "Stadtwerke", "entity_type": "Organization"}
    body.update(kw)
    return body


# ── Erfolg ─────────────────────────────────────────────────────────────────


def test_create_entity_returns_201_with_manual_provenance(client):
    response = client.post(f"/api/graph/{GID}/entities", json=_create_body())

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["name"] == "Stadtwerke"
    assert data["entity_type"] == "Organization"
    assert data["provenance"]["origin"] == "manual"


def test_repeated_create_with_same_client_request_id_creates_no_second_element(client, storage):
    body = _create_body()
    first = client.post(f"/api/graph/{GID}/entities", json=body)
    second = client.post(f"/api/graph/{GID}/entities", json=body)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["data"]["uuid"] == second.get_json()["data"]["uuid"]
    assert len(storage.entities) == 1


def test_repeated_relation_create_with_same_client_request_id_creates_no_second_element(client, storage):
    body = {"client_request_id": str(uuid.uuid4()), "source_uuid": U1, "target_uuid": U2,
            "name": "KENNT", "fact": "A kennt B."}
    first = client.post(f"/api/graph/{GID}/relations", json=body)
    second = client.post(f"/api/graph/{GID}/relations", json=body)

    assert (first.status_code, second.status_code) == (201, 200)
    assert len(storage.relations) == 1
    assert first.get_json()["data"]["episode_ids"] == []


def test_update_entity_returns_edited(client, storage):
    storage.entities[U1] = _node(origin=None)

    response = client.patch(f"/api/graph/{GID}/entities/{U1}", json={"name": "Alexander"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name"] == "Alexander"
    assert data["provenance"]["origin"] == "edited"


def test_delete_entity_reports_removed_relations(client, storage):
    storage.entities[U1] = _node()

    response = client.delete(f"/api/graph/{GID}/entities/{U1}")

    assert response.status_code == 200
    assert response.get_json()["data"] == {"uuid": U1, "removed_relation_count": 1}


def test_merge_returns_counts(client):
    response = client.post(
        f"/api/graph/{GID}/entities/merge", json={"target_uuid": U1, "source_uuids": [U2]}
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["merged_source_uuids"] == [U2]
    assert (data["rewired_relation_count"], data["dropped_relation_count"]) == (2, 1)
    assert data["target"]["provenance"]["origin"] == "edited"


def test_update_and_delete_relation(client, storage):
    storage.relations[U2] = _edge(origin=None)

    patched = client.patch(f"/api/graph/{GID}/relations/{U2}", json={"fact": "Neuer Fakt."})
    deleted = client.delete(f"/api/graph/{GID}/relations/{U2}")

    assert patched.status_code == 200
    assert patched.get_json()["data"]["provenance"]["origin"] == "edited"
    assert deleted.status_code == 200
    assert storage.relations == {}


def test_lock_endpoint_reports_free_and_locked(client, monkeypatch):
    free = client.get(f"/api/graph/{GID}/lock")
    assert free.status_code == 200
    assert free.get_json()["data"] == {"graph_id": GID, "locked": False, "used_by": []}

    record = SimulationRecord(simulation_id="sim_0123456789ab", graph_id=GID, status="completed")
    monkeypatch.setattr("app.services.graph_lock._default_repository", lambda: _SimRepo(record))
    locked = client.get(f"/api/graph/{GID}/lock")
    data = locked.get_json()["data"]
    assert data["locked"] is True
    assert data["used_by"][0]["simulation_id"] == "sim_0123456789ab"


def test_get_graph_ontology(client):
    response = client.get(f"/api/graph/{GID}/ontology")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "entity_types" in data["data"]
    assert "Person" in data["data"]["entity_types"]
    assert "Organization" in data["data"]["entity_types"]


# ── Validierungsfehler ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"client_request_id": "keine-uuid", "name": "A", "entity_type": "Person"},
        _create_body(name="   "),
        _create_body(extra_field=1),
    ],
    ids=["leer", "request_id", "name_leer", "unbekanntes_feld"],
)
def test_create_entity_validation_errors_return_400(client, body):
    response = client.post(f"/api/graph/{GID}/entities", json=body)

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "validation_failed"
    assert payload["errors"]


def test_non_object_body_returns_400(client):
    response = client.post(f"/api/graph/{GID}/entities", json=[1, 2])
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_unknown_ontology_type_returns_400(client):
    response = client.post(f"/api/graph/{GID}/entities", json=_create_body(entity_type="Planet"))
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_empty_update_returns_400(client):
    response = client.patch(f"/api/graph/{GID}/entities/{U1}", json={})
    assert response.status_code == 400


def test_invalid_ids_return_invalid_id(client):
    assert client.post("/api/graph/not-valid/entities", json=_create_body()).get_json()["code"] == "invalid_id"
    assert client.delete(f"/api/graph/{GID}/entities/nicht-uuid").get_json()["code"] == "invalid_id"
    assert client.patch(f"/api/graph/{GID}/relations/x", json={"fact": "a"}).status_code == 400
    assert client.get("/api/graph/not-valid/lock").status_code == 400


def test_unknown_entity_returns_404(client):
    response = client.delete(f"/api/graph/{GID}/entities/{U1}")
    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


# ── Sperre, Kollision, Migration, Einbettung ───────────────────────────────


def test_locked_graph_returns_409_for_every_write(client, storage, monkeypatch):
    record = SimulationRecord(simulation_id="sim_0123456789ab", graph_id=GID, status="running")
    monkeypatch.setattr("app.services.graph_lock._default_repository", lambda: _SimRepo(record))
    storage.entities[U1] = _node()
    storage.relations[U2] = _edge()

    responses = [
        client.post(f"/api/graph/{GID}/entities", json=_create_body()),
        client.patch(f"/api/graph/{GID}/entities/{U1}", json={"name": "X"}),
        client.delete(f"/api/graph/{GID}/entities/{U1}"),
        client.post(f"/api/graph/{GID}/entities/merge", json={"target_uuid": U1, "source_uuids": [U2]}),
        client.post(f"/api/graph/{GID}/relations", json={
            "client_request_id": str(uuid.uuid4()), "source_uuid": U1, "target_uuid": U2,
            "name": "K", "fact": "f"}),
        client.patch(f"/api/graph/{GID}/relations/{U2}", json={"fact": "neu"}),
        client.delete(f"/api/graph/{GID}/relations/{U2}"),
    ]

    for response in responses:
        assert response.status_code == 409
        body = response.get_json()
        assert body["code"] == "graph_locked"
        assert body["used_by"][0]["simulation_id"] == "sim_0123456789ab"
    # nichts geschrieben, nichts eingebettet
    assert set(storage.entities) == {U1}
    assert set(storage.relations) == {U2}
    assert storage.embed_calls == 0


def test_collision_returns_409_graph_edit_conflict(client):
    assert client.post(f"/api/graph/{GID}/entities", json=_create_body()).status_code == 201

    response = client.post(f"/api/graph/{GID}/entities", json=_create_body())  # neue request_id, gleicher Name/Typ

    assert response.status_code == 409
    assert response.get_json()["code"] == "graph_edit_conflict"


def test_running_embedding_migration_returns_409_with_own_code(client, storage, monkeypatch):
    monkeypatch.setattr("app.api.graph_edit.embedding_migration_active", lambda: True)

    response = client.post(f"/api/graph/{GID}/entities", json=_create_body())

    assert response.status_code == 409
    assert response.get_json()["code"] == "embedding_migration_running"
    assert storage.entities == {}


def test_embedding_failure_returns_503_and_writes_nothing(client, storage, monkeypatch):
    def _boom(texts):
        raise RuntimeError("Endpoint down")

    monkeypatch.setattr(storage, "edit_embed_texts", _boom)

    response = client.post(f"/api/graph/{GID}/entities", json=_create_body())

    assert response.status_code == 503
    assert response.get_json()["code"] == "service_unavailable"
    assert storage.entities == {}


def test_default_migration_check_reads_job_states(monkeypatch):
    """``embedding_migration_active`` wertet pending/running/validating aus."""
    from app.services import graph_edit_service as module

    jobs = [SimpleNamespace(status="completed"), SimpleNamespace(status="running")]

    class _Svc:
        def __init__(self, **_kw):
            pass

        def list_jobs(self):
            return jobs

    monkeypatch.setattr("app.services.embedding_migration.EmbeddingMigrationService", _Svc)
    assert module.embedding_migration_active() is True
    jobs[:] = [SimpleNamespace(status="completed"), SimpleNamespace(status="failed")]
    assert module.embedding_migration_active() is False
