"""Echte Neo4j-Re-Embedding-Engine (Onboarding Slice 4.3.4, erweitert 4.4).

Ersetzt den ``_NoopReEmbedder``-Stub aus Slice 4.3.1 durch einen echten
Read-Loop, der pro Job **zwei Traeger-Typen** re-embedded, sequenziell
in zwei Phasen (gesteuert ueber ``EmbeddingMigrationProgress.phase``):

1. **Entity-Phase** — ``(n:Entity).entity_embedding``:
   Versionierten Ziel-Vector-Index anlegen (``CREATE ... IF NOT EXISTS``,
   niemals DROP — ADR-0007), Knoten zaehlen, batchweise lesen sortiert
   nach ``n.uuid`` mit Cursor ``uuid > last_processed_id``, Embeddings
   erzeugen, Dimension pruefen, passende Vektoren ueber
   ``db.create.setNodeVectorProperty`` schreiben.
2. **Fact-Phase** — ``()-[r:RELATION]-().fact_embedding``:
   Analog, aber ueber Relationships: ``FOR ()-[r:RELATION]-() ON
   (r.<property_key>)`` und ``db.create.setRelationshipVectorProperty``
   (Neo4j 5.13+, Stack ist 5.18 CE). Cursor ist ``r.uuid`` (RELATION
   hat eine eigene UUID, siehe ``neo4j_write``).

Beide Phasen sind Resume-faehig: ``progress.phase`` disambiguiert den
Cursor ``last_processed_id`` (Entity-UUID vs. RELATION-UUID). Beim
Phasenwechsel ``entity -> fact`` resettet die Engine ``total``/
``processed``/``failed``/``last_processed_id`` auf die Fact-Menge. Ein
Crash waehrend der Fact-Phase setzt ``run()`` am ``last_processed_id``
der Fact-Phase fort; ein Crash am Phasenübergang laeuft die (leere)
Entity-Phase idempotent durch und wechselt dann zur Fact-Phase.

Nach jedem Batch ruft die Engine ``checkpoint(progress)`` auf; der
``EmbeddingMigrationService`` persistiert den Job-Zustand.

Endstatus: ``failed`` sobald mindestens ein Traeger in *irgendeiner*
Phase keine gueltige Dimension bekam (kein Switch auf einen
unvollstaendigen Index), ``completed`` sonst. Ein leerer Graph (keine
Entities, keine Relations) ist eine gueltige Erst-Migration.

Bewusste Einschraenkungen (dokumentiert im Epic-Handover):

* ``RELATION.fact_embedding`` wird **nicht** ueber einen eigenen
  ``EmbeddingIndexVersion``-Datensatz verwaltet — der versionierte
  Index-Vertrag verwaltet weiterhin nur ``entity_embedding_vN``. Die
  Fact-Index/Property-Namen werden konventionell aus der Ziel-Version
  abgeleitet (``fact_embedding_v{N}``) und der Engine explizit
  uebergeben. Ein Folge-Slice kann fact-spezifische
  ``EmbeddingIndexVersion``-Datensaetze einfuehren.
* Kein ``scope="project"``-Filter — die Zuordnung Projekt -> Graph ist
  nicht Teil des Embedding-Vertrags; die Engine laeuft global.
* Gemini-Re-Embedding / Batch-Embedding ist explizit noch nicht
  unterstuetzt — die Engine ist provider-neutral ueber den konfigurierten
  Embedding-Pfad und taeuscht keine Gemini-Batch-API vor.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingMigrationPhase,
    EmbeddingMigrationProgress,
    EmbeddingMigrationStatus,
)
from app.utils.logger import get_logger

logger = get_logger("agora.embedding_reembedder")

# Index- und Property-Namen kommen aus dem eigenen Store
# (``entity_embedding_vN`` / ``fact_embedding_vN``), nie aus User-Input.
# Der Guard verhindert trotzdem strukturell jede Cypher-Injection ueber
# die DDL-F-Strings.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ----------------------------------------------------------------------
# Entity-Phase: (n:Entity).entity_embedding
# ----------------------------------------------------------------------

_ENTITY_COUNT_QUERY = """
MATCH (n:Entity)
WHERE n.uuid IS NOT NULL
RETURN count(n) AS total
"""

# ``summary`` ist der Text, der beim Ingest embedded wurde
# (``ingestion_pipeline.embed_entities_and_relations``); der coalesce-
# Fallback rekonstruiert ihn fuer Bestandsknoten ohne summary-Property.
_ENTITY_BATCH_QUERY = """
MATCH (n:Entity)
WHERE n.uuid IS NOT NULL
  AND ($cursor IS NULL OR n.uuid > $cursor)
RETURN
    n.uuid AS uuid,
    coalesce(n.summary, coalesce(n.name, '') + ' (' + coalesce(n.entity_type, '') + ')') AS text
ORDER BY n.uuid
LIMIT $limit
"""

_ENTITY_WRITE_QUERY = """
UNWIND $rows AS row
MATCH (n:Entity {uuid: row.uuid})
CALL db.create.setNodeVectorProperty(n, $property_key, row.vector)
RETURN count(n) AS written
"""

# ----------------------------------------------------------------------
# Fact-Phase: ()-[r:RELATION]-().fact_embedding
# ----------------------------------------------------------------------

_FACT_COUNT_QUERY = """
MATCH ()-[r:RELATION]-()
WHERE r.uuid IS NOT NULL
RETURN count(r) AS total
"""

# Fact-Text ist ``r.fact`` (beim Ingest embedded, siehe ``neo4j_write``),
# Fallback ``r.name`` fuer Bestandsrelations ohne fact-Property.
_FACT_BATCH_QUERY = """
MATCH ()-[r:RELATION]-()
WHERE r.uuid IS NOT NULL
  AND ($cursor IS NULL OR r.uuid > $cursor)
RETURN
    r.uuid AS uuid,
    coalesce(r.fact, r.name, '') AS text
ORDER BY r.uuid
LIMIT $limit
"""

_FACT_WRITE_QUERY = """
UNWIND $rows AS row
MATCH ()-[r:RELATION {uuid: row.uuid}]-()
CALL db.create.setRelationshipVectorProperty(r, $property_key, row.vector)
RETURN count(r) AS written
"""

EmbedTexts = Callable[[list[str]], list[list[float]]]


class Neo4jReEmbedder:
    """Re-Embedding-Loop ueber Neo4j-Entities und -Relations, batchweise.

    ``driver_factory`` liefert einen Neo4j-Driver (lazy — die Engine
    verbindet erst beim ``run()``); ``embedder_factory`` baut aus der
    ``EmbeddingConfiguration`` eine Batch-Embedding-Funktion. Beide sind
    injizierbar, damit Tests ohne Neo4j und ohne Embedding-Backend laufen.

    ``run()`` durchlaeuft zunaechst die Entity-Phase und danach — sofern
    ``fact_target_index_name`` / ``fact_target_property_key`` uegeben
    wurden — die Fact-Phase. Ohne Fact-Targets verhaelt sich die Engine
    wie Slice 4.3.4 (nur Entity, backward-kompatibel).
    """

    def __init__(
        self,
        *,
        driver_factory: Callable[[], Any],
        embedder_factory: Callable[[EmbeddingConfiguration], EmbedTexts],
        batch_size: int = 50,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size muss >= 1 sein")
        self._driver_factory = driver_factory
        self._embedder_factory = embedder_factory
        self._batch_size = batch_size

    def run(
        self,
        target_index_name: str,
        target_property_key: str,
        expected_dimensions: int,
        progress: EmbeddingMigrationProgress,
        *,
        configuration: EmbeddingConfiguration,
        checkpoint: Callable[[EmbeddingMigrationProgress], None],
        fact_target_index_name: str | None = None,
        fact_target_property_key: str | None = None,
    ) -> EmbeddingMigrationStatus:
        self._require_identifier("Index-Name", target_index_name)
        self._require_identifier("Property-Key", target_property_key)
        has_fact = fact_target_index_name is not None and fact_target_property_key is not None
        if fact_target_index_name is not None:
            self._require_identifier("Fact-Index-Name", fact_target_index_name)
        if fact_target_property_key is not None:
            self._require_identifier("Fact-Property-Key", fact_target_property_key)

        embed_texts = self._embedder_factory(configuration)
        driver = self._driver_factory()
        try:
            with driver.session() as session:
                # Entity-Phase — ueberspringen, wenn der Job bereits in
                # der Fact-Phase resumed (``progress.phase == "fact"``).
                if progress.phase != "fact":
                    progress = self._drain(
                        session,
                        ddl=_entity_index_ddl(
                            target_index_name, target_property_key, expected_dimensions
                        ),
                        count_query=_ENTITY_COUNT_QUERY,
                        batch_query=_ENTITY_BATCH_QUERY,
                        write_query=_ENTITY_WRITE_QUERY,
                        property_key=target_property_key,
                        expected_dimensions=expected_dimensions,
                        progress=progress,
                        phase="entity",
                        embed_texts=embed_texts,
                        checkpoint=checkpoint,
                    )
                    if progress.failed > 0:
                        return "failed"
                    # Phasenwechsel entity -> fact: Cursor disambiguieren
                    # und Zaehler auf die Fact-Menge zuruecksetzen. Der
                    # Wechsel wird *nicht* separat gecheckpointet —
                    # ``_drain(fact)`` schreibt den ersten Fact-Checkpoint
                    # mit dem gezaehlten Fact-Bestand. Crash zwischen
                    # Entity-Ende und Fact-Count ist sicher: beim Resume
                    # laeuft die (leere) Entity-Phase idempotent durch
                    # (kein Traeger mit ``uuid > cursor`` -> kein Write)
                    # und wechselt dann zur Fact-Phase.
                    if has_fact:
                        progress = progress.model_copy(
                            update={"phase": "fact", "last_processed_id": None}
                        )

                if has_fact:
                    progress = self._drain(
                        session,
                        ddl=_fact_index_ddl(
                            fact_target_index_name,  # type: ignore[arg-type]
                            fact_target_property_key,  # type: ignore[arg-type]
                            expected_dimensions,
                        ),
                        count_query=_FACT_COUNT_QUERY,
                        batch_query=_FACT_BATCH_QUERY,
                        write_query=_FACT_WRITE_QUERY,
                        property_key=fact_target_property_key,  # type: ignore[arg-type]
                        expected_dimensions=expected_dimensions,
                        progress=progress,
                        phase="fact",
                        embed_texts=embed_texts,
                        checkpoint=checkpoint,
                    )
                    if progress.failed > 0:
                        return "failed"
        finally:
            driver.close()

        if progress.failed > 0:
            logger.warning(
                "Re-Embedding beendet mit %d fehlgeschlagenen Traegern "
                "(processed=%d, total=%d, phase=%s) — kein Index-Switch",
                progress.failed,
                progress.processed,
                progress.total,
                progress.phase,
            )
            return "failed"
        logger.info(
            "Re-Embedding abgeschlossen: %d/%d Traeger in Phase %s "
            "(entity_property=%s, fact_property=%s)",
            progress.processed,
            progress.total,
            progress.phase,
            target_property_key,
            fact_target_property_key,
        )
        return "completed"

    # ------------------------------------------------------------------
    # Phasen-Loop
    # ------------------------------------------------------------------

    def _drain(
        self,
        session: Any,
        *,
        ddl: str,
        count_query: str,
        batch_query: str,
        write_query: str,
        property_key: str,
        expected_dimensions: int,
        progress: EmbeddingMigrationProgress,
        phase: EmbeddingMigrationPhase,
        embed_texts: EmbedTexts,
        checkpoint: Callable[[EmbeddingMigrationProgress], None],
    ) -> EmbeddingMigrationProgress:
        """Treibt eine Phase (entity ODER fact) batchweise mit Checkpoints.

        Beim ersten Eintritt in die Phase (``last_processed_id is None``)
        werden ``total``/``processed``/``failed`` auf die neue Menge
        gesetzt; bei Resume (Cursor gesetzt) bleibt ``processed``/``failed``
        erhalten und nur ``total`` wird aktualisiert.
        """
        # Versionierten Ziel-Index anlegen — additiv, niemals DROP.
        session.execute_write(lambda tx: tx.run(ddl).consume())

        total = session.execute_read(
            lambda tx: int(tx.run(count_query).single()["total"])
        )
        if progress.last_processed_id is None:
            progress = progress.model_copy(
                update={
                    "phase": phase,
                    "total": total,
                    "processed": 0,
                    "failed": 0,
                    "last_processed_id": None,
                }
            )
        else:
            progress = progress.model_copy(
                update={"phase": phase, "total": total}
            )
        checkpoint(progress)

        cursor = progress.last_processed_id
        while True:
            rows = session.execute_read(
                lambda tx, cursor_=cursor: [
                    dict(record)
                    for record in tx.run(
                        batch_query,
                        cursor=cursor_,
                        limit=self._batch_size,
                    )
                ]
            )
            if not rows:
                break

            texts = [str(row.get("text") or "") for row in rows]
            vectors = embed_texts(texts)
            # Laengen-Mismatch heisst: die Positionszuordnung
            # Text -> Vektor ist nicht mehr verlaesslich. Weiter-
            # machen wuerde falsche Vektoren an falsche Traeger
            # schreiben (Alignment-Drift) — harter Abbruch.
            if len(vectors) != len(rows):
                raise RuntimeError(
                    f"Embedder lieferte {len(vectors)} Vektoren fuer "
                    f"{len(rows)} Texte — Abbruch, um Alignment-"
                    "Drift zu verhindern."
                )

            writable: list[dict[str, Any]] = []
            failed = 0
            for row, vector in zip(rows, vectors):
                if vector is not None and len(vector) == expected_dimensions:
                    writable.append(
                        {
                            "uuid": row["uuid"],
                            "vector": [float(x) for x in vector],
                        }
                    )
                else:
                    failed += 1
                    logger.warning(
                        "Re-Embedding (%s): Traeger %s lieferte Dimension "
                        "%d statt %d — uebersprungen",
                        phase,
                        row["uuid"],
                        len(vector) if vector is not None else 0,
                        expected_dimensions,
                    )

            if writable:
                session.execute_write(
                    lambda tx, rows_=writable: tx.run(
                        write_query,
                        rows=rows_,
                        property_key=property_key,
                    ).consume()
                )

            cursor = rows[-1]["uuid"]
            progress = progress.model_copy(
                update={
                    "processed": progress.processed + len(writable),
                    "failed": progress.failed + failed,
                    "last_processed_id": cursor,
                }
            )
            checkpoint(progress)

        return progress

    # ------------------------------------------------------------------
    # Identifier-Guard
    # ------------------------------------------------------------------

    @staticmethod
    def _require_identifier(label: str, value: str) -> None:
        if not _IDENTIFIER.match(value):
            raise ValueError(f"Ungueltiger {label}: {value!r}")


def _entity_index_ddl(index_name: str, property_key: str, dimensions: int) -> str:
    """Versionierten Entity-Vector-Index anlegen — additiv, niemals DROP."""
    return f"""
CREATE VECTOR INDEX {index_name} IF NOT EXISTS
FOR (n:Entity) ON (n.{property_key})
OPTIONS {{indexConfig: {{
    `vector.dimensions`: {int(dimensions)},
    `vector.similarity_function`: 'cosine'
}}}}
"""


def _fact_index_ddl(index_name: str, property_key: str, dimensions: int) -> str:
    """Versionierten Relationship-Vector-Index anlegen (Neo4j 5.13+).

    Relationship-Vector-Indexe sind ab Neo4j 5.13 unterstuetzt
    (``FOR ()-[r:RELATION]-() ON (r.<prop>)``). Der Stack ist 5.18 CE.
    Additiv (``IF NOT EXISTS``), niemals DROP — ADR-0007.
    """
    return f"""
CREATE VECTOR INDEX {index_name} IF NOT EXISTS
FOR ()-[r:RELATION]-() ON (r.{property_key})
OPTIONS {{indexConfig: {{
    `vector.dimensions`: {int(dimensions)},
    `vector.similarity_function`: 'cosine'
}}}}
"""


__all__ = ["Neo4jReEmbedder", "EmbedTexts"]