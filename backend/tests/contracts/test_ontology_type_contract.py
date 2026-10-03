"""Issue #1759 (B1): Ontologie-Typ-Metadaten ``kind`` und ``actor_capable``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.ontology_type_contract import (
    ONTOLOGY_KIND_CONTESTED_TOPIC,
    OntologyTypeMetadata,
    contested_topic_type_names,
)


class TestMetadataDefaults:
    def test_legacy_type_without_fields_is_plain_actor_capable_entity(self):
        meta = OntologyTypeMetadata()
        assert meta.kind == "entity"
        assert meta.actor_capable is True

    def test_contested_topic_is_declared_via_kind(self):
        meta = OntologyTypeMetadata(kind=ONTOLOGY_KIND_CONTESTED_TOPIC)
        assert meta.kind == "contested_topic"

    def test_contested_topic_is_never_actor_capable(self):
        assert OntologyTypeMetadata(kind="contested_topic").actor_capable is False
        assert (
            OntologyTypeMetadata(kind="contested_topic", actor_capable=True).actor_capable
            is False
        )

    def test_plain_entity_may_be_declared_not_actor_capable(self):
        meta = OntologyTypeMetadata(kind="entity", actor_capable=False)
        assert meta.actor_capable is False

    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            OntologyTypeMetadata(kind="something_else")  # type: ignore[arg-type]

    def test_extra_fields_are_forbidden(self):
        with pytest.raises(ValidationError):
            OntologyTypeMetadata(kind="entity", unexpected=1)  # type: ignore[call-arg]


class TestContestedTopicTypeNames:
    def test_declared_topic_type_is_returned(self):
        ontology = {
            "entity_types": [
                {"name": "Measure", "kind": "contested_topic", "actor_capable": False},
                {"name": "Union", "kind": "entity"},
                {"name": "Person"},
            ],
            "edge_types": [],
        }
        assert contested_topic_type_names(ontology) == frozenset({"Measure"})

    def test_legacy_ontology_without_kind_has_no_topic_type(self):
        ontology = {"entity_types": [{"name": "Union"}, {"name": "Person"}]}
        assert contested_topic_type_names(ontology) == frozenset()

    @pytest.mark.parametrize(
        "ontology",
        [None, {}, {"entity_types": None}, {"entity_types": "x"}, {"entity_types": [1, None]}],
    )
    def test_missing_or_broken_structure_yields_empty_set(self, ontology):
        assert contested_topic_type_names(ontology) == frozenset()

    def test_multiple_topic_types_are_all_returned(self):
        ontology = {
            "entity_types": [
                {"name": "A", "kind": "contested_topic"},
                {"name": "B", "kind": "contested_topic"},
            ]
        }
        assert contested_topic_type_names(ontology) == frozenset({"A", "B"})


class TestOntologyTypeCatalog:
    """Issue #1759 (B2/B3): Eignung folgt der Typ-Definition."""

    def test_legacy_ontology_without_metadata_is_not_metadata_driven(self):
        from app.contracts.ontology_type_contract import ontology_type_catalog

        catalog = ontology_type_catalog({"entity_types": [{"name": "Person"}]})
        assert catalog.metadata_driven is False
        assert catalog.non_actor_reason("Person") is None

    def test_broken_structure_yields_empty_catalog(self):
        from app.contracts.ontology_type_contract import ontology_type_catalog

        assert ontology_type_catalog(None).metadata_driven is False
        assert ontology_type_catalog({"entity_types": "kaputt"}).metadata_driven is False

    def test_topic_and_non_actor_types_are_reported(self):
        from app.contracts.ontology_type_contract import ontology_type_catalog

        catalog = ontology_type_catalog(
            {
                "entity_types": [
                    {"name": "Measure", "kind": "contested_topic", "actor_capable": False},
                    {"name": "Hospital", "kind": "entity", "actor_capable": False},
                    {"name": "Person", "kind": "entity", "actor_capable": True},
                ]
            }
        )
        assert catalog.metadata_driven is True
        assert catalog.declared_types == frozenset({"measure", "hospital", "person"})
        assert "contested_topic" in (catalog.non_actor_reason("Measure") or "")
        assert "actor_capable=false" in (catalog.non_actor_reason("hospital") or "")
        assert catalog.non_actor_reason("Person") is None
