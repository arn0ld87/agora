"""Fachregeln des ``GraphEditService`` (Issue #1808, ADR-0022)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.contracts.graph_edit_contract import (
    EntityCreate,
    EntityMerge,
    EntityUpdate,
    GraphLockState,
    RelationCreate,
    RelationUpdate,
)
from app.services.graph_edit_service import (
    EmbeddingMigrationRunningError,
    GraphEditEmbeddingError,
    GraphEditNotFound,
    GraphEditService,
    GraphEditValidationError,
    GraphLockedError,
    derive_element_uuid,
)

GID = "11111111-1111-4111-8111-111111111111"
RID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
U2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
NOW = "2026-10-07T10:00:00+00:00"


def _node(name="Alex", etype="Person", summary=None, **kw) -> Dict[str, Any]:
    return {
        "uuid": U1, "name": name, "labels": [etype], "entity_type": etype,
        "summary": summary if summary is not None else f"{name} ({etype})",
        "attributes": kw.get("attributes", {}), "created_at": NOW,
        "provenance": {"origin": kw.get("origin"), "changed_at": None, "episode_count": 0},
    }


def _edge(**kw) -> Dict[str, Any]:
    return {
        "uuid": U2, "name": kw.get("name", "KENNT"), "fact": kw.get("fact", "A kennt B."),
        "source_node_uuid": U1, "target_node_uuid": U2, "attributes": {}, "created_at": NOW,
        "valid_at": None, "invalid_at": None, "expired_at": None, "valid_from_round": None,
        "valid_to_round": None, "reinforced_count": 1, "episode_ids": ["ep-1"],
        "provenance": {"origin": None, "changed_at": None, "episode_count": 1},
    }


class _FakeStorage:
    def __init__(self) -> None:
        self.ontology = {"entity_types": [{"name": "Person"}, {"name": "Organization"}]}
        self.entity = _node()
        self.relation = _edge()
        self.embedded: List[str] = []
        self.embed_error: Exception | None = None
        self.calls: List[tuple[str, Dict[str, Any]]] = []

    def get_ontology(self, graph_id):
        return self.ontology

    def edit_property_keys(self):
        return "embedding", "fact_embedding"

    def edit_embed_texts(self, texts):
        if self.embed_error:
            raise self.embed_error
        self.embedded.extend(texts)
        return [[0.1, 0.2] for _ in texts]

    def edit_get_entity(self, graph_id, entity_uuid):
        return self.entity

    def edit_get_relation(self, graph_id, relation_uuid):
        return self.relation

    def edit_create_entity(self, **kw):
        self.calls.append(("create_entity", kw))
        return _node(kw["name"], kw["entity_type"], summary=kw["summary"], origin="manual"), True

    def edit_update_entity(self, **kw):
        self.calls.append(("update_entity", kw))
        return _node(kw["name"] or "Alex", kw["entity_type"] or "Person", origin="edited")

    def edit_delete_entity(self, graph_id, entity_uuid):
        self.calls.append(("delete_entity", {"uuid": entity_uuid}))
        return 2

    def edit_merge_entities(self, **kw):
        self.calls.append(("merge", kw))
        return {"node": _node(origin="edited"), "merged_source_uuids": kw["source_uuids"],
                "rewired": 1, "dropped": 0}

    def edit_create_relation(self, **kw):
        self.calls.append(("create_relation", kw))
        return _edge(name=kw["name"], fact=kw["fact"]), True

    def edit_update_relation(self, **kw):
        self.calls.append(("update_relation", kw))
        return _edge(name=kw["name"] or "KENNT", fact=kw["fact"] or "A kennt B.")

    def edit_delete_relation(self, graph_id, relation_uuid):
        self.calls.append(("delete_relation", {"uuid": relation_uuid}))


def _service(storage=None, *, locked=False, migrating=False):
    storage = storage or _FakeStorage()

    def lock_check(graph_id):
        if locked:
            raise GraphLockedError(GraphLockState(graph_id=graph_id, locked=True))

    return GraphEditService(
        storage, lock_check=lock_check, migration_active=lambda: migrating, clock=lambda: NOW
    ), storage


# ── Sperre und Migration ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.create_entity(GID, EntityCreate(client_request_id=RID, name="A", entity_type="Person")),
        lambda s: s.update_entity(GID, U1, EntityUpdate(summary="x")),
        lambda s: s.delete_entity(GID, U1),
        lambda s: s.merge_entities(GID, EntityMerge(target_uuid=U1, source_uuids=[U2])),
        lambda s: s.create_relation(
            GID, RelationCreate(client_request_id=RID, source_uuid=U1, target_uuid=U2, name="K", fact="f")
        ),
        lambda s: s.update_relation(GID, U2, RelationUpdate(fact="neu")),
        lambda s: s.delete_relation(GID, U2),
    ],
    ids=["create_entity", "update_entity", "delete_entity", "merge", "create_relation",
         "update_relation", "delete_relation"],
)
class TestEveryWriteIsGuarded:
    def test_locked_graph_rejects_before_any_write(self, call):
        service, storage = _service(locked=True)
        with pytest.raises(GraphLockedError):
            call(service)
        assert storage.calls == []
        assert storage.embedded == []

    def test_running_embedding_migration_rejects_before_any_write(self, call):
        service, storage = _service(migrating=True)
        with pytest.raises(EmbeddingMigrationRunningError):
            call(service)
        assert storage.calls == []
        assert storage.embedded == []


# ── Entitäten ────────────────────────────────────────────────────────────


class TestCreateEntity:
    def test_uses_ingestion_embedding_text_and_default_summary(self):
        service, storage = _service()
        view, created = service.create_entity(
            GID, EntityCreate(client_request_id=RID, name="Stadtwerke", entity_type="Organization")
        )
        assert created is True
        assert storage.embedded == ["Stadtwerke (Organization)"]
        _name, kw = storage.calls[0]
        assert kw["summary"] == "Stadtwerke (Organization)"
        assert kw["property_key"] == "embedding"
        assert kw["now"] == NOW
        assert view.provenance.origin == "manual"

    def test_uuid_is_derived_from_client_request_id(self):
        service, storage = _service()
        request = EntityCreate(client_request_id=RID, name="A", entity_type="Person")
        service.create_entity(GID, request)
        service.create_entity(GID, request)
        first, second = storage.calls[0][1]["entity_uuid"], storage.calls[1][1]["entity_uuid"]
        assert first == second == derive_element_uuid("entity", GID, RID)
        assert derive_element_uuid("entity", GID, RID) != derive_element_uuid("relation", GID, RID)
        assert derive_element_uuid("entity", GID, RID) != derive_element_uuid("entity", "other", RID)

    def test_type_must_be_in_ontology(self):
        service, storage = _service()
        with pytest.raises(GraphEditValidationError):
            service.create_entity(
                GID, EntityCreate(client_request_id=RID, name="A", entity_type="Planet")
            )
        assert storage.calls == []

    def test_graph_without_ontology_is_rejected(self):
        storage = _FakeStorage()
        storage.ontology = {}
        service, _ = _service(storage)
        with pytest.raises(GraphEditValidationError):
            service.create_entity(
                GID, EntityCreate(client_request_id=RID, name="A", entity_type="Person")
            )

    def test_embedding_failure_writes_nothing(self):
        storage = _FakeStorage()
        storage.embed_error = RuntimeError("Endpoint down")
        service, _ = _service(storage)
        with pytest.raises(GraphEditEmbeddingError):
            service.create_entity(
                GID, EntityCreate(client_request_id=RID, name="A", entity_type="Person")
            )
        assert storage.calls == []


class TestUpdateEntity:
    def test_name_change_reembeds_and_follows_default_summary(self):
        service, storage = _service()
        service.update_entity(GID, U1, EntityUpdate(name="Alexander"))
        assert storage.embedded == ["Alexander (Person)"]
        kw = storage.calls[0][1]
        assert kw["embedding_text"] == "Alexander (Person)"
        assert kw["summary"] == "Alexander (Person)"

    def test_hand_written_summary_is_kept_on_rename(self):
        storage = _FakeStorage()
        storage.entity = _node(summary="Leiter der Abteilung")
        service, _ = _service(storage)
        service.update_entity(GID, U1, EntityUpdate(name="Alexander"))
        assert storage.calls[0][1]["summary"] is None

    def test_type_change_requires_ontology_type_and_reembeds(self):
        service, storage = _service()
        service.update_entity(GID, U1, EntityUpdate(entity_type="Organization"))
        assert storage.embedded == ["Alex (Organization)"]
        with pytest.raises(GraphEditValidationError):
            service.update_entity(GID, U1, EntityUpdate(entity_type="Planet"))

    def test_summary_or_alias_change_does_not_reembed(self):
        service, storage = _service()
        service.update_entity(GID, U1, EntityUpdate(summary="neu", aliases=["Al"]))
        assert storage.embedded == []
        kw = storage.calls[0][1]
        assert kw["embedding"] is None and kw["embedding_text"] is None

    def test_unchanged_values_write_nothing(self):
        service, storage = _service()
        view = service.update_entity(GID, U1, EntityUpdate(name="Alex", entity_type="Person"))
        assert storage.calls == []
        assert view.provenance.origin is None  # bleibt extrahiert

    def test_unknown_entity_is_not_found(self):
        storage = _FakeStorage()
        storage.entity = None
        service, _ = _service(storage)
        with pytest.raises(GraphEditNotFound):
            service.update_entity(GID, U1, EntityUpdate(summary="x"))

    def test_embedding_failure_writes_nothing(self):
        storage = _FakeStorage()
        storage.embed_error = RuntimeError("down")
        service, _ = _service(storage)
        with pytest.raises(GraphEditEmbeddingError):
            service.update_entity(GID, U1, EntityUpdate(name="Neu"))
        assert storage.calls == []


class TestDeleteAndMerge:
    def test_delete_reports_removed_relations(self):
        service, _ = _service()
        result = service.delete_entity(GID, U1)
        assert (result.uuid, result.removed_relation_count) == (U1, 2)

    def test_merge_does_not_embed_and_reports_counts(self):
        service, storage = _service()
        result = service.merge_entities(GID, EntityMerge(target_uuid=U1, source_uuids=[U2]))
        assert storage.embedded == []
        assert result.merged_source_uuids == [U2]
        assert result.rewired_relation_count == 1
        assert result.target.provenance.origin == "edited"


# ── Beziehungen ──────────────────────────────────────────────────────────


class TestRelations:
    def test_create_embeds_the_fact_and_has_no_episodes(self):
        service, storage = _service()
        view, created = service.create_relation(
            GID,
            RelationCreate(client_request_id=RID, source_uuid=U1, target_uuid=U2, name="FINANZIERT",
                           fact="A finanziert B."),
        )
        assert created is True
        assert storage.embedded == ["A finanziert B."]
        assert storage.calls[0][1]["property_key"] == "fact_embedding"
        assert storage.calls[0][1]["relation_uuid"] == derive_element_uuid("relation", GID, RID)
        assert view.name == "FINANZIERT"

    def test_fact_change_reembeds_name_change_does_not(self):
        service, storage = _service()
        service.update_relation(GID, U2, RelationUpdate(fact="Neuer Fakt."))
        assert storage.embedded == ["Neuer Fakt."]
        service.update_relation(GID, U2, RelationUpdate(name="LEITET"))
        assert storage.embedded == ["Neuer Fakt."]  # keine zweite Einbettung

    def test_unchanged_update_writes_nothing(self):
        service, storage = _service()
        service.update_relation(GID, U2, RelationUpdate(name="KENNT", fact="A kennt B."))
        assert storage.calls == []

    def test_delete_relation(self):
        service, storage = _service()
        assert service.delete_relation(GID, U2).uuid == U2
        assert storage.calls[0][0] == "delete_relation"
