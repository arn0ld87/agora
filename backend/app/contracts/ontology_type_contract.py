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


__all__ = [
    "ONTOLOGY_KIND_CONTESTED_TOPIC",
    "ONTOLOGY_KIND_ENTITY",
    "OntologyTypeKind",
    "OntologyTypeMetadata",
    "contested_topic_type_names",
]
