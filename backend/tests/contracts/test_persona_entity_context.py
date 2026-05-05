"""Contract-Tests fuer persona_entity_context.py (Issue #69, EPIC-13-ST-02).

Vertragsgarantien:
- Pflichtfelder valide
- extra="forbid" abgelehnt
- entity_properties akzeptiert nur Skalare
- source ist ein Literal
- EntityRelationship strict getypt
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.persona_entity_context import EntityRelationship, PersonaEntityContext


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)


def _make_rel(**overrides) -> EntityRelationship:
    data = dict(
        relation_type="WORKS_AT",
        target_uuid="node-uuid-001",
        target_label="Muster GmbH",
        target_type="Organization",
    )
    data.update(overrides)
    return EntityRelationship(**data)


def _make_context(**overrides) -> PersonaEntityContext:
    data = dict(
        username="test_user",
        simulation_id="sim_aabbccdd0011",
        entity_uuid="ent-uuid-0001",
        entity_label="Max Mustermann",
        entity_type="PERSON",
        entity_summary="Ein typischer Vertreter der Berliner Startup-Szene.",
        entity_properties={"age": 32, "city": "Berlin"},
        relationships=[_make_rel()],
        generated_at=_NOW,
        source="graph",
    )
    data.update(overrides)
    return PersonaEntityContext(**data)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_minimal_valid_persona_entity_context_validates():
    """Alle Pflichtfelder gesetzt — muss ohne ValidationError validen."""
    ctx = _make_context()
    assert ctx.username == "test_user"
    assert ctx.source == "graph"
    assert isinstance(ctx.relationships, list)
    assert ctx.relationships[0].relation_type == "WORKS_AT"


def test_extra_fields_rejected():
    """extra='forbid' — unbekanntes Feld muss ValidationError ausloesen."""
    with pytest.raises(ValidationError, match="bogus"):
        PersonaEntityContext(
            username="u",
            simulation_id="sim_aabbccdd0011",
            entity_uuid="ent-001",
            entity_label="X",
            entity_type="PERSON",
            generated_at=_NOW,
            bogus="verboten",
        )


def test_extra_fields_rejected_relationship():
    """extra='forbid' auf EntityRelationship."""
    with pytest.raises(ValidationError):
        EntityRelationship(
            relation_type="FOLLOWS",
            target_uuid="node-002",
            target_label="Someone",
            unexpected_field="nein",
        )


def test_relationships_typed():
    """list[EntityRelationship] muss strict mit dem Vertrag valide sein."""
    rel = _make_rel(relation_type="OPPOSES", target_type=None)
    assert rel.target_type is None

    ctx = _make_context(relationships=[rel])
    dumped = ctx.model_dump()
    restored = PersonaEntityContext.model_validate(dumped)
    assert restored.relationships[0].relation_type == "OPPOSES"
    assert restored.relationships[0].target_type is None


def test_entity_properties_only_scalars():
    """entity_properties mit komplexem Typ (list) muss ValidationError ausloesen."""
    with pytest.raises(ValidationError):
        PersonaEntityContext(
            username="u",
            simulation_id="sim_aabbccdd0011",
            entity_uuid="ent-001",
            entity_label="X",
            entity_type="PERSON",
            generated_at=_NOW,
            entity_properties={"k": ["a", "b"]},  # type: ignore[dict-item]
        )


def test_source_literal_constrained():
    """source='invalid' muss ValidationError ausloesen (Literal-Constraint)."""
    with pytest.raises(ValidationError):
        PersonaEntityContext(
            username="u",
            simulation_id="sim_aabbccdd0011",
            entity_uuid="ent-001",
            entity_label="X",
            entity_type="PERSON",
            generated_at=_NOW,
            source="invalid",  # type: ignore[arg-type]
        )

    # Beide validen Literale akzeptiert
    for valid_src in ("graph", "fallback"):
        ctx = _make_context(source=valid_src)  # type: ignore[arg-type]
        assert ctx.source == valid_src


def test_round_trip_json():
    """model_dump(mode='json') -> model_validate muss identisches Objekt liefern."""
    original = _make_context()
    dumped = original.model_dump(mode="json")
    restored = PersonaEntityContext.model_validate(dumped)
    assert original.entity_uuid == restored.entity_uuid
    assert original.entity_label == restored.entity_label
    assert original.relationships[0].target_label == restored.relationships[0].target_label


def test_schema_idempotent():
    """model_json_schema() zweimal aufrufen muss identisches Dict liefern."""
    s1 = PersonaEntityContext.model_json_schema()
    s2 = PersonaEntityContext.model_json_schema()
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)


def test_fallback_source_with_empty_entity_uuid():
    """source='fallback' ist valide auch wenn entity_uuid leer ist (Legacy-Personas)."""
    ctx = _make_context(entity_uuid="", source="fallback", entity_properties={}, relationships=[])
    assert ctx.source == "fallback"
    assert ctx.entity_uuid == ""
