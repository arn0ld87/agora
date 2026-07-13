"""Echte Neo4j-Re-Embedding-Engine (Onboarding Slice 4.3.4).

Ersetzt den ``_NoopReEmbedder``-Stub aus Slice 4.3.1 durch einen echten
Read-Loop ueber alle ``(n:Entity)``-Knoten:

1. Versionierten Ziel-Vector-Index anlegen (``CREATE ... IF NOT EXISTS``,
   niemals DROP — ADR-0007).
2. Gesamtzahl der Knoten zaehlen (``progress.total``).
3. Batchweise lesen, sortiert nach ``n.uuid`` mit Cursor
   ``uuid > last_processed_id`` — dadurch ist der Loop nach einem Crash
   ueber ``EmbeddingMigrationProgress.last_processed_id`` wiederaufnehmbar.
4. Pro Batch Embeddings ueber den konfigurierten Provider erzeugen,
   Dimension gegen die verifizierte Konfiguration pruefen und nur
   passende Vektoren in die neue Property schreiben
   (``db.create.setNodeVectorProperty``).
5. Nach jedem Batch ``checkpoint(progress)`` aufrufen — der
   ``EmbeddingMigrationService`` persistiert den Job-Zustand.

Endstatus: ``failed`` sobald mindestens ein Knoten keine gueltige
Dimension bekam (kein Switch auf einen unvollstaendigen Index),
``completed`` sonst. Ein leerer Graph ist eine gueltige Erst-Migration.

Bewusste Nicht-Ziele dieses Slices (dokumentiert im Epic-Handover):

* ``RELATION.fact_embedding`` wird nicht re-embedded — der versionierte
  Index-Vertrag (``EmbeddingIndexVersion``) verwaltet bisher nur
  ``entity_embedding_vN``.
* Kein ``scope="project"``-Filter — die Zuordnung Projekt -> Graph ist
  nicht Teil des Embedding-Vertrags; die Engine laeuft global.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingMigrationProgress,
    EmbeddingMigrationStatus,
)
from app.utils.logger import get_logger

logger = get_logger("agora.embedding_reembedder")

# Index- und Property-Namen kommen aus dem eigenen Store
# (``entity_embedding_vN``), nie aus User-Input. Der Guard verhindert
# trotzdem strukturell jede Cypher-Injection ueber die DDL-F-Strings.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_COUNT_QUERY = """
MATCH (n:Entity)
WHERE n.uuid IS NOT NULL
RETURN count(n) AS total
"""

# ``summary`` ist der Text, der beim Ingest embedded wurde
# (``ingestion_pipeline.embed_entities_and_relations``); der coalesce-
# Fallback rekonstruiert ihn fuer Bestandsknoten ohne summary-Property.
_BATCH_QUERY = """
MATCH (n:Entity)
WHERE n.uuid IS NOT NULL
  AND ($cursor IS NULL OR n.uuid > $cursor)
RETURN
    n.uuid AS uuid,
    coalesce(n.summary, n.name + ' (' + coalesce(n.entity_type, '') + ')') AS text
ORDER BY n.uuid
LIMIT $limit
"""

_WRITE_QUERY = """
UNWIND $rows AS row
MATCH (n:Entity {uuid: row.uuid})
CALL db.create.setNodeVectorProperty(n, $property_key, row.vector)
RETURN count(n) AS written
"""

EmbedTexts = Callable[[list[str]], list[list[float]]]


class Neo4jReEmbedder:
    """Re-Embedding-Loop ueber Neo4j-Entities, batchweise mit Checkpoints.

    ``driver_factory`` liefert einen Neo4j-Driver (lazy — die Engine
    verbindet erst beim ``run()``); ``embedder_factory`` baut aus der
    ``EmbeddingConfiguration`` eine Batch-Embedding-Funktion. Beide sind
    injizierbar, damit Tests ohne Neo4j und ohne Embedding-Backend laufen.
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
    ) -> EmbeddingMigrationStatus:
        if not _IDENTIFIER.match(target_index_name):
            raise ValueError(
                f"Ungueltiger Index-Name: {target_index_name!r}"
            )
        if not _IDENTIFIER.match(target_property_key):
            raise ValueError(
                f"Ungueltiger Property-Key: {target_property_key!r}"
            )

        embed_texts = self._embedder_factory(configuration)
        driver = self._driver_factory()
        try:
            with driver.session() as session:
                ddl = _index_ddl(
                    target_index_name, target_property_key, expected_dimensions
                )
                session.execute_write(lambda tx: tx.run(ddl).consume())

                total = session.execute_read(
                    lambda tx: int(tx.run(_COUNT_QUERY).single()["total"])
                )
                progress = progress.model_copy(update={"total": total})
                checkpoint(progress)

                cursor = progress.last_processed_id
                while True:
                    rows = session.execute_read(
                        lambda tx, cursor_=cursor: [
                            dict(record)
                            for record in tx.run(
                                _BATCH_QUERY,
                                cursor=cursor_,
                                limit=self._batch_size,
                            )
                        ]
                    )
                    if not rows:
                        break

                    texts = [str(row.get("text") or "") for row in rows]
                    vectors = embed_texts(texts)

                    writable: list[dict[str, Any]] = []
                    failed = 0
                    for row, vector in zip(rows, vectors):
                        if len(vector) == expected_dimensions:
                            writable.append(
                                {
                                    "uuid": row["uuid"],
                                    "vector": [float(x) for x in vector],
                                }
                            )
                        else:
                            failed += 1
                            logger.warning(
                                "Re-Embedding: Entity %s lieferte Dimension "
                                "%d statt %d — Knoten uebersprungen",
                                row["uuid"],
                                len(vector),
                                expected_dimensions,
                            )
                    # Defensiv: liefert der Embedder weniger Vektoren als
                    # Texte, zaehlen die fehlenden Knoten als failed.
                    if len(vectors) < len(rows):
                        failed += len(rows) - len(vectors)

                    if writable:
                        session.execute_write(
                            lambda tx, rows_=writable: tx.run(
                                _WRITE_QUERY,
                                rows=rows_,
                                property_key=target_property_key,
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
        finally:
            driver.close()

        if progress.failed > 0:
            logger.warning(
                "Re-Embedding beendet mit %d fehlgeschlagenen Knoten "
                "(processed=%d, total=%d) — kein Index-Switch",
                progress.failed,
                progress.processed,
                progress.total,
            )
            return "failed"
        logger.info(
            "Re-Embedding abgeschlossen: %d/%d Knoten in Property %s",
            progress.processed,
            progress.total,
            target_property_key,
        )
        return "completed"


def _index_ddl(index_name: str, property_key: str, dimensions: int) -> str:
    """Versionierten Vector-Index anlegen — additiv, niemals DROP."""
    return f"""
CREATE VECTOR INDEX {index_name} IF NOT EXISTS
FOR (n:Entity) ON (n.{property_key})
OPTIONS {{indexConfig: {{
    `vector.dimensions`: {int(dimensions)},
    `vector.similarity_function`: 'cosine'
}}}}
"""


__all__ = ["Neo4jReEmbedder", "EmbedTexts"]
