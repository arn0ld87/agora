"""Vertrag für das Bearbeiten von Graphen (Issue #1808, Etappe 8, ADR-0022).

Ein Graph in der Bibliothek lässt sich von Hand ändern: Entitäten und
Beziehungen anlegen, ändern, löschen, Entitäten zusammenführen. Dieser
Vertrag beschreibt die Anfragen, die Ansichten der Elemente (mit
Herkunftsmerkmal) und den Sperrzustand eines Graphen.

Herkunft (ADR-0022 §1): ``extrahiert`` ist der Bestand und trägt kein
Merkmal. ``manual`` (von Hand angelegt) und ``edited`` (extrahiert, danach
von Hand geändert) tragen die Markierung und einen Zeitpunkt. Ein fehlendes
Merkmal bedeutet „extrahiert“; Altgraphen werden nicht nachgerüstet. In
``GraphProvenanceInfo`` ist das ``origin=None``.

Alle Eingabemodelle sind ``extra="forbid"``; Namen und Fakten werden an den
Rändern gekürzt, damit ein leerer oder nur aus Leerraum bestehender Wert
nicht durchrutscht.

Die Leseantwort ``GET /api/graph/data/<graph_id>`` hat weiterhin keinen
Pydantic-Vertrag (sie wird über die Dataclass ``GraphDataDTO`` gebaut). Sie
trägt additiv ``entity_type`` und ``provenance`` je Knoten und ``provenance``
je Kante; die Ansichten hier (``GraphNodeView``, ``GraphEdgeView``) sind die
Form, die der spätere Vollvertrag der Leseantwort übernimmt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

_STRICT = ConfigDict(extra="forbid")

GraphOrigin = Literal["manual", "edited"]

# Neo4j speichert uuid4 in der üblichen 36-Zeichen-Schreibweise.
_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

ElementUuid = Annotated[str, Field(pattern=_UUID_PATTERN)]
EntityName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
EntityTypeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
RelationName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
EntitySummary = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
RelationFact = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
AliasName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

MAX_ALIASES = 20
MAX_MERGE_SOURCES = 50


def _dedupe_aliases(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


# ---------------------------------------------------------------------------
# Herkunft und Ansichten
# ---------------------------------------------------------------------------


class GraphProvenanceInfo(BaseModel):
    """Herkunftsmerkmal eines Knotens oder einer Kante.

    ``origin=None`` heißt „extrahiert“ (Bestand, kein Merkmal).
    ``changed_at`` ist der Zeitpunkt der Handeingabe bzw. der letzten
    Handänderung. ``episode_count`` ist die Zahl der Episoden, aus denen die
    Kante ursprünglich stammt (bei Knoten und manuellen Kanten ``0``); eine
    bearbeitete Kante behält ihre Episoden zur Anzeige.
    """

    model_config = _STRICT

    origin: GraphOrigin | None = None
    changed_at: datetime | None = None
    episode_count: int = Field(default=0, ge=0)


class GraphNodeView(BaseModel):
    """Knoten (Entität) in der Leseform."""

    model_config = _STRICT

    uuid: str = Field(min_length=1)
    name: str
    labels: list[str] = Field(default_factory=list)
    entity_type: str | None = None
    summary: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    provenance: GraphProvenanceInfo = Field(default_factory=GraphProvenanceInfo)


class GraphEdgeView(BaseModel):
    """Kante (Beziehung) in der Leseform."""

    model_config = _STRICT

    uuid: str = Field(min_length=1)
    name: str
    fact: str = ""
    source_node_uuid: str = Field(min_length=1)
    target_node_uuid: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    expired_at: datetime | None = None
    valid_from_round: int | None = None
    valid_to_round: int | None = None
    reinforced_count: int = 1
    episode_ids: list[str] = Field(default_factory=list)
    provenance: GraphProvenanceInfo = Field(default_factory=GraphProvenanceInfo)


# ---------------------------------------------------------------------------
# Anfragen
# ---------------------------------------------------------------------------


class EntityCreate(BaseModel):
    """Entität von Hand anlegen.

    ``client_request_id`` (UUID vom Aufrufer) macht das Anlegen wiederholbar:
    dieselbe Kennung ergibt dieselbe Entität, nie eine zweite.
    ``entity_type`` muss in der Ontologie des Graphen vorkommen.
    """

    model_config = _STRICT

    client_request_id: str = Field(pattern=_UUID_PATTERN)
    name: EntityName
    entity_type: EntityTypeName
    summary: EntitySummary = ""
    aliases: list[AliasName] = Field(default_factory=list, max_length=MAX_ALIASES)

    @field_validator("aliases")
    @classmethod
    def _unique_aliases(cls, value: list[str]) -> list[str]:
        return _dedupe_aliases(value)


class EntityUpdate(BaseModel):
    """Teilmenge der Felder einer Entität ändern. Mindestens ein Feld."""

    model_config = _STRICT

    name: EntityName | None = None
    entity_type: EntityTypeName | None = None
    summary: EntitySummary | None = None
    aliases: list[AliasName] | None = Field(default=None, max_length=MAX_ALIASES)

    @field_validator("aliases")
    @classmethod
    def _unique_aliases(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _dedupe_aliases(value)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> EntityUpdate:
        if not self.model_fields_set:
            raise ValueError("mindestens ein Feld muss angegeben werden")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Felder dürfen nicht null sein; nicht zu ändernde Felder weglassen")
        return self


class EntityMerge(BaseModel):
    """Quell-Entitäten in eine Ziel-Entität zusammenführen."""

    model_config = _STRICT

    target_uuid: ElementUuid
    source_uuids: list[ElementUuid] = Field(min_length=1, max_length=MAX_MERGE_SOURCES)

    @model_validator(mode="after")
    def _sources_distinct_from_target(self) -> EntityMerge:
        if self.target_uuid in self.source_uuids:
            raise ValueError("target_uuid darf nicht in source_uuids vorkommen")
        if len(set(self.source_uuids)) != len(self.source_uuids):
            raise ValueError("source_uuids dürfen sich nicht wiederholen")
        return self


class RelationCreate(BaseModel):
    """Beziehung von Hand anlegen (ohne Episoden, damit ohne Dokumentanker)."""

    model_config = _STRICT

    client_request_id: str = Field(pattern=_UUID_PATTERN)
    source_uuid: ElementUuid
    target_uuid: ElementUuid
    name: RelationName
    fact: RelationFact

    @model_validator(mode="after")
    def _no_self_loop(self) -> RelationCreate:
        if self.source_uuid == self.target_uuid:
            raise ValueError("Quelle und Ziel dürfen nicht dieselbe Entität sein")
        return self


class RelationUpdate(BaseModel):
    """Name und/oder Fakt einer Beziehung ändern. Mindestens ein Feld."""

    model_config = _STRICT

    name: RelationName | None = None
    fact: RelationFact | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> RelationUpdate:
        if not self.model_fields_set:
            raise ValueError("mindestens ein Feld muss angegeben werden")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Felder dürfen nicht null sein; nicht zu ändernde Felder weglassen")
        return self


# ---------------------------------------------------------------------------
# Ergebnisse
# ---------------------------------------------------------------------------


class EntityMergeResult(BaseModel):
    """Ergebnis eines Zusammenführens."""

    model_config = _STRICT

    target: GraphNodeView
    merged_source_uuids: list[str] = Field(default_factory=list)
    rewired_relation_count: int = Field(default=0, ge=0)
    dropped_relation_count: int = Field(default=0, ge=0)


class EntityDeleteResult(BaseModel):
    """Ergebnis eines Löschens einer Entität samt ihrer Beziehungen."""

    model_config = _STRICT

    uuid: str = Field(min_length=1)
    removed_relation_count: int = Field(default=0, ge=0)


class RelationDeleteResult(BaseModel):
    """Ergebnis eines Löschens einer Beziehung."""

    model_config = _STRICT

    uuid: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Sperre
# ---------------------------------------------------------------------------


class GraphLockUser(BaseModel):
    """Eine Simulation, die den Graphen (oder sein Projekt) verwendet."""

    model_config = _STRICT

    simulation_id: str = Field(min_length=1)
    status: str = ""
    project_id: str = ""
    branch_name: str | None = None


class GraphLockState(BaseModel):
    """Sperrzustand eines Graphen (ADR-0022 §6).

    Gesperrt ist ein Graph, sobald eine Simulation sein Projekt oder seine
    ``graph_id`` verwendet. Der Zustand wird bei jeder Abfrage aus dem
    Bestand abgeleitet; es gibt kein eigenes Feld.

    ``graph_id`` ist leer, wenn die Sperre für ein Projekt ohne Graph
    ermittelt wurde (Löschen und Zurücksetzen eines Projekts); dann zählen
    nur die Simulationen des Projekts.
    """

    model_config = _STRICT

    graph_id: str
    locked: bool
    used_by: list[GraphLockUser] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Duplizieren
# ---------------------------------------------------------------------------

GraphDuplicateStatus = Literal["pending", "processing", "completed", "failed", "stopped", "paused"]


class GraphDuplicateRequest(BaseModel):
    """Einen Graphen als unabhängige, nicht gesperrte Kopie anlegen.

    ``client_request_id`` (UUID vom Aufrufer) macht den Auftrag wiederholbar:
    dieselbe Kennung ergibt denselben Auftrag, nie eine zweite Kopie.
    ``name`` ist der Name der Kopie (Graph und Projekt).
    """

    model_config = _STRICT

    client_request_id: str = Field(pattern=_UUID_PATTERN)
    name: EntityName


class GraphDuplicateJob(BaseModel):
    """Der Kopierauftrag (ein Job der ``RunRegistry`` mit ``run_type='graph_duplicate'``).

    ``graph_id`` und ``project_id`` sind die Kennungen der Kopie. Sie stehen
    von Anfang an fest, die Kopie ist aber erst bei ``status='completed'``
    vollständig lesbar. Bei ``failed`` sind Zielgraph und Zielprojekt
    wieder entfernt. Fortschritt und Endzustand liefert
    ``GET /api/runs/<run_id>``.
    """

    model_config = _STRICT

    run_id: str = Field(min_length=1)
    source_graph_id: str = Field(min_length=1)
    graph_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: GraphDuplicateStatus
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    error: str | None = None


__all__ = [
    "GraphDuplicateJob",
    "GraphDuplicateRequest",
    "GraphDuplicateStatus",
    "GraphOrigin",
    "GraphProvenanceInfo",
    "GraphNodeView",
    "GraphEdgeView",
    "EntityCreate",
    "EntityUpdate",
    "EntityMerge",
    "RelationCreate",
    "RelationUpdate",
    "EntityMergeResult",
    "EntityDeleteResult",
    "RelationDeleteResult",
    "GraphLockUser",
    "GraphLockState",
    "MAX_ALIASES",
    "MAX_MERGE_SOURCES",
]
