"""Typ-Metadaten der Ontologie — Streitgegenstand und Akteurstauglichkeit.

Issue #1759 · B1

Die Ontologie-Typ-Definition trägt zwei harte Metadaten:

* ``kind`` markiert, ob ein Typ der **Streitgegenstand** des Laufs ist
  (``"contested_topic"``) oder ein gewöhnlicher Entitätstyp (``"entity"``,
  Default). Der Streitgegenstand wird nicht über eine feste Typliste erkannt,
  sondern pro Lauf vom Ontologie-Generator deklariert.
* ``actor_capable`` sagt, ob Entitäten dieses Typs als Akteure in eine
  Simulation gehören. Standorte, Vorhaben, Dokumente und der Streitgegenstand
  selbst sind keine Akteure.

Rückwärtskompatibel: Ontologien, die vor diesem Vertrag persistiert wurden,
tragen keines der beiden Felder. Sie lesen sich über die Defaults
(``kind="entity"``, ``actor_capable=True``) und bleiben unverändert gültig —
``True`` ist das bisherige, konservativ durchlassende Verhalten der
Eignungsprüfung (#1034).

Die Ablösung der festen Typlisten der Eignungsprüfung ist bewusst nicht Teil
dieses Vertrags; hier liegen nur die Metadaten und der Lesezugriff darauf.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

OntologyTypeKind = Literal["entity", "contested_topic"]

ONTOLOGY_KIND_ENTITY: OntologyTypeKind = "entity"
ONTOLOGY_KIND_CONTESTED_TOPIC: OntologyTypeKind = "contested_topic"


class OntologyTypeMetadata(BaseModel):
    """Metadaten eines Ontologie-Entitätstyps (Streitgegenstand, Akteurstauglichkeit)."""

    model_config = ConfigDict(extra="forbid")

    kind: OntologyTypeKind = Field(
        default=ONTOLOGY_KIND_ENTITY,
        description=(
            '"contested_topic" markiert den Streitgegenstand des Laufs '
            '(pro Lauf deklariert, kein fester Typ); sonst "entity".'
        ),
    )
    actor_capable: bool = Field(
        default=True,
        description=(
            "Ob Entitäten dieses Typs als Akteure simuliert werden dürfen. "
            "Ein contested_topic ist nie akteursfähig."
        ),
    )

    @model_validator(mode="after")
    def _topic_is_never_an_actor(self) -> OntologyTypeMetadata:
        if self.kind == ONTOLOGY_KIND_CONTESTED_TOPIC and self.actor_capable:
            self.actor_capable = False
        return self


def contested_topic_type_names(ontology: Optional[Mapping[str, Any]]) -> frozenset[str]:
    """Namen aller als ``contested_topic`` deklarierten Typen dieser Ontologie.

    Liest die persistierte Ontologie (``Project.ontology``, ein Dict). Typen
    ohne ``kind`` — also jede Ontologie aus der Zeit vor diesem Vertrag —
    zählen als gewöhnliche Entitätstypen. Fehlende oder kaputte Struktur
    ergibt die leere Menge statt eines Fehlers: ohne Topic-Typ gilt das
    bisherige Verhalten.
    """
    if not isinstance(ontology, Mapping):
        return frozenset()
    entity_types = ontology.get("entity_types")
    if not isinstance(entity_types, list):
        return frozenset()
    names: set[str] = set()
    for entity_type in entity_types:
        if not isinstance(entity_type, Mapping):
            continue
        name = entity_type.get("name")
        if (
            isinstance(name, str)
            and name
            and entity_type.get("kind") == ONTOLOGY_KIND_CONTESTED_TOPIC
        ):
            names.add(name)
    return frozenset(names)


class OntologyTypeCatalog(BaseModel):
    """Lesesicht auf die Typ-Definitionen einer persistierten Ontologie (B2/B3).

    Die Eignungsprüfung folgt damit der Typ-Definition statt einer festen
    Typliste. Alle Namen sind ``casefold``-normalisiert, damit der Vergleich
    gegen ``entity_type`` der Graph-Entitäten nicht an der Schreibweise hängt.

    ``metadata_driven`` ist nur wahr, wenn mindestens ein Typ ``kind`` oder
    ``actor_capable`` ausdrücklich trägt. Ontologien aus der Zeit vor diesem
    Vertrag haben keines von beidem — für sie bleibt es beim bisherigen
    Rückfall auf die festen Typlisten.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata_driven: bool = False
    declared_types: frozenset[str] = Field(default_factory=frozenset)
    non_actor_types: frozenset[str] = Field(default_factory=frozenset)
    contested_topic_types: frozenset[str] = Field(default_factory=frozenset)

    def non_actor_reason(self, entity_type: str) -> Optional[str]:
        """Grund, warum dieser Typ nie Persona wird — ``None``, wenn er es darf."""
        key = (entity_type or "").strip().casefold()
        if key in self.contested_topic_types:
            return "contested_topic (Streitgegenstand des Laufs)"
        if key in self.non_actor_types:
            return "actor_capable=false"
        return None


def _entity_type_definitions(ontology: Optional[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not isinstance(ontology, Mapping):
        return []
    entity_types = ontology.get("entity_types")
    if not isinstance(entity_types, list):
        return []
    return [
        entity_type
        for entity_type in entity_types
        if isinstance(entity_type, Mapping)
        and isinstance(entity_type.get("name"), str)
        and entity_type["name"]
    ]


def _carries_metadata(entity_type: Mapping[str, Any]) -> bool:
    return "kind" in entity_type or "actor_capable" in entity_type


def _is_non_actor(entity_type: Mapping[str, Any]) -> bool:
    if entity_type.get("kind") == ONTOLOGY_KIND_CONTESTED_TOPIC:
        return True
    return entity_type.get("actor_capable") is False


def ontology_type_catalog(ontology: Optional[Mapping[str, Any]]) -> OntologyTypeCatalog:
    """Baut den :class:`OntologyTypeCatalog` aus ``Project.ontology``.

    Fehlende oder kaputte Struktur ergibt den leeren, nicht metadatengetriebenen
    Katalog — die Eignungsprüfung fällt dann auf die festen Typlisten zurück.
    """
    definitions = _entity_type_definitions(ontology)
    if not any(_carries_metadata(definition) for definition in definitions):
        return OntologyTypeCatalog()
    return OntologyTypeCatalog(
        metadata_driven=True,
        declared_types=frozenset(d["name"].casefold() for d in definitions),
        non_actor_types=frozenset(d["name"].casefold() for d in definitions if _is_non_actor(d)),
        contested_topic_types=frozenset(
            name.casefold() for name in contested_topic_type_names(ontology)
        ),
    )


__all__ = [
    "ONTOLOGY_KIND_CONTESTED_TOPIC",
    "ONTOLOGY_KIND_ENTITY",
    "OntologyTypeCatalog",
    "OntologyTypeKind",
    "OntologyTypeMetadata",
    "contested_topic_type_names",
    "ontology_type_catalog",
]
