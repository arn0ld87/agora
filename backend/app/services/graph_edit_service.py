"""Graphen von Hand bearbeiten (Issue #1808, Etappe 8, ADR-0022).

Der Dienst setzt die Fachregeln vor dem Schreibpfad ``Neo4jEditMixin``
durch:

1. **Sperre**: Jeder Schreibzugriff prüft zuerst, ob eine Simulation den
   Graphen verwendet (``graph_lock``). Gesperrt → ``GraphLockedError``.
2. **Embedding-Migration**: Läuft eine Migration (pending, running,
   validating), wird nicht geschrieben; sonst entstünden Einbettungen auf
   einem Property-Schlüssel, den die Migration gerade umstellt.
3. **Ontologie**: Eine manuelle Entität verwendet nur Typen aus der
   Ontologie des Graphen.
4. **Einbettung**: Ändern sich Name/Typ einer Entität oder der Fakt einer
   Beziehung, wird die Einbettung auf dem aktiven Property-Schlüssel mit
   demselben Eingabetext wie in der Ingestion neu berechnet. Schlägt das
   fehl, wird **nicht** geschrieben: ein stiller Leer-Vektor machte das
   Element für die semantische Suche unsichtbar.

Wiederholbares Anlegen: UUID und Zeitpunkt entstehen vor dem Schreiben. Die
UUID wird aus ``client_request_id`` abgeleitet (UUIDv5 über Graph, Art und
Kennung), derselbe Aufruf ergibt dasselbe Element.

Beziehungen werden hart gelöscht, nicht per ``tombstone_relation``
(Abweichung vom Briefing, Begründung): ``tombstone_relation`` setzt nur
``valid_to_round``, und nur ``get_edges_at_round`` wertet das aus. Die
Leseantwort, die Graph-Werkzeuge des Berichts und die Suche zeigen eine
solche Kante weiter an. Eine „gelöschte“ Beziehung, die weiter zitiert wird,
wäre das Gegenteil des Gewollten.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from ..contracts.graph_edit_contract import (
    EntityCreate,
    EntityDeleteResult,
    EntityMerge,
    EntityMergeResult,
    EntityUpdate,
    GraphEdgeView,
    GraphNodeView,
    RelationCreate,
    RelationDeleteResult,
    RelationUpdate,
)
from ..storage.neo4j_edit import (
    ALIASES_KEY,
    GraphEditConflict,
    GraphEditNotFound,
    default_entity_summary,
    entity_embedding_text,
)
from ..storage.neo4j_mappings import sanitize_label
from ..utils.logger import get_logger
from .graph_lock import GraphLockedError, ensure_graph_unlocked

if TYPE_CHECKING:
    from ..storage.neo4j_storage import Neo4jStorage

logger = get_logger("agora.graph_edit")

_ACTIVE_MIGRATION_STATES = frozenset({"pending", "running", "validating"})


class GraphEditValidationError(ValueError):
    """Die Anfrage ist formal gültig, aber fachlich nicht ausführbar (z. B. unbekannter Typ)."""


class EmbeddingMigrationRunningError(Exception):
    """Eine Embedding-Migration läuft; Schreibzugriffe sind vorübergehend abgelehnt."""


class GraphEditEmbeddingError(Exception):
    """Die Einbettung konnte nicht berechnet werden; es wurde nichts geschrieben."""


def embedding_migration_active() -> bool:
    """Läuft ein Embedding-Migrationsjob (pending, running oder validating)?"""
    from .embedding_configuration_store import EmbeddingConfigurationStore
    from .embedding_migration import EmbeddingMigrationService

    service = EmbeddingMigrationService(store=EmbeddingConfigurationStore())
    return any(job.status in _ACTIVE_MIGRATION_STATES for job in service.list_jobs())


def derive_element_uuid(kind: str, graph_id: str, client_request_id: str) -> str:
    """UUID eines neuen Elements, abgeleitet aus der ``client_request_id`` des Aufrufers."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"agora:graph-edit:{kind}:{graph_id}:{client_request_id.lower()}")
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphEditService:
    """Fachregeln und Orchestrierung der Handänderungen. Siehe Modul-Docstring."""

    def __init__(
        self,
        storage: "Neo4jStorage",
        *,
        lock_check: Callable[[str], None] = ensure_graph_unlocked,
        migration_active: Callable[[], bool] = embedding_migration_active,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._storage = storage
        self._lock_check = lock_check
        self._migration_active = migration_active
        self._clock = clock

    # ── Gemeinsame Prüfungen ────────────────────────────────────────

    def _guard(self, graph_id: str) -> None:
        self._lock_check(graph_id)
        if self._migration_active():
            raise EmbeddingMigrationRunningError(graph_id)

    def _require_ontology_type(self, graph_id: str, entity_type: str) -> None:
        ontology = self._storage.get_ontology(graph_id) or {}
        names = {
            (item.get("name") if isinstance(item, dict) else item)
            for item in (ontology.get("entity_types") or [])
        }
        names.discard(None)
        if entity_type not in names:
            raise GraphEditValidationError(
                f"Typ '{entity_type}' kommt in der Ontologie des Graphen nicht vor"
            )
        if sanitize_label(entity_type) is None:
            raise GraphEditValidationError(
                f"Typ '{entity_type}' lässt sich nicht als Label verwenden"
            )

    def get_allowed_entity_types(self, graph_id: str) -> List[str]:
        """Liefert sortiert alle zulässigen Entitäts-Typen aus der Ontologie des Graphen."""
        ontology = self._storage.get_ontology(graph_id) or {}
        raw = ontology.get("entity_types") or []
        types: set[str] = set()
        for item in raw:
            name: str | None = None
            if isinstance(item, dict) and "name" in item and item["name"]:
                name = str(item["name"]).strip()
            elif isinstance(item, str) and item.strip():
                name = item.strip()
            if name and name != "Entity" and sanitize_label(name) is not None:
                types.add(name)
        return sorted(types)

    def _embed(self, text: str) -> List[float]:
        try:
            vectors = self._storage.edit_embed_texts([text])
        except Exception as exc:  # noqa: BLE001 — wird als fachlicher Fehler weitergegeben
            logger.warning("Einbettung für Handänderung fehlgeschlagen: %s", type(exc).__name__)
            raise GraphEditEmbeddingError(type(exc).__name__) from exc
        vector = vectors[0] if vectors else []
        if not vector:
            raise GraphEditEmbeddingError("leere Einbettung")
        return list(vector)

    @staticmethod
    def _log(graph_id: str, kind: str, action: str, element_uuid: str) -> None:
        # Bewusst ohne Namen und Fakten: Freitext kann personenbezogen sein.
        logger.info(
            "Graph-Handänderung (graph=%s, art=%s, aktion=%s, element=%s)",
            graph_id,
            kind,
            action,
            element_uuid,
        )

    # ── Entitäten ───────────────────────────────────────────────────

    def create_entity(self, graph_id: str, request: EntityCreate) -> Tuple[GraphNodeView, bool]:
        """Legt eine manuelle Entität an. Rückgabe ``(Ansicht, neu_angelegt)``."""
        self._guard(graph_id)
        self._require_ontology_type(graph_id, request.entity_type)

        entity_uuid = derive_element_uuid("entity", graph_id, request.client_request_id)
        now = self._clock()
        embedding = self._embed(entity_embedding_text(request.name, request.entity_type))
        entity_key, _fact_key = self._storage.edit_property_keys()

        node, created = self._storage.edit_create_entity(
            graph_id=graph_id,
            entity_uuid=entity_uuid,
            name=request.name,
            entity_type=request.entity_type,
            summary=request.summary or default_entity_summary(request.name, request.entity_type),
            aliases=request.aliases,
            embedding=embedding,
            property_key=entity_key,
            now=now,
        )
        self._log(graph_id, "entity", "create" if created else "create-replay", entity_uuid)
        return GraphNodeView.model_validate(node), created

    @staticmethod
    def _current_type(current: Dict[str, Any]) -> Optional[str]:
        """Gemeldeten Entitäts-Typ aus dem Knoten extrahieren (Attribute oder Labels)."""
        return current.get("entity_type") or next(iter(current.get("labels") or []), None)

    @staticmethod
    def _current_aliases(current: Dict[str, Any]) -> List[Any]:
        """Alias-Property in kanonische Liste überführen (rückwärtskompatibel)."""
        attrs = current.get("attributes") or {}
        raw = attrs.get(ALIASES_KEY) or attrs.get("aliases") or attrs.get("alias") or []
        return [raw] if isinstance(raw, str) else list(raw)

    @staticmethod
    def _changed_fields(
        request: EntityUpdate,
        cur_name: str,
        cur_type: Optional[str],
        cur_summary: str,
        cur_aliases: List[Any],
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[List[str]]]:
        """Liefert die gewünschten Felder; unveränderte Werte als ``None``."""
        name = request.name if request.name is not None and request.name != cur_name else None
        entity_type = (
            request.entity_type
            if request.entity_type is not None and request.entity_type != cur_type
            else None
        )
        summary = (
            request.summary
            if request.summary is not None and request.summary != cur_summary
            else None
        )
        aliases = (
            request.aliases
            if request.aliases is not None and request.aliases != cur_aliases
            else None
        )
        return name, entity_type, summary, aliases

    def _embed_entity_update(
        self,
        name: Optional[str],
        entity_type: Optional[str],
        summary: Optional[str],
        cur_name: str,
        cur_type: Optional[str],
        cur_summary: str,
    ) -> Tuple[Optional[List[float]], Optional[str], Optional[str]]:
        """Berechnet die Einbettung bei Namens-/Typwechsel und folgt der Auto-Zusammenfassung."""
        if name is None and entity_type is None:
            return None, None, summary
        new_name = name if name is not None else cur_name
        new_type = entity_type if entity_type is not None else cur_type
        embedding_text = entity_embedding_text(new_name, new_type)
        embedding = self._embed(embedding_text)
        # Hatte die Entität noch die automatische Zusammenfassung, folgt sie
        # dem neuen Namen/Typ; eine von Hand gepflegte bleibt unberührt.
        if summary is None and cur_summary == default_entity_summary(cur_name, cur_type):
            summary = default_entity_summary(new_name, new_type)
        return embedding, embedding_text, summary

    def update_entity(self, graph_id: str, entity_uuid: str, request: EntityUpdate) -> GraphNodeView:
        self._guard(graph_id)
        current = self._storage.edit_get_entity(graph_id, entity_uuid)
        if current is None:
            raise GraphEditNotFound(entity_uuid)

        cur_name = current["name"]
        cur_summary = current.get("summary", "")
        cur_type = self._current_type(current)
        cur_aliases = self._current_aliases(current)

        name, entity_type, summary, aliases = self._changed_fields(
            request, cur_name, cur_type, cur_summary, cur_aliases
        )
        if name is None and entity_type is None and summary is None and aliases is None:
            return GraphNodeView.model_validate(current)  # nichts zu ändern

        if entity_type is not None:
            self._require_ontology_type(graph_id, entity_type)

        embedding, embedding_text, summary = self._embed_entity_update(
            name, entity_type, summary, cur_name, cur_type, cur_summary
        )

        entity_key, _fact_key = self._storage.edit_property_keys()
        node = self._storage.edit_update_entity(
            graph_id=graph_id,
            entity_uuid=entity_uuid,
            name=name,
            entity_type=entity_type,
            summary=summary,
            aliases=aliases,
            embedding=embedding,
            embedding_text=embedding_text,
            property_key=entity_key,
            now=self._clock(),
        )
        self._log(graph_id, "entity", "update", entity_uuid)
        return GraphNodeView.model_validate(node)

    def delete_entity(self, graph_id: str, entity_uuid: str) -> EntityDeleteResult:
        self._guard(graph_id)
        removed = self._storage.edit_delete_entity(graph_id, entity_uuid)
        self._log(graph_id, "entity", "delete", entity_uuid)
        return EntityDeleteResult(uuid=entity_uuid, removed_relation_count=removed)

    def merge_entities(self, graph_id: str, request: EntityMerge) -> EntityMergeResult:
        self._guard(graph_id)
        result: Dict[str, Any] = self._storage.edit_merge_entities(
            graph_id=graph_id,
            target_uuid=request.target_uuid,
            source_uuids=list(request.source_uuids),
            now=self._clock(),
        )
        self._log(graph_id, "entity", "merge", request.target_uuid)
        return EntityMergeResult(
            target=GraphNodeView.model_validate(result["node"]),
            merged_source_uuids=result["merged_source_uuids"],
            rewired_relation_count=result["rewired"],
            dropped_relation_count=result["dropped"],
        )

    # ── Beziehungen ─────────────────────────────────────────────────

    def create_relation(self, graph_id: str, request: RelationCreate) -> Tuple[GraphEdgeView, bool]:
        """Legt eine manuelle Beziehung an. Rückgabe ``(Ansicht, neu_angelegt)``."""
        self._guard(graph_id)
        relation_uuid = derive_element_uuid("relation", graph_id, request.client_request_id)
        now = self._clock()
        embedding = self._embed(request.fact)
        _entity_key, fact_key = self._storage.edit_property_keys()

        edge, created = self._storage.edit_create_relation(
            graph_id=graph_id,
            relation_uuid=relation_uuid,
            source_uuid=request.source_uuid,
            target_uuid=request.target_uuid,
            name=request.name,
            fact=request.fact,
            embedding=embedding,
            property_key=fact_key,
            now=now,
        )
        self._log(graph_id, "relation", "create" if created else "create-replay", relation_uuid)
        return GraphEdgeView.model_validate(edge), created

    def update_relation(
        self, graph_id: str, relation_uuid: str, request: RelationUpdate
    ) -> GraphEdgeView:
        self._guard(graph_id)
        current = self._storage.edit_get_relation(graph_id, relation_uuid)
        if current is None:
            raise GraphEditNotFound(relation_uuid)

        name = request.name if request.name is not None and request.name != current["name"] else None
        fact = request.fact if request.fact is not None and request.fact != current["fact"] else None
        if name is None and fact is None:
            return GraphEdgeView.model_validate(current)  # nichts zu ändern

        embedding = self._embed(fact) if fact is not None else None
        _entity_key, fact_key = self._storage.edit_property_keys()
        edge = self._storage.edit_update_relation(
            graph_id=graph_id,
            relation_uuid=relation_uuid,
            name=name,
            fact=fact,
            embedding=embedding,
            property_key=fact_key,
            now=self._clock(),
        )
        self._log(graph_id, "relation", "update", relation_uuid)
        return GraphEdgeView.model_validate(edge)

    def delete_relation(self, graph_id: str, relation_uuid: str) -> RelationDeleteResult:
        self._guard(graph_id)
        self._storage.edit_delete_relation(graph_id, relation_uuid)
        self._log(graph_id, "relation", "delete", relation_uuid)
        return RelationDeleteResult(uuid=relation_uuid)


__all__ = [
    "EmbeddingMigrationRunningError",
    "GraphEditConflict",
    "GraphEditEmbeddingError",
    "GraphEditNotFound",
    "GraphEditService",
    "GraphEditValidationError",
    "GraphLockedError",
    "derive_element_uuid",
    "embedding_migration_active",
]
