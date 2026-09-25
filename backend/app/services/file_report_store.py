"""Dateibasierter Adapter fuer Report-Metadaten (Issue #1580).

Das ist die bisherige ``meta.json``-Logik aus
``ReportManager.save_report``/``get_report``, hinter den ``ReportRepository``-
Port gelegt — eine Umstrukturierung, keine Neuimplementierung. Format und
Pfad von ``meta.json`` bleiben unveraendert, damit eine bestehende
Installation nach diesem Umbau dieselbe Datei liest und schreibt wie davor.

Die begleitenden Report-Inhalte (``report-v3.json``, ``outline.json``,
``section_XX.md``, Logs; Plan §11 Klasse B) laufen NICHT durch diesen
Adapter — sie bleiben direkte Dateizugriffe in ``ReportManager`` ueber
``report_agent/storage.py``.

Der Adapter nutzt dieselben atomaren Schreib-/Lesehelfer wie der Rest von
``report_agent`` (``write_json_atomic``/``read_json_safe`` aus
``report_agent/storage.py``), statt eine zweite I/O-Implementierung
einzufuehren.

**Legacy-Format:** Vor der Umstellung auf Report-Ordner lag die
Metadaten-Datei direkt als ``<reports_dir>/<report_id>.json``. ``get`` faellt
auf diesen Pfad zurueck, wenn ``<report_id>/meta.json`` fehlt — genau die
Fallback-Reihenfolge, die ``ReportManager.get_report`` bisher selbst
implementierte. ``save`` schreibt ausschliesslich das neue Ordnerformat,
ebenfalls unveraendert gegenueber dem bisherigen Verhalten.
"""

from __future__ import annotations

import os
from typing import List, Optional

from ..contracts.report_record_contract import ReportRecord
from ..utils.logger import get_logger
from .report_agent.storage import (
    ensure_report_folder,
    ensure_reports_dir,
    get_report_path,
    read_json_safe,
    write_json_atomic,
)

logger = get_logger("agora.report.file_store")


class FileReportRepository:
    """Report-Metadaten als ``meta.json`` je Reportverzeichnis."""

    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = reports_dir

    # --- Pfade -----------------------------------------------------------

    def _meta_path(self, report_id: str) -> str:
        return get_report_path(self.reports_dir, report_id)

    def _legacy_flat_path(self, report_id: str) -> str:
        return os.path.join(self.reports_dir, f"{report_id}.json")

    # --- Port --------------------------------------------------------------

    def get(self, report_id: str) -> Optional[ReportRecord]:
        """Ein Datensatz oder ``None``, wenn es den Report nicht gibt.

        Faellt auf das Legacy-Flachformat (``<report_id>.json`` direkt unter
        ``reports_dir``) zurueck, wenn das Ordnerformat fehlt — dieselbe
        Reihenfolge, die ``ReportManager.get_report`` bisher selbst pruefte.
        Ein korruptes oder unvollstaendiges Manifest zaehlt ebenfalls als
        fehlend (Warnung statt Absturz), damit ein einzelner defekter Report
        ``list`` nicht fuer alle anderen mitreisst.
        """
        path = self._meta_path(report_id)
        if not os.path.exists(path):
            legacy_path = self._legacy_flat_path(report_id)
            if not os.path.exists(legacy_path):
                return None
            path = legacy_path

        data = read_json_safe(path, logger)
        if not data:
            return None

        try:
            return ReportRecord.from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            # ValueError deckt pydantic.ValidationError mit ab, KeyError ein
            # fehlendes Pflichtfeld. Ein unlesbares Manifest zaehlt als fehlend.
            logger.warning(
                "Skipping unreadable report meta for %s: %s",
                report_id,
                type(exc).__name__,
            )
            return None

    def save(self, record: ReportRecord) -> ReportRecord:
        """Schreibt ``meta.json`` im (aktuellen) Ordnerformat."""
        ensure_report_folder(self.reports_dir, record.report_id)
        write_json_atomic(self._meta_path(record.report_id), record.to_dict())
        return record

    def delete(self, report_id: str) -> bool:
        """Entfernt ``meta.json`` (Ordnerformat) und ``<id>.json``
        (Legacy-Flachformat). Den Ordner mit den Inhalten raeumt
        ``ReportManager.delete_report`` ab."""
        removed = False
        for path in (self._meta_path(report_id), self._legacy_flat_path(report_id)):
            if os.path.exists(path):
                os.remove(path)
                removed = True
        return removed

    def list_ids(self) -> List[str]:
        """Ablageschluessel aller Reports: Ordnernamen (aktuelles Format) und
        ``<id>.json`` ohne Endung (Legacy-Flachformat).

        Der Schluessel ist nicht zwingend die ``report_id`` im Manifest: ein
        Altbestand kann unter ``report_deepseek_<hex>/`` liegen und
        ``report_<hex>`` eintragen (Codex-Review auf #1601). Die Artefakte
        daneben (Outline, Markdown, Evidence-Map) findet nur der Schluessel.
        """
        ensure_reports_dir(self.reports_dir)

        candidate_ids: dict[str, None] = {}
        for item in os.listdir(self.reports_dir):
            item_path = os.path.join(self.reports_dir, item)
            if os.path.isdir(item_path):
                candidate_ids.setdefault(item, None)
            elif item.endswith(".json"):
                candidate_ids.setdefault(item[:-5], None)
        return list(candidate_ids)

    def list(self, simulation_id: Optional[str] = None) -> List[ReportRecord]:
        """Alle Reports, optional gefiltert nach Simulation.

        Reihenfolge: adapterabhaengig.
        """
        records: list[ReportRecord] = []
        for report_id in self.list_ids():
            record = self.get(report_id)
            if record is None:
                continue
            if simulation_id is not None and record.simulation_id != simulation_id:
                continue
            records.append(record)

        return records


def get_file_report_repository(reports_dir: str) -> FileReportRepository:
    """Baut den Dateiadapter fuer den gegebenen Ablageort."""
    return FileReportRepository(reports_dir)


__all__ = ["FileReportRepository", "get_file_report_repository"]
