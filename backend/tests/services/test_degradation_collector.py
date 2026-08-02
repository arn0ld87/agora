"""Tests für den DegradationCollector (Issue #1029).

Der Collector existiert, weil die Stelle, an der eine Degradierung
auffällt, nie die Stelle ist, an der sie gemeldet werden kann — und weil
die Graph-Chunks parallel laufen. Beide Eigenschaften werden hier
geprüft: Zusammenfassung gleichartiger Meldungen und Thread-Sicherheit.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from app.services.degradation_collector import DegradationCollector


class TestRecording:
    def test_empty_collector_is_falsy(self):
        collector = DegradationCollector()
        assert not collector
        assert len(collector) == 0
        assert collector.report().events == []
        assert collector.report().has_blocking is False

    def test_single_event_is_recorded_with_context(self):
        collector = DegradationCollector()
        collector.record(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.BLOCKING,
            detail="Graph ohne Kanten",
            context={"node_count": 3, "edge_count": 0},
        )

        events = collector.report().events
        assert len(events) == 1
        assert events[0].kind is DegradationKind.GRAPH_BELOW_THRESHOLD
        assert events[0].occurrences == 1
        assert events[0].context == {"node_count": 3, "edge_count": 0}
        assert collector.has_blocking is True

    def test_same_kind_and_detail_collapses_into_one_event(self):
        """Vierzig Chunks am selben abwesenden Ollama sind ein Befund, nicht vierzig."""
        collector = DegradationCollector()
        for _ in range(40):
            collector.record(
                kind=DegradationKind.EMBEDDING_UNAVAILABLE,
                severity=DegradationSeverity.WARNING,
                detail="Ollama nicht erreichbar",
            )

        events = collector.report().events
        assert len(events) == 1
        assert events[0].occurrences == 40

    def test_same_kind_different_detail_stays_separate(self):
        """Zwei Ursachen desselben Ausfalltyps bleiben unterscheidbar."""
        collector = DegradationCollector()
        collector.record(
            kind=DegradationKind.EMBEDDING_UNAVAILABLE,
            severity=DegradationSeverity.WARNING,
            detail="Ollama nicht erreichbar",
        )
        collector.record(
            kind=DegradationKind.EMBEDDING_UNAVAILABLE,
            severity=DegradationSeverity.WARNING,
            detail="Modell nicht geladen",
        )

        assert len(collector.report().events) == 2

    def test_blocking_escalates_a_previous_warning(self):
        collector = DegradationCollector()
        collector.record(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.WARNING,
            detail="knapp unter Schwelle",
        )
        collector.record(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.BLOCKING,
            detail="knapp unter Schwelle",
        )

        events = collector.report().events
        assert len(events) == 1
        assert events[0].severity is DegradationSeverity.BLOCKING

    def test_warning_never_downgrades_a_blocking(self):
        """Ein harmloser Nachzügler darf eine harte Einstufung nicht verwässern."""
        collector = DegradationCollector()
        collector.record(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.BLOCKING,
            detail="keine Kanten",
        )
        collector.record(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.WARNING,
            detail="keine Kanten",
        )

        assert collector.report().events[0].severity is DegradationSeverity.BLOCKING


class TestThreadSafety:
    def test_concurrent_records_do_not_lose_occurrences(self):
        """Der Graph-Build verarbeitet Chunks im ThreadPoolExecutor.

        Ohne Lock gehen bei gleichzeitigem ``record`` Zählungen verloren
        (read-modify-write auf ``occurrences``). Die Barrier erzwingt, dass
        alle Threads wirklich gleichzeitig eintreffen statt nacheinander.
        """
        collector = DegradationCollector()
        thread_count = 32
        barrier = threading.Barrier(thread_count)

        def _record() -> None:
            barrier.wait()
            collector.record(
                kind=DegradationKind.EMBEDDING_UNAVAILABLE,
                severity=DegradationSeverity.WARNING,
                detail="gleichzeitig",
            )

        with ThreadPoolExecutor(max_workers=thread_count) as pool:
            for future in [pool.submit(_record) for _ in range(thread_count)]:
                future.result()

        events = collector.report().events
        assert len(events) == 1
        assert events[0].occurrences == thread_count

    def test_concurrent_distinct_kinds_all_survive(self):
        collector = DegradationCollector()
        kinds = list(DegradationKind)
        repetitions = 12
        jobs = kinds * repetitions
        barrier = threading.Barrier(len(jobs))

        def _record(kind: DegradationKind) -> None:
            barrier.wait()
            collector.record(
                kind=kind,
                severity=DegradationSeverity.WARNING,
                detail=f"parallel {kind.value}",
            )

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            for future in [pool.submit(_record, kind) for kind in jobs]:
                future.result()

        events = collector.report().events
        assert len(events) == len(kinds)
        assert all(event.occurrences == repetitions for event in events)


class TestReportSerialization:
    def test_report_is_json_serializable(self):
        """Das Ergebnis geht als Task-Result durch JSON an die Oberfläche."""
        collector = DegradationCollector()
        collector.record(
            kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
            severity=DegradationSeverity.WARNING,
            detail="drei LLM-Versuche fehlgeschlagen",
            context={"attempts": 3, "profile": "AdministrativeEmployee"},
        )

        payload = collector.report().model_dump(mode="json")

        assert payload["schema_version"] == 1
        assert len(payload["events"]) == 1
        event = payload["events"][0]
        assert event["kind"] == "persona_rule_based_fallback"
        assert event["severity"] == "warning"
        assert isinstance(event["occurred_at"], str)
        assert event["context"] == {"attempts": 3, "profile": "AdministrativeEmployee"}
