"""Sammelstelle für stille Teilausfälle während eines Pipeline-Laufs.

Issue #1029 · 2026-08-02

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


__all__ = ["DegradationCollector"]
