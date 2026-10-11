"""Issue #1833 — Charakterisierung der Befunde aus dem Referenzlauf.

Diese Tests halten den Istzustand fest, sie ändern kein Verhalten und sind kein
Sollwert. Referenzlauf: ``sim_c56d9430b50a`` (Deployment ``328d2b8d``, enthält
#1759, #1713 und #1471 bereits). Alle Fixtures sind synthetisch und frei
erfunden; kein Test liest Laufartefakte oder greift auf einen Remote-Host zu.

Befunde und offene Entscheidungen (Vorschläge, keine Maintainer-Entscheidung):

1. **Klinikträger wird Einzelperson.** ``Kliniken Hollerau gGmbH`` hat im Graph
   den Typ ``HospitalOperator``; der Typ-Kopf ``operator`` steht in
   ``_PERSON_TYPE_HEADS``, deshalb gilt er als Personentyp und nicht als
   Kollektiv. Offen: Rechtsform-Namensregel oder ``operator`` aus
   ``_PERSON_TYPE_HEADS`` streichen.
2. **Drei Agenten ohne Profil.** ``Hollerau``/``Kleinwiese`` (``Organization``)
   und ``Rettungsdienst Landkreis Hollerau`` (``EmergencyService``) bestehen den
   Eignungsfilter. Weist der Generator eine Entität ab und gibt es keine Reserve,
   bleibt die Profilliste kürzer als die Entitätenliste; ``_phase_generate_profiles``
   gibt die Entitätenliste trotzdem als ``expanded_entities`` an die
   Konfiguration weiter. Offen: Agent streichen oder Profil erzwingen.
3. **Alias-Varianten bleiben getrennt.** ``Hollerau-Nord`` / ``Klinikum
   Hollerau-Nord`` und ``Hollerau-Süd (Brenkhausen)`` / ``Kreiskrankenhaus
   Hollerau-Süd`` werden von der bestehenden deterministischen Auflösung nicht
   zusammengeführt (anderes Kopf-Nomen). Keine neue Heuristik.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.entity_alias_resolution import resolve_aliases
from app.services.entity_reader import EntityNode
from app.services.entity_semantic_class import SemanticEntityClass, classify_entity
from app.services.oasis_profile_generator import OasisProfileGenerator, PersonaDemographicSlot
from app.services.persona_eligibility import filter_eligible_entities
from app.services.persona_identity_binding import resolve_identity_binding
from app.services.prepare_entities import _merge_entity_variants


@pytest.fixture()
def generator():
    return OasisProfileGenerator(api_key="test", base_url="http://localhost", language="de")


def _entity(name: str, entity_type: str, uuid: str | None = None) -> EntityNode:
    return EntityNode(
        uuid=uuid or f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=f"{name} im Kontext der Klinikschließung.",
        attributes={},
    )


def test_hospital_operator_ggmbh_is_currently_an_individual_representative(generator):
    """Istzustand, kein Sollwert: der Klinikträger wird eine erfundene Einzelperson."""
    entity = _entity("Kliniken Hollerau gGmbH", "HospitalOperator")

    assert classify_entity(entity.name, "HospitalOperator") is SemanticEntityClass.PERSON
    assert generator._is_group_entity("HospitalOperator") is False

    binding = resolve_identity_binding(
        entity_uuid=entity.uuid,
        entity_name=entity.name,
        entity_type="HospitalOperator",
        attributes=entity.attributes,
        summary=entity.summary,
        is_collective_type=generator._is_group_entity("HospitalOperator"),
    )
    assert binding.origin == "synthetic_representative"
    assert binding.name_is_locked is False

    def fake(**kwargs: Any) -> dict[str, Any]:
        return {
            "display_name": "Tobias Neumann",
            "handle": "tobias_neumann",
            "persona": "Tobias Neumann, 35, arbeitet als Notfallsanitäter in Hollerau.",
            "bio": "Notfallsanitäter, Hollerau",
            "profession": "Notfallsanitäter",
            "interested_topics": [],
        }

    generator._generate_profile_with_llm = fake  # type: ignore[method-assign]
    profile = generator.generate_profile_from_entity(
        entity,
        user_id=1,
        use_llm=True,
        demographic_slot=PersonaDemographicSlot(age=35, gender="male", mbti="ESTJ"),
    )
    assert profile.persona_kind == "individual"
    assert profile.name == "Tobias Neumann"
    assert profile.identity_binding is not None
    assert profile.identity_binding["origin"] == "synthetic_representative"


@pytest.mark.parametrize(
    ("entity_type", "is_collective_today"),
    [
        ("HospitalCarrier", False),
        ("ClinicProvider", False),
        ("Organization", True),
        ("Hospital", True),
    ],
)
def test_collective_type_comparison_cases_are_characterised(
    generator, entity_type, is_collective_today
):
    """Istzustand, kein Sollwert: welcher Typ heute als Kollektiv gilt."""
    assert generator._is_group_entity(entity_type) is is_collective_today


def test_agents_without_profile_are_characterised(generator):
    """Istzustand, kein Sollwert: abgewiesene Entität ohne Reserve ergibt kein Profil."""
    entities = [
        _entity("Hollerau", "Organization"),
        _entity("Kleinwiese", "Organization"),
        _entity("Rettungsdienst Landkreis Hollerau", "EmergencyService"),
    ]

    eligibility = filter_eligible_entities(entities)
    assert [e.name for e in eligibility.eligible] == [e.name for e in entities]
    assert eligibility.exclusions == [], "der Eignungsfilter schließt keine der drei aus"

    def fake(**kwargs: Any) -> dict[str, Any]:
        if kwargs["entity_name"] == "Kleinwiese":
            return {"ineligible": True, "ineligible_reason": "Ortsname, kein Träger"}
        return {
            "bio": "Organisation in Hollerau",
            "persona": f"{kwargs['entity_name']} äußert sich als Organisation.",
            "country": "DE",
            "interested_topics": [],
            "voice_register": "neutral-de",
        }

    generator._generate_profile_with_llm = fake  # type: ignore[method-assign]
    slots = [PersonaDemographicSlot(age=30 + i, gender="female", mbti="ISFJ") for i in range(3)]

    profiles = generator.generate_profiles_from_entities(
        entities=entities,
        use_llm=True,
        parallel_count=1,
        demographic_slots=slots,
        reserve_entities=[],
    )

    assert len(profiles) == 2
    assert len(profiles) < len(entities)
    assert "Kleinwiese" not in {p.name for p in profiles}


@pytest.mark.parametrize(
    ("short_name", "long_name"),
    [
        ("Hollerau-Nord", "Klinikum Hollerau-Nord"),
        ("Hollerau-Süd (Brenkhausen)", "Kreiskrankenhaus Hollerau-Süd"),
    ],
)
def test_alias_variants_are_characterised(short_name, long_name):
    """Istzustand, kein Sollwert: beide Alias-Auflösungen lassen die Paare getrennt."""
    pair = [_entity(short_name, "Hospital"), _entity(long_name, "Hospital")]

    assert [e.name for e in resolve_aliases(list(pair))] == [short_name, long_name]
    assert [e.name for e in _merge_entity_variants(list(pair))] == [short_name, long_name]
