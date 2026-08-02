"""Qualitätssignale, die von unten nach oben durch die Pipeline wandern.

Issue #1029 · 2026-08-02

Zwei Dinge leben hier, weil sie denselben Weg gehen: der
``DegradationCollector`` für fertige Befunde und der
``ChunkExtractionTally`` für die Rohzahlen, aus denen erst weiter oben
ein Befund wird.

Der Ort, an dem eine Degradierung auffällt, ist selten der Ort, an dem sie
gemeldet werden kann. Das Batch-Embedding scheitert tief in
``ingestion_pipeline``; sichtbar werden muss der Ausfall vier Ebenen höher
im Ergebnis des Graph-Build-Tasks. Dazwischen liegt ein
``ThreadPoolExecutor``, der die Chunks parallel abarbeitet.

Der Collector löst beides: Er wird von oben nach unten durchgereicht und
ist thread-safe. Gleichartige Ereignisse fasst er zusammen — vierzig
Chunks, die alle am selben abwesenden Ollama scheitern, ergeben einen
Eintrag mit ``occurrences=40`` statt vierzig Zeilen Rauschen.

Bewusst kein ``contextvars``-Ansatz: ``ThreadPoolExecutor.submit`` kopiert
den Kontext nicht, und ein explizites Argument ist testbar, ohne globalen
Zustand aufzuräumen.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Optional

from ..contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
    PipelineDegradationModel,
    PipelineDegradationReport,
)
from ..utils.logger import get_logger

logger = get_logger("agora.degradation")


class DegradationCollector:
    """Thread-safer Sammler für ``PipelineDegradationModel``-Ereignisse.

    Zusammengefasst wird nach ``(kind, detail)``. Der Schlüssel enthält
    absichtlich das Detail: derselbe Ausfalltyp aus zwei verschiedenen
    Ursachen bleibt so unterscheidbar, während der Regelfall — dieselbe
    Fehlermeldung aus N parallelen Chunks — auf einen Eintrag kollabiert.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[tuple[DegradationKind, str], PipelineDegradationModel] = {}

    def record(
        self,
        kind: DegradationKind,
        severity: DegradationSeverity,
        detail: str,
        context: Optional[Mapping[str, str | int | float]] = None,
    ) -> None:
        """Meldet einen Teilausfall. Idempotent gegenüber Wiederholungen.

        Wird dasselbe ``(kind, detail)`` erneut gemeldet, steigt nur der
        Zähler. Ein späteres ``BLOCKING`` hebt eine zuvor als ``WARNING``
        eingestufte Meldung an — nie umgekehrt, sonst könnte ein
        harmloser Nachzügler eine harte Einstufung verwässern.
        """
        key = (kind, detail)
        with self._lock:
            existing = self._events.get(key)
            if existing is None:
                self._events[key] = PipelineDegradationModel(
                    kind=kind,
                    severity=severity,
                    detail=detail,
                    context=dict(context or {}),
                )
                logger.warning(
                    "Pipeline-Degradierung erfasst: kind=%s severity=%s detail=%s",
                    kind.value,
                    severity.value,
                    detail,
                )
                return

            escalated = (
                DegradationSeverity.BLOCKING
                if DegradationSeverity.BLOCKING in (existing.severity, severity)
                else existing.severity
            )
            self._events[key] = existing.model_copy(
                update={
                    "occurrences": existing.occurrences + 1,
                    "severity": escalated,
                }
            )

    def report(self) -> PipelineDegradationReport:
        """Momentaufnahme als Contract-Objekt, sortiert nach erstem Auftreten."""
        with self._lock:
            events = sorted(self._events.values(), key=lambda event: event.occurred_at)
        return PipelineDegradationReport(events=events)

    @property
    def has_blocking(self) -> bool:
        return self.report().has_blocking

    def __bool__(self) -> bool:
        """Falsy, solange nichts degradiert ist."""
        with self._lock:
            return bool(self._events)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


class ChunkExtractionTally:
    """Zählt, wie viele Chunks der NER überhaupt etwas entnommen hat.

    Ein einzelner leerer Chunk ist kein Befund — er kann schlicht eine
    Kapitelüberschrift enthalten. Erst der Anteil macht ihn zu einem: Bei
    Befund B-24 meldeten zwei von vier Chunks ``0 entities, 0 relations``,
    die Hälfte des Dokuments war also nicht erfasst, und die
    Gesamtzahlen verrieten davon nichts.

    Deshalb ein reiner Zähler und kein ``DegradationCollector``-Eintrag:
    Die Bewertung passiert einmal am Ende des Builds, wo die Gesamtzahl
    der Chunks bekannt ist — nicht N-mal währenddessen.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._productive = 0

    def record_chunk(self, entity_count: int, relation_count: int) -> None:
        """Verbucht einen verarbeiteten Chunk. Thread-safe."""
        with self._lock:
            self._total += 1
            if entity_count > 0 or relation_count > 0:
                self._productive += 1

    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    @property
    def productive(self) -> int:
        with self._lock:
            return self._productive

    @property
    def empty(self) -> int:
        with self._lock:
            return self._total - self._productive

    @property
    def success_ratio(self) -> float:
        """Anteil produktiver Chunks. Ohne Chunks per Definition 1.0.

        Der Leerfall ist bewusst „alles in Ordnung" und nicht 0.0 — ein
        Build ohne Chunks hat kein Extraktionsproblem, sondern kein
        Dokument, und das ist ein anderer Fehler an einer anderen Stelle.
        """
        with self._lock:
            if self._total == 0:
                return 1.0
            return self._productive / self._total


__all__ = ["ChunkExtractionTally", "DegradationCollector"]
