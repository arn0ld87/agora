"""Unit-Tests für services/ingestion_pipeline.py (Issue #51, EPIC-08-ST-02).

Sichern Phase 1 (NER+RE) und Phase 2 (Batch-Embedding) der zerlegten
``add_text``-Pipeline. Phase 3 (Persist) bleibt storage-intern und wird
weiterhin via ``test_neo4j_*``-Tests indirekt abgedeckt.
"""

from unittest.mock import MagicMock

from app.services.ingestion_pipeline import (
    embed_entities_and_relations,
    extract_entities_and_relations,
)


# ── Phase 1 — NER + RE ──────────────────────────────────────────────


class TestExtractEntitiesAndRelations:
    def test_delegates_to_ner_with_text_and_ontology(self):
        ner = MagicMock()
        ner.extract.return_value = {
            "entities": [{"name": "Alice", "type": "Person"}],
            "relations": [],
        }
        ontology = {"entity_types": ["Person"]}

        result = extract_entities_and_relations(ner, "Alice goes home.", ontology)

        ner.extract.assert_called_once_with("Alice goes home.", ontology)
        assert result["entities"] == [{"name": "Alice", "type": "Person"}]
        assert result["relations"] == []

    def test_passes_through_full_extraction_dict(self):
        """Schema bleibt 1:1 — auch zusätzliche Keys werden durchgereicht."""
        ner = MagicMock()
        ner.extract.return_value = {
            "entities": [],
            "relations": [],
            "extra_meta": {"version": 2},
        }
        result = extract_entities_and_relations(ner, "x", {})
        assert result["extra_meta"] == {"version": 2}

    def test_empty_extraction_is_fine(self):
        ner = MagicMock()
        ner.extract.return_value = {"entities": [], "relations": []}
        result = extract_entities_and_relations(ner, "", {})
        assert result["entities"] == []
        assert result["relations"] == []


# ── Phase 2 — Batch-Embedding ───────────────────────────────────────


class TestEmbedEntitiesAndRelations:
    def test_empty_inputs_skip_embedding_call(self):
        embedding = MagicMock()
        ent_emb, rel_emb = embed_entities_and_relations(embedding, [], [])
        assert ent_emb == []
        assert rel_emb == []
        embedding.embed_batch.assert_not_called()

    def test_combines_entity_summaries_and_facts_into_single_batch(self):
        embedding = MagicMock()
        embedding.embed_batch.return_value = [
            [0.1], [0.2], [0.3], [0.4],  # 2 entities + 2 relations
        ]
        entities = [
            {"name": "Alice", "type": "Person"},
            {"name": "Berlin", "type": "City"},
        ]
        relations = [
            {"source": "Alice", "target": "Berlin", "type": "LIVES_IN", "fact": "Alice lives in Berlin."},
            {"source": "Berlin", "target": "Germany", "type": "PART_OF", "fact": "Berlin part of Germany."},
        ]

        ent_emb, rel_emb = embed_entities_and_relations(embedding, entities, relations)

        embedding.embed_batch.assert_called_once()
        called_with = embedding.embed_batch.call_args[0][0]
        assert called_with == [
            "Alice (Person)",
            "Berlin (City)",
            "Alice lives in Berlin.",
            "Berlin part of Germany.",
        ]
        assert ent_emb == [[0.1], [0.2]]
        assert rel_emb == [[0.3], [0.4]]

    def test_relation_without_fact_falls_back_to_synthesized_text(self):
        embedding = MagicMock()
        embedding.embed_batch.return_value = [[0.1]]
        relations = [
            {"source": "Alice", "target": "Berlin", "type": "LIVES_IN"},  # no "fact"
        ]
        embed_entities_and_relations(embedding, [], relations)
        called_with = embedding.embed_batch.call_args[0][0]
        assert called_with == ["Alice LIVES_IN Berlin"]

    def test_only_entities_no_relations(self):
        embedding = MagicMock()
        embedding.embed_batch.return_value = [[0.1], [0.2]]
        entities = [
            {"name": "Alice", "type": "Person"},
            {"name": "Bob", "type": "Person"},
        ]
        ent_emb, rel_emb = embed_entities_and_relations(embedding, entities, [])
        assert ent_emb == [[0.1], [0.2]]
        assert rel_emb == []

    def test_only_relations_no_entities(self):
        embedding = MagicMock()
        embedding.embed_batch.return_value = [[0.5]]
        relations = [
            {"source": "X", "target": "Y", "type": "REL", "fact": "f"},
        ]
        ent_emb, rel_emb = embed_entities_and_relations(embedding, [], relations)
        assert ent_emb == []
        assert rel_emb == [[0.5]]

    def test_embedding_failure_returns_empty_vectors_per_text(self):
        """Bei Embedding-Crash: für jeden Text ein leerer Vektor —
        Persist-Pfad darf nicht durch Embedding-Fehler crashen."""
        embedding = MagicMock()
        embedding.embed_batch.side_effect = RuntimeError("model down")
        entities = [{"name": "Alice", "type": "Person"}]
        relations = [{"source": "Alice", "target": "Bob", "type": "KNOWS", "fact": "Alice knows Bob."}]

        ent_emb, rel_emb = embed_entities_and_relations(embedding, entities, relations)

        # Beide Listen haben die richtige Länge, aber jeder Eintrag ist []
        assert ent_emb == [[]]
        assert rel_emb == [[]]

    def test_position_alignment_preserved_with_uneven_split(self):
        """3 entities + 1 relation → split[:3] vs split[3:]."""
        embedding = MagicMock()
        embedding.embed_batch.return_value = [[1], [2], [3], [4]]
        entities = [
            {"name": "A", "type": "T"},
            {"name": "B", "type": "T"},
            {"name": "C", "type": "T"},
        ]
        relations = [{"source": "A", "target": "B", "type": "R", "fact": "f"}]

        ent_emb, rel_emb = embed_entities_and_relations(embedding, entities, relations)

        assert ent_emb == [[1], [2], [3]]
        assert rel_emb == [[4]]


# ── Pipeline-Komposition (Phase 1 → Phase 2) ────────────────────────


class TestPipelineComposition:
    """Sichert, dass Phase-1-Output direkt in Phase 2 reingeht — der
    Vertrag, den ``add_text`` heute orchestriert."""

    def test_extract_then_embed_end_to_end(self):
        ner = MagicMock()
        ner.extract.return_value = {
            "entities": [{"name": "Alice", "type": "Person"}],
            "relations": [{"source": "Alice", "target": "Bob", "type": "KNOWS", "fact": "Alice knows Bob."}],
        }
        embedding = MagicMock()
        embedding.embed_batch.return_value = [[0.1], [0.2]]

        extraction = extract_entities_and_relations(ner, "Alice knows Bob.", {})
        ent_emb, rel_emb = embed_entities_and_relations(
            embedding,
            extraction["entities"],
            extraction["relations"],
        )

        assert len(ent_emb) == 1
        assert len(rel_emb) == 1
        assert embedding.embed_batch.call_args[0][0] == [
            "Alice (Person)",
            "Alice knows Bob.",
        ]
