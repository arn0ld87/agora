"""Durchreichung des Degradierungs-Sammlers durch alle Ebenen (Issue #1029).

Ein Unit-Test auf ``embed_entities_and_relations`` allein beweist nichts
über den echten Lauf: Der Ausfall entsteht vier Ebenen tiefer als die
Stelle, an der er sichtbar werden muss. Genau an dieser Sorte Lücke sind
#961, #966 und #985 nacheinander vorbeigelaufen — dreimal derselbe Defekt,
dreimal am falschen Codepfad adressiert.

Diese Datei prüft deshalb die Verbindungen selbst:

    embed_entities_and_relations      ← Ebene 1 (test_ingestion_pipeline.py)
        ↑ Neo4jWriteMixin.add_text    ← Ebene 2 (hier)
        ↑ add_text_batches            ← Ebene 3 (hier)
        ↑ _build_graph_worker         ← Ebene 4, Task-Ergebnis (hier)
"""

from unittest.mock import MagicMock

from app.contracts.pipeline_degradation_contract import DegradationKind
from app.services.degradation_collector import DegradationCollector
from app.services.ingestion_pipeline import embed_entities_and_relations


def _failing_embedding(message: str = "connection refused") -> MagicMock:
    embedding = MagicMock(name="EmbeddingService")
    embedding.embed_batch.side_effect = RuntimeError(message)
    return embedding


# ── Ebene 2 — Neo4jWriteMixin.add_text → embed_entities_and_relations ──


class TestStorageAddTextForwardsCollector:
    def _mixin_with(self, embedding: MagicMock):
        """Echter ``Neo4jWriteMixin`` mit gemockter Persistenz.

        Nur Neo4j-I/O wird ersetzt; Phase 1 und Phase 2 laufen als echter
        Code, damit die Durchreichung tatsächlich geprüft wird und nicht
        eine Nachbildung davon.
        """
        from app.storage.neo4j_write import Neo4jWriteMixin

        mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
        mixin._ontology_mutation_service = None  # type: ignore[attr-defined]
        mixin._embedding = embedding  # type: ignore[attr-defined]

        ner = MagicMock(name="NER")
        ner.extract.return_value = {
            "entities": [{"name": "Alice", "type": "Person"}],
            "relations": [],
        }
        mixin._ner = ner  # type: ignore[attr-defined]
        mixin.get_ontology = MagicMock(return_value={})  # type: ignore[attr-defined]
        mixin._persist_episode = MagicMock()  # type: ignore[attr-defined]
        return mixin

    def test_embedding_failure_reaches_the_collector(self):
        from app.storage.neo4j_write import Neo4jWriteMixin

        collector = DegradationCollector()
        mixin = self._mixin_with(_failing_embedding("ollama down"))

        Neo4jWriteMixin.add_text(
            mixin, "graph-1", "Alice lebt in Berlin.", degradations=collector
        )

        events = collector.report().events
        assert len(events) == 1
        assert events[0].kind is DegradationKind.EMBEDDING_UNAVAILABLE
        assert "ollama down" in events[0].detail
        # Der Chunk wurde trotz Ausfall persistiert — der Fallback bleibt.
        mixin._persist_episode.assert_called_once()

    def test_without_collector_the_call_still_succeeds(self):
        """Rückwärtskompatibel: Aufrufer ohne Sammler brechen nicht."""
        from app.storage.neo4j_write import Neo4jWriteMixin

        mixin = self._mixin_with(_failing_embedding())
        episode_id = Neo4jWriteMixin.add_text(mixin, "graph-1", "Text.")
        assert episode_id
        mixin._persist_episode.assert_called_once()


# ── Ebene 3 — add_text_batches → storage.add_text ──────────────────────


class TestAddTextBatchesForwardsCollector:
    def test_collector_is_handed_to_every_chunk(self):
        from app.services.graph_builder import GraphBuilderService

        collector = DegradationCollector()
        storage = MagicMock(name="Storage")
        storage.add_text.side_effect = ["uuid-1", "uuid-2", "uuid-3"]
        service = GraphBuilderService(storage=storage)

        service.add_text_batches(
            graph_id="g1",
            chunks=["a", "b", "c"],
            degradations=collector,
        )

        assert storage.add_text.call_count == 3
        for call in storage.add_text.call_args_list:
            assert call.kwargs["degradations"] is collector

    def test_parallel_chunks_collapse_into_one_finding(self):
        """Alle Chunks scheitern am selben Embedding — ein Befund, nicht N.

        Nutzt die echte ``embed_entities_and_relations``; nur der
        Storage-Aufruf ist ersetzt. Damit läuft die Zusammenfassung durch
        den ThreadPoolExecutor, so wie im echten Build.
        """
        from app.services.graph_builder import GraphBuilderService

        collector = DegradationCollector()
        embedding = _failing_embedding("kein Ollama")

        def _add_text(graph_id, chunk, round_num=None, ner_extractor=None, degradations=None):
            embed_entities_and_relations(
                embedding,
                [{"name": "X", "type": "T"}],
                [],
                degradations=degradations,
            )
            return f"uuid-{chunk}"

        storage = MagicMock(name="Storage")
        storage.add_text.side_effect = _add_text
        service = GraphBuilderService(storage=storage)

        service.add_text_batches(
            graph_id="g1",
            chunks=[f"chunk-{i}" for i in range(12)],
            degradations=collector,
        )

        events = collector.report().events
        assert len(events) == 1
        assert events[0].occurrences == 12


# ── Ebene 4 — _build_graph_worker → Task-Ergebnis ──────────────────────


class TestBuildWorkerPublishesDegradations:
    def _service_with_failing_embedding(self):
        from app.services.graph_builder import GraphBuilderService

        embedding = _failing_embedding("Embedding-Dienst nicht erreichbar")

        def _add_text(graph_id, chunk, round_num=None, ner_extractor=None, degradations=None):
            embed_entities_and_relations(
                embedding,
                [{"name": "X", "type": "T"}],
                [],
                degradations=degradations,
            )
            return "uuid-1"

        storage = MagicMock(name="Storage")
        storage.create_graph.return_value = "graph-1"
        storage.add_text.side_effect = _add_text
        storage.get_graph_info.return_value = {
            "graph_id": "graph-1",
            "node_count": 5,
            "edge_count": 4,
            "entity_types": ["Person"],
        }
        return GraphBuilderService(storage=storage)

    def test_embedding_failure_appears_in_the_task_result(self):
        """Der Beweis, auf den es ankommt: Der Ausfall verlässt die Pipeline.

        Ohne diesen Weg meldete der Graph-Build „Abgeschlossen", und
        niemand außerhalb des Logs erfuhr, dass die semantische Suche auf
        Leer-Vektoren arbeitet.
        """
        service = self._service_with_failing_embedding()
        task_id = service.task_manager.create_task(task_type="graph_build")

        service._build_graph_worker(
            task_id=task_id,
            text="Ein Text, der zu genau einem Chunk wird.",
            ontology={},
            graph_name="Test",
            chunk_size=500,
            chunk_overlap=50,
            batch_size=3,
        )

        task = service.task_manager.get_task(task_id)
        assert task is not None
        assert task.result is not None

        degradations = task.result["degradations"]
        kinds = [event["kind"] for event in degradations["events"]]
        assert "embedding_unavailable" in kinds

    def test_clean_run_reports_an_empty_list(self):
        """Ein sauberer Lauf trägt eine leere Liste — nicht das Fehlen des Feldes.

        Ein fehlender Schlüssel wäre für die Oberfläche nicht von „alte
        Version ohne Degradierungen" zu unterscheiden.
        """
        from app.services.graph_builder import GraphBuilderService

        storage = MagicMock(name="Storage")
        storage.create_graph.return_value = "graph-1"
        storage.add_text.return_value = "uuid-1"
        storage.get_graph_info.return_value = {
            "graph_id": "graph-1",
            "node_count": 5,
            "edge_count": 4,
            "entity_types": ["Person"],
        }
        service = GraphBuilderService(storage=storage)
        task_id = service.task_manager.create_task(task_type="graph_build")

        service._build_graph_worker(
            task_id=task_id,
            text="Sauberer Lauf.",
            ontology={},
            graph_name="Test",
            chunk_size=500,
            chunk_overlap=50,
            batch_size=3,
        )

        task = service.task_manager.get_task(task_id)
        assert task is not None
        assert task.result is not None
        assert task.result["degradations"]["events"] == []
