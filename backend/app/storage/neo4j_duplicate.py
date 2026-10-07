"""
Kopierpfad für Graphen (Issue #1808, Etappe 8, Slice 8c).

``Neo4jDuplicateMixin`` liest einen Graphen seitenweise und schreibt ihn
unter neuer ``graph_id`` und neuen UUIDs wieder. Er führt **keinen** LLM- und
keinen Embedding-Aufruf aus: Eigenschaften (auch die Embedding-Vektoren auf
dem jeweils aktiven Property-Schlüssel) werden unverändert übernommen. Die
Fachregeln (Sperre, Migration, Projekt, Rollback) liegen im
``GraphDuplicateService``; hier steht nur, was Neo4j ausführt.

Aufbau des Graphen in Neo4j: ein ``:Graph``-Knoten, ``:Entity``- und
``:Episode``-Knoten mit ``graph_id`` sowie ``:RELATION``-Kanten zwischen
Entitäten. Mehr gehört zum Graphen nicht; Simulationsknoten (``Agent``,
``Persona``, ``SimulationBranch``) werden nicht kopiert.

Stapel: Gelesen wird seitenweise nach ``uuid`` (Schlüsselmengen-Paging über
den vorhandenen Unique-Constraint, ohne neuen Index); Kanten werden über die
Quell-Entitäten einer Seite gelesen. Geschrieben wird je Seite in einer
Transaktion mit ``UNWIND``.

Idempotenz: Jede Schreib-Transaktion läuft unter ``_call_with_retry`` und
kann nach einer verlorenen Commit-Bestätigung erneut ausgeführt werden. Alle
Schreib-Statements sind ``MERGE`` auf der (vom Dienst deterministisch
abgeleiteten) neuen UUID; ein zweiter Durchlauf legt nichts doppelt an.
Kantenstatements melden die Zahl der verarbeiteten Zeilen zurück, damit ein
fehlender Endpunkt nicht still eine Kante verschluckt.

Cypher-Identifier: Labels laufen durch ``sanitize_label`` (ein Label, das
sich nicht sicher schreiben lässt, bricht das Kopieren ab, statt still zu
entfallen). Property-Namen stammen aus den gelesenen Datensätzen und werden
nie in den Query-Text interpoliert, sie reisen als Map-Parameter.

Mixin-Voraussetzungen am konkreten Storage: ``_get_session`` und
``_call_with_retry``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ContextManager, Dict, Iterable, List, Optional, Tuple

from .neo4j_mappings import sanitize_label


class GraphDuplicateWriteError(RuntimeError):
    """Beim Schreiben der Kopie ist etwas still weggefallen oder nicht schreibbar."""


def _label_clause(labels: Iterable[str]) -> str:
    """``:`A`:`B```-Anhängsel für ``SET n``; ``Entity`` ist schon über ``MERGE`` gesetzt."""
    parts: List[str] = []
    for label in labels:
        if label == "Entity":
            continue
        safe = sanitize_label(label)
        if safe is None or safe != label:
            raise GraphDuplicateWriteError(f"Label {label!r} lässt sich nicht sicher schreiben")
        parts.append(f"`{safe}`")
    return ":".join(parts)


class Neo4jDuplicateMixin:
    """Kopierpfad für Graphen. Siehe Modul-Docstring."""

    if TYPE_CHECKING:
        # Voraussetzungen am konkreten Storage (Modul-Docstring). Nur für den
        # Typprüfer deklariert: zur Laufzeit gibt es sie hier nicht und
        # verdecken daher nichts in der MRO.
        def _get_session(self, **kwargs: Any) -> ContextManager[Any]: ...

        def _call_with_retry(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...

    # ── Lesen ───────────────────────────────────────────────────────

    def duplicate_read_graph(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Eigenschaften des ``:Graph``-Knotens oder ``None``, wenn es ihn nicht gibt."""

        def _read(tx):
            record = tx.run(
                "MATCH (g:Graph {graph_id: $gid}) RETURN properties(g) AS props",
                gid=graph_id,
            ).single()
            return dict(record["props"]) if record is not None else None

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def duplicate_count(self, graph_id: str) -> Dict[str, int]:
        """Zahl der Entitäten, Beziehungen und Episoden eines Graphen."""

        def _read(tx):
            counts: Dict[str, int] = {}
            for key, query in (
                ("entities", "MATCH (n:Entity {graph_id: $gid}) RETURN count(n) AS c"),
                ("relations", "MATCH ()-[r:RELATION {graph_id: $gid}]->() RETURN count(r) AS c"),
                ("episodes", "MATCH (ep:Episode {graph_id: $gid}) RETURN count(ep) AS c"),
            ):
                record = tx.run(query, gid=graph_id).single()
                counts[key] = int(record["c"]) if record is not None else 0
            return counts

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def duplicate_read_entities(
        self, graph_id: str, after_uuid: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Eine Seite Entitäten (``props``, ``labels``), aufsteigend nach UUID, ab ``after_uuid`` (exklusiv)."""

        def _read(tx):
            result = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) WHERE n.uuid > $after "
                "RETURN properties(n) AS props, labels(n) AS labels "
                "ORDER BY n.uuid LIMIT $limit",
                gid=graph_id,
                after=after_uuid,
                limit=limit,
            )
            return [{"props": dict(r["props"]), "labels": list(r["labels"])} for r in result]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def duplicate_read_episodes(
        self, graph_id: str, after_uuid: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Eine Seite Episoden (``props``), aufsteigend nach UUID, ab ``after_uuid`` (exklusiv)."""

        def _read(tx):
            result = tx.run(
                "MATCH (ep:Episode {graph_id: $gid}) WHERE ep.uuid > $after "
                "RETURN properties(ep) AS props ORDER BY ep.uuid LIMIT $limit",
                gid=graph_id,
                after=after_uuid,
                limit=limit,
            )
            return [{"props": dict(r["props"])} for r in result]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def duplicate_read_relations(
        self, graph_id: str, source_uuids: List[str]
    ) -> List[Dict[str, Any]]:
        """Alle ausgehenden Beziehungen der angegebenen Entitäten (``props``, ``source``, ``target``)."""

        def _read(tx):
            result = tx.run(
                "MATCH (s:Entity)-[r:RELATION]->(t:Entity) "
                "WHERE s.uuid IN $uuids AND r.graph_id = $gid AND t.graph_id = $gid "
                "RETURN properties(r) AS props, s.uuid AS src, t.uuid AS tgt",
                gid=graph_id,
                uuids=source_uuids,
            )
            return [
                {"props": dict(r["props"]), "source": r["src"], "target": r["tgt"]}
                for r in result
            ]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ── Schreiben ───────────────────────────────────────────────────

    def duplicate_create_graph(
        self,
        *,
        graph_id: str,
        name: str,
        description: str,
        ontology_json: str,
        now: str,
    ) -> None:
        """Legt den ``:Graph``-Knoten der Kopie an (Status ``building``, bis alles geschrieben ist)."""

        def _create(tx):
            tx.run(
                """
                MERGE (g:Graph {graph_id: $gid})
                ON CREATE SET
                    g.name = $name,
                    g.description = $description,
                    g.ontology_json = $ontology_json,
                    g.created_at = $now,
                    g.status = 'building'
                """,
                gid=graph_id,
                name=name,
                description=description,
                ontology_json=ontology_json,
                now=now,
            )

        with self._get_session() as session:
            self._call_with_retry(session.execute_write, _create)

    def duplicate_write_entities(self, rows: List[Dict[str, Any]]) -> int:
        """Schreibt Entitäten (Zeilen ``uuid``, ``props``, ``labels``). Rückgabe: Zahl geschriebener Zeilen."""
        written = 0
        # Ein Statement je Label-Kombination: Labels sind in Cypher keine Parameter.
        groups: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
        for row in rows:
            key = tuple(sorted(label for label in row["labels"] if label != "Entity"))
            groups.setdefault(key, []).append({"uuid": row["uuid"], "props": row["props"]})

        for labels, group in groups.items():
            clause = _label_clause(labels)
            set_labels = f" SET n:{clause}" if clause else ""
            query = (
                "UNWIND $rows AS row "
                "MERGE (n:Entity {uuid: row.uuid}) "
                f"ON CREATE SET n = row.props{set_labels} "
                "RETURN count(n) AS written"
            )

            def _write(tx, _query=query, _group=group):
                record = tx.run(_query, rows=_group).single()
                return int(record["written"]) if record is not None else 0

            with self._get_session() as session:
                count = self._call_with_retry(session.execute_write, _write)
            if count != len(group):
                raise GraphDuplicateWriteError(
                    f"Entitäten: {count} von {len(group)} Zeilen geschrieben"
                )
            written += count
        return written

    def duplicate_write_episodes(self, rows: List[Dict[str, Any]]) -> int:
        """Schreibt Episoden (Zeilen ``uuid``, ``props``). Rückgabe: Zahl geschriebener Zeilen."""
        if not rows:
            return 0

        def _write(tx):
            record = tx.run(
                "UNWIND $rows AS row "
                "MERGE (ep:Episode {uuid: row.uuid}) "
                "ON CREATE SET ep = row.props "
                "RETURN count(ep) AS written",
                rows=rows,
            ).single()
            return int(record["written"]) if record is not None else 0

        with self._get_session() as session:
            count = self._call_with_retry(session.execute_write, _write)
        if count != len(rows):
            raise GraphDuplicateWriteError(f"Episoden: {count} von {len(rows)} Zeilen geschrieben")
        return count

    def duplicate_write_relations(self, rows: List[Dict[str, Any]]) -> int:
        """Schreibt Beziehungen (Zeilen ``uuid``, ``source``, ``target``, ``props``).

        Fehlt ein Endpunkt in der Kopie, entfiele die Zeile im ``MATCH``
        still; die zurückgemeldete Zeilenzahl deckt das auf.
        """
        if not rows:
            return 0

        def _write(tx):
            record = tx.run(
                "UNWIND $rows AS row "
                "MATCH (s:Entity {uuid: row.source}) "
                "MATCH (t:Entity {uuid: row.target}) "
                "MERGE (s)-[r:RELATION {uuid: row.uuid}]->(t) "
                "ON CREATE SET r = row.props "
                "RETURN count(r) AS written",
                rows=rows,
            ).single()
            return int(record["written"]) if record is not None else 0

        with self._get_session() as session:
            count = self._call_with_retry(session.execute_write, _write)
        if count != len(rows):
            raise GraphDuplicateWriteError(
                f"Beziehungen: {count} von {len(rows)} Zeilen geschrieben"
            )
        return count


__all__ = ["GraphDuplicateWriteError", "Neo4jDuplicateMixin"]
