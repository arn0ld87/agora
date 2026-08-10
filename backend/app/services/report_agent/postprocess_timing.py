"""Sichtbarkeits-Instrumentierung fuer die Report-Nachbearbeitung (Issue #1187).

Befund (Lauf ``report_b76cf7078229``): zwischen "Section-Text fertig" und
"Section saved" lagen 178-347s ohne eine einzige Logzeile und ohne
``progress.json``-Update — 59 % der Gesamtlaufzeit. Ein arbeitender Lauf war
von einem abgestuerzten nicht unterscheidbar.

:class:`PostprocessPhaseTracker` macht die Nachbearbeitung sichtbar und
messbar:

* Jede Phase (Metadaten-Extraktion, Claim-Extraktion, Evidence-Binding,
  Persistenz der Evidenzkarte) bekommt Start/Ende/Dauer im strukturierten
  Log (:meth:`~app.services.report_logger.ReportLogger.log_phase_timing`).
* ``progress.json`` wird bei jedem Phasenwechsel aktualisiert — nicht nur
  beim Abschnittswechsel.
* :meth:`PostprocessPhaseTracker.heartbeat` erlaubt langlaufenden Schleifen
  (z. B. Claim-fuer-Claim Evidence-Binding) periodische Lebenszeichen, ohne
  ``progress.json`` bei jedem Claim neu zu schreiben.

Macht die Nachbearbeitung ausdruecklich NICHT schneller — das ist Issue
#1190, bewusst blockiert bis diese Instrumentierung belastbare Phasenzeiten
liefert.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional

from ...utils.logger import get_logger
from .manager import ReportManager as _DefaultReportManager

logger = get_logger("agora.report_agent")

#: Mindestabstand zwischen zwei Heartbeat-Updates innerhalb derselben Phase.
#: Verhindert progress.json-Spam bei vielen Claims, haelt aber lange Phasen
#: (Messung: bis zu 347s) sichtbar in Bewegung.
HEARTBEAT_INTERVAL_SECONDS = 20.0


class PostprocessPhaseTracker:
    """Trackt Nachbearbeitungsphasen fuer eine einzelne Section.

    Eine Instanz lebt fuer die Dauer der Nachbearbeitung EINER Section. Sie
    liest optional den aktuellen Fortschrittsstand aus ``progress.json``,
    damit der gemeldete Prozentwert/die ``completed_sections``-Liste nicht
    zurueckspringt, wenn Aufrufer (z. B. ``agent.py``) den Wert nicht kennen.
    """

    def __init__(
        self,
        report_id: str,
        *,
        section_index: int,
        section_title: str,
        base_progress: Optional[int] = None,
        completed_sections: Optional[List[str]] = None,
        report_logger: Any = None,
        report_manager: Any = None,
    ) -> None:
        self.report_id = report_id
        self.section_index = section_index
        self.section_title = section_title
        self.report_logger = report_logger
        # Injizierbar, damit Aufrufer (workflow.py, agent.py) ihre eigene,
        # in Tests patchbare ``ReportManager``-Namensbindung durchreichen
        # koennen statt dass dieses Modul unbeachtet an einer eigenen,
        # unge-mockten Bindung vorbeischreibt.
        self._report_manager = report_manager or _DefaultReportManager

        # Zwei getrennte, einfache Narrowing-Checks statt einer
        # "or"-verknuepften Bedingung — mypy narrowt ``int | None``
        # zuverlaessig nur ueber ein direktes ``if x is None: x = ...``.
        if base_progress is None:
            current_progress = self._report_manager.get_progress(report_id) or {}
            base_progress = int(current_progress.get("progress") or 0)
        if completed_sections is None:
            current_completed = self._report_manager.get_progress(report_id) or {}
            completed_sections = list(current_completed.get("completed_sections") or [])

        self.base_progress: int = base_progress
        self.completed_sections: List[str] = completed_sections

        self._phase_name: Optional[str] = None
        self._phase_started_at: Optional[float] = None
        self._last_heartbeat_at: Optional[float] = None

    def _report_progress(self, message: str) -> None:
        try:
            self._report_manager.update_progress(
                self.report_id,
                "generating",
                self.base_progress,
                message,
                current_section=self.section_title,
                completed_sections=self.completed_sections,
            )
        except Exception:  # noqa: BLE001 — Fortschrittsmeldung darf Postprocessing nie stoppen
            logger.warning(
                "postprocess progress update failed: report=%s section=%d",
                self.report_id,
                self.section_index,
                exc_info=True,
            )

    @contextmanager
    def phase(self, name: str) -> Iterator["PostprocessPhaseTracker"]:
        """Context-Manager-Variante von :meth:`start_phase`/:meth:`end_phase`."""
        self.start_phase(name)
        try:
            yield self
        finally:
            self.end_phase()

    def start_phase(self, name: str) -> None:
        self._phase_name = name
        self._phase_started_at = time.monotonic()
        self._last_heartbeat_at = self._phase_started_at
        logger.info(
            "postprocess phase start: report=%s section=%d phase=%s",
            self.report_id,
            self.section_index,
            name,
        )
        self._report_progress(
            f"Nachbearbeitung Abschnitt {self.section_index} "
            f"({self.section_title}): {name} gestartet"
        )

    def heartbeat(self, detail: str = "") -> None:
        """Von langlaufenden Schleifen innerhalb einer Phase aufzurufen.

        No-op wenn keine Phase laeuft oder das Heartbeat-Intervall noch
        nicht abgelaufen ist — verhindert progress.json-Spam.
        """
        if self._phase_started_at is None or self._last_heartbeat_at is None:
            return
        now = time.monotonic()
        if now - self._last_heartbeat_at < HEARTBEAT_INTERVAL_SECONDS:
            return
        self._last_heartbeat_at = now
        elapsed = now - self._phase_started_at
        suffix = f" — {detail}" if detail else ""
        logger.info(
            "postprocess heartbeat: report=%s section=%d phase=%s elapsed_seconds=%.0f detail=%r",
            self.report_id,
            self.section_index,
            self._phase_name,
            elapsed,
            detail,
        )
        self._report_progress(
            f"Nachbearbeitung Abschnitt {self.section_index} "
            f"({self.section_title}): {self._phase_name} laeuft seit "
            f"{elapsed:.0f}s{suffix}"
        )

    def end_phase(self) -> float:
        """Beendet die laufende Phase und gibt ihre Dauer in Sekunden zurueck."""
        if self._phase_started_at is None:
            return 0.0
        duration = time.monotonic() - self._phase_started_at
        name = self._phase_name or "<unknown>"
        logger.info(
            "postprocess phase end: report=%s section=%d phase=%s duration_seconds=%.2f",
            self.report_id,
            self.section_index,
            name,
            duration,
        )
        if self.report_logger is not None and hasattr(self.report_logger, "log_phase_timing"):
            self.report_logger.log_phase_timing(
                phase=name,
                duration_seconds=duration,
                section_title=self.section_title,
                section_index=self.section_index,
            )
        self._report_progress(
            f"Nachbearbeitung Abschnitt {self.section_index} "
            f"({self.section_title}): {name} abgeschlossen ({duration:.1f}s)"
        )
        self._phase_name = None
        self._phase_started_at = None
        self._last_heartbeat_at = None
        return duration


__all__ = ["PostprocessPhaseTracker", "HEARTBEAT_INTERVAL_SECONDS"]
