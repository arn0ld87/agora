"""Vertragstests für ``graph_edit_contract`` (Issue #1808, ADR-0022)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.contracts.graph_edit_contract import (
    EntityCreate,
    EntityMerge,
    EntityUpdate,
    GraphEdgeView,
    GraphLockState,
    GraphLockUser,
    GraphNodeView,
    GraphProvenanceInfo,
    RelationCreate,
    RelationUpdate,
)


def _rid() -> str:
    return str(uuid.uuid4())


class TestEntityCreate:
    def test_valid_request_strips_whitespace_and_dedupes_aliases(self):
        model = EntityCreate(
            client_request_id=_rid(),
            name="  Stadtwerke  ",
            entity_type=" Organization ",
            aliases=["SW", "sw", " Stadtwerke AG "],
        )
        assert model.name == "Stadtwerke"
        assert model.entity_type == "Organization"
        assert model.aliases == ["SW", "Stadtwerke AG"]
        assert model.summary == ""

    @pytest.mark.parametrize("name", ["", "   "])
    def test_rejects_empty_name(self, name):
        with pytest.raises(ValidationError):
            EntityCreate(client_request_id=_rid(), name=name, entity_type="Person")

    def test_rejects_overlong_name(self):
        with pytest.raises(ValidationError):
            EntityCreate(client_request_id=_rid(), name="x" * 201, entity_type="Person")

    def test_rejects_non_uuid_client_request_id(self):
        with pytest.raises(ValidationError):
            EntityCreate(client_request_id="nicht-eine-uuid", name="A", entity_type="Person")

    def test_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            EntityCreate.model_validate(
                {"client_request_id": _rid(), "name": "A", "entity_type": "P", "uuid": _rid()}
            )

    def test_rejects_too_many_aliases(self):
        with pytest.raises(ValidationError):
            EntityCreate(
                client_request_id=_rid(),
                name="A",
                entity_type="Person",
                aliases=[f"a{i}" for i in range(21)],
            )


class TestEntityUpdate:
    def test_requires_at_least_one_field(self):
        with pytest.raises(ValidationError):
            EntityUpdate()

    def test_rejects_explicit_null(self):
        with pytest.raises(ValidationError):
            EntityUpdate.model_validate({"name": None})

    def test_partial_update_keeps_unset_fields_out(self):
        model = EntityUpdate(summary="neu")
        assert model.model_fields_set == {"summary"}

    def test_empty_alias_list_is_allowed_to_clear_aliases(self):
        model = EntityUpdate(aliases=[])
        assert model.aliases == []


class TestEntityMerge:
    def test_valid(self):
        target, source = _rid(), _rid()
        model = EntityMerge(target_uuid=target, source_uuids=[source])
        assert model.source_uuids == [source]

    def test_target_must_not_be_source(self):
        target = _rid()
        with pytest.raises(ValidationError):
            EntityMerge(target_uuid=target, source_uuids=[target])

    def test_sources_must_be_distinct(self):
        source = _rid()
        with pytest.raises(ValidationError):
            EntityMerge(target_uuid=_rid(), source_uuids=[source, source])

    def test_requires_a_source(self):
        with pytest.raises(ValidationError):
            EntityMerge(target_uuid=_rid(), source_uuids=[])


class TestRelation:
    def test_create_rejects_self_loop(self):
        same = _rid()
        with pytest.raises(ValidationError):
            RelationCreate(
                client_request_id=_rid(), source_uuid=same, target_uuid=same, name="KENNT", fact="x"
            )

    def test_create_rejects_blank_fact(self):
        with pytest.raises(ValidationError):
            RelationCreate(
                client_request_id=_rid(),
                source_uuid=_rid(),
                target_uuid=_rid(),
                name="KENNT",
                fact="   ",
            )

    def test_update_requires_a_field(self):
        with pytest.raises(ValidationError):
            RelationUpdate()

    def test_update_accepts_fact_only(self):
        assert RelationUpdate(fact="neu").model_fields_set == {"fact"}


class TestViews:
    def test_provenance_default_is_extracted(self):
        info = GraphProvenanceInfo()
        assert info.origin is None
        assert info.changed_at is None
        assert info.episode_count == 0

    def test_provenance_rejects_unknown_origin(self):
        with pytest.raises(ValidationError):
            GraphProvenanceInfo(origin="extracted")

    def test_node_view_accepts_storage_dict_with_iso_timestamps(self):
        node = GraphNodeView.model_validate(
            {
                "uuid": _rid(),
                "name": "A",
                "labels": ["Person"],
                "entity_type": "Person",
                "summary": "",
                "attributes": {},
                "created_at": "2026-10-07T10:00:00+00:00",
                "provenance": {
                    "origin": "manual",
                    "changed_at": "2026-10-07T10:00:00+00:00",
                    "episode_count": 0,
                },
            }
        )
        assert node.provenance.origin == "manual"
        assert node.created_at is not None

    def test_edge_view_defaults_without_provenance(self):
        edge = GraphEdgeView(
            uuid=_rid(), name="KENNT", source_node_uuid=_rid(), target_node_uuid=_rid()
        )
        assert edge.provenance.origin is None
        assert edge.episode_ids == []


class TestLockState:
    def test_unlocked(self):
        state = GraphLockState(graph_id="g", locked=False)
        assert state.used_by == []

    def test_locked_carries_users(self):
        state = GraphLockState(
            graph_id="g",
            locked=True,
            used_by=[GraphLockUser(simulation_id="sim_0123456789ab", status="completed")],
        )
        assert state.used_by[0].simulation_id == "sim_0123456789ab"
