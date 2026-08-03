"""Qualitätsgate nach dem Graph-Build (Issue #1029, Befund B-24).

`gemini-3.5-flash-lite` lieferte für dasselbe 1-KB-Dokument 3 Entitäten
und **0 Beziehungen**; zwei von vier Chunks meldeten `NER done: 0
entities, 0 relations`. Der Schritt meldete trotzdem „Abgeschlossen",
„Graph fertig." und „Weiter zur Umgebung → Bereit". Erst mehrere Schritte
später scheiterte der Report an fehlender Evidenz — an einem Symptom,
dessen Ursache hier liegt.

Die Zahlen lagen dem Build-Worker schon immer vor. Sie wurden nur nie
bewertet.
"""

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from app.services.degradation_collector import ChunkExtractionTally, DegradationCollector
from app.services.graph_builder import GraphBuilderService, GraphInfo


def _service() -> GraphBuilderService:
    return GraphBuilderService(storage=MagicMock(name="Storage"))


def _graph_info(node_count: int, edge_count: int) -> GraphInfo:
    return GraphInfo(
        graph_id="graph-1",
        node_count=node_count,
        edge_count=edge_count,
        entity_types=["Person"],
    )


def _tally(productive: int, total: int) -> ChunkExtractionTally:
    tally = ChunkExtractionTally()
    for index in range(total):
        # Produktive Chunks zuerst — die Reihenfolge ist für die Quote egal.
        tally.record_chunk(1, 1) if index < productive else tally.record_chunk(0, 0)
    return tally


class TestRelationThreshold:
    def test_graph_without_relations_blocks(self):
        """Der Fall aus B-24: 3 Entitäten, 0 Beziehungen, trotzdem „bereit"."""
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(3, 0), _tally(4, 4), degradations)

        events = degradations.report().events
        assert len(events) == 1
        assert events[0].kind is DegradationKind.GRAPH_BELOW_THRESHOLD
        assert events[0].severity is DegradationSeverity.BLOCKING
        assert degradations.report().has_blocking is True
        assert events[0].context["edge_count"] == 0
        assert events[0].context["node_count"] == 3

    def test_graph_with_relations_passes(self):
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(12, 8), _tally(4, 4), degradations)

        assert degradations.report().events == []

    def test_blocking_wins_over_the_entity_warning(self):
        """Ein Graph ohne Kanten ist blockiert, egal wie dünn er sonst ist.

        Sonst überschriebe die mildere Entitäten-Warnung den härteren
        Befund und der Weiter-Knopf bliebe offen.
        """
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(1, 0), _tally(4, 4), degradations)

        events = degradations.report().events
        assert len(events) == 1
        assert events[0].severity is DegradationSeverity.BLOCKING


class TestEntityThreshold:
    def test_too_few_entities_warns_but_does_not_block(self):
        """Dünn ist nicht wertlos — hier lohnt das Weitermachen noch."""
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(2, 5), _tally(4, 4), degradations)

        events = degradations.report().events
        assert len(events) == 1
        assert events[0].severity is DegradationSeverity.WARNING
        assert events[0].context["min_entities"] == Config.GRAPH_MIN_ENTITIES

    def test_entity_count_at_the_threshold_passes(self):
        degradations = DegradationCollector()

        _service()._assess_graph_quality(
            _graph_info(Config.GRAPH_MIN_ENTITIES, 5), _tally(4, 4), degradations
        )

        assert degradations.report().events == []


class TestChunkSuccessRatio:
    def test_half_the_document_unprocessed_warns(self):
        """Zwei von vier Chunks leer — genau der Nebenbefund aus B-24.

        Die Gesamtzahlen verraten das nicht: Der Graph kann genug
        Entitäten tragen und trotzdem aus der Hälfte des Dokuments nichts
        gezogen haben.
        """
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(20, 15), _tally(1, 4), degradations)

        events = degradations.report().events
        assert len(events) == 1
        assert events[0].severity is DegradationSeverity.WARNING
        assert events[0].context["productive_chunks"] == 1
        assert events[0].context["total_chunks"] == 4
        assert events[0].context["success_ratio"] == 0.25

    def test_good_ratio_passes(self):
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(20, 15), _tally(4, 4), degradations)

        assert degradations.report().events == []

    def test_build_without_chunks_is_not_flagged(self):
        """Kein Dokument ist ein anderer Fehler an einer anderen Stelle."""
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(20, 15), _tally(0, 0), degradations)

        assert degradations.report().events == []

    def test_ratio_check_is_switchable(self, monkeypatch: pytest.MonkeyPatch):
        degradations = DegradationCollector()
        monkeypatch.setattr(Config, "GRAPH_MIN_CHUNK_SUCCESS_RATIO", 0.0)

        _service()._assess_graph_quality(_graph_info(20, 15), _tally(1, 4), degradations)

        assert degradations.report().events == []

    def test_ratio_and_relation_findings_coexist(self):
        """Zwei unabhängige Befunde bleiben zwei Zeilen in der Oberfläche."""
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(20, 0), _tally(1, 4), degradations)

        events = degradations.report().events
        assert len(events) == 2
        assert degradations.report().has_blocking is True


class TestThresholdsAreConfigurable:
    def test_relation_threshold_follows_config(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Config, "GRAPH_MIN_RELATIONS", 5)
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(20, 4), _tally(4, 4), degradations)

        events = degradations.report().events
        assert len(events) == 1
        assert events[0].severity is DegradationSeverity.BLOCKING
        assert events[0].context["min_relations"] == 5

    def test_entity_threshold_follows_config(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Config, "GRAPH_MIN_ENTITIES", 50)
        degradations = DegradationCollector()

        _service()._assess_graph_quality(_graph_info(20, 15), _tally(4, 4), degradations)

        events = degradations.report().events
        assert len(events) == 1
        assert events[0].severity is DegradationSeverity.WARNING


class TestTally:
    def test_counts_productive_and_empty_chunks(self):
        tally = ChunkExtractionTally()
        tally.record_chunk(3, 2)
        tally.record_chunk(0, 0)
        tally.record_chunk(1, 0)
        tally.record_chunk(0, 1)

        assert tally.total == 4
        assert tally.productive == 3
        assert tally.empty == 1
        assert tally.success_ratio == 0.75

    def test_empty_tally_reports_full_success(self):
        assert ChunkExtractionTally().success_ratio == 1.0
