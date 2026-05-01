"""
Ingestion-Pipeline für Text-Chunks (NER + Embedding).

Issue #51 (EPIC-08-ST-02): Die monolithische ``Neo4jStorage.add_text``-Methode
in drei Phasen zerlegen. Phase 1 (NER + RE) und Phase 2 (Batch-Embedding)
sind hier als state-lose Top-Level-Funktionen — beide unit-testbar mit
Mock-Backends. Phase 3 (Persistenz in Neo4j) bleibt storage-nah als
private Methode auf ``Neo4jStorage``, weil sie eng an Driver, Cypher
und Retry-Logik gekoppelt ist.

Konsumiert von ``Neo4jStorage.add_text``.
"""

from typing import Any, Dict, List, Tuple

from ..utils.logger import get_logger

logger = get_logger("agora.ingestion_pipeline")


def extract_entities_and_relations(
    ner: Any,
    text: str,
    ontology: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase 1 — NER + Relation-Extraction.

    Delegiert an ``ner.extract(text, ontology)`` und loggt das Ergebnis.

    Args:
        ner: NER-Service mit ``.extract(text, ontology)``-Methode.
        text: Einzelner Text-Chunk (typischerweise eine Episode).
        ontology: Aktuelle Ontologie als Schema-Hinweis für den NER.

    Returns:
        Extraction-Dict mit den Schlüsseln ``"entities"`` und ``"relations"``
        (jeweils ``List[Dict[str, Any]]``). Schema unverändert zum
        ursprünglichen ``add_text``-Verhalten.
    """
    logger.info(f"[ingestion] Starting NER extraction for chunk ({len(text)} chars)...")
    extraction = ner.extract(text, ontology)
    entities = extraction.get("entities", [])
    relations = extraction.get("relations", [])
    logger.info(
        f"[ingestion] NER done: {len(entities)} entities, {len(relations)} relations"
    )
    return extraction


def embed_entities_and_relations(
    embedding: Any,
    entities: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
) -> Tuple[List[List[float]], List[List[float]]]:
    """Phase 2 — Batch-Embedding für Entity-Summaries und Fact-Texts.

    Konkateniert beide Text-Listen und feuert einen einzigen
    ``embed_batch``-Call ab (Performance: ein Roundtrip statt N).
    Bei Embedding-Fehler liefern alle Items ``[]`` zurück, damit der
    Persist-Pfad nicht crasht — entspricht dem historischen Verhalten.

    Args:
        embedding: Embedding-Service mit ``.embed_batch(texts)``-Methode.
        entities: NER-Output ``[{"name": …, "type": …, …}, …]``.
        relations: NER-Output ``[{"source": …, "target": …, "type": …,
            "fact": …}, …]``.

    Returns:
        ``(entity_embeddings, relation_embeddings)`` — zwei Listen, die
        positionsweise zu ``entities`` bzw. ``relations`` passen. Bei
        leeren Inputs gibt's zwei leere Listen zurück.
    """
    entity_summaries = [f"{e['name']} ({e['type']})" for e in entities]
    fact_texts = [
        r.get("fact", f"{r['source']} {r['type']} {r['target']}")
        for r in relations
    ]
    all_texts = entity_summaries + fact_texts

    if not all_texts:
        return [], []

    logger.info(f"[ingestion] Batch-embedding {len(all_texts)} texts...")
    try:
        all_embeddings = embedding.embed_batch(all_texts)
    except Exception as exc:
        logger.warning(f"[ingestion] Batch embedding failed, falling back to empty: {exc}")
        all_embeddings = [[] for _ in all_texts]

    entity_count = len(entities)
    return all_embeddings[:entity_count], all_embeddings[entity_count:]


__all__ = [
    "extract_entities_and_relations",
    "embed_entities_and_relations",
]
