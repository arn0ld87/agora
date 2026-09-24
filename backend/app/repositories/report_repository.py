"""Port fuer Report-Metadaten (Issue #1580, Plan-PR 9 Teil 1).

Der Port beschreibt ausschliesslich die **Metadaten** eines Reports — den
Inhalt von ``reports/<report_id>/meta.json``. Die Report-Inhalte (Markdown,
ReportV3-JSON, Outline-Datei, Section-Dateien, Logs; Plan §11 Klasse B)
bleiben Dateien und laufen NICHT durch diesen Port — sie werden weiterhin
direkt ueber ``report_agent/storage.py`` gelesen und geschrieben.

Die Semantik ist die des heutigen Dateispeichers und wird hier
festgeschrieben, damit ein zweiter Adapter (Postgres, #1588) sie nicht
anders auslegt:

``get`` gibt ``None`` zurueck, wenn es den Report nicht gibt oder sein
Datensatz nicht lesbar ist (korruptes JSON, fehlendes Pflichtfeld). Ein
fehlender oder unlesbarer Datensatz ist ein erwarteter Fall — er wirft
nicht.

``save`` schreibt den Datensatz und gibt ihn zurueck. Kein zusaetzliches
Stempeln: anders als ``SimulationRecord``/``RunRecord`` traegt
``ReportRecord`` kein ``updated_at``-Feld, das die Ablage automatisch
pflegen wuerde — das entspricht dem heutigen ``ReportManager.save_report``,
das ebenfalls nichts stempelt.

``list`` liefert alle Reports, optional gefiltert nach ``simulation_id``.
Die Reihenfolge ist adapterabhaengig — kein Sortierversprechen hier. Die
Sortierung nach ``created_at`` (neueste zuerst) bleibt Sache von
``ReportManager.list_reports``, das seit jeher auf dem Domain-Objekt sortiert
und nicht auf dem rohen Datensatz.

Die Fabrik ``get_report_repository`` ist die einzige Stelle, an der ein
Consumer an ein Report-Repository kommt. Heute liefert sie ausschliesslich
den Dateiadapter; der PostgreSQL-Adapter folgt in #1588 ohne
Konfigurationsschalter in diesem Commit.
"""

from __future__ import annotations

import os
from typing import List, Optional, Protocol, runtime_checkable

from ..config import Config
from ..contracts.report_record_contract import ReportRecord


@runtime_checkable
class ReportRepository(Protocol):
    """Lesen und Schreiben von Report-Metadaten, unabhaengig von der Ablage."""

    def get(self, report_id: str) -> Optional[ReportRecord]:
        """Ein Datensatz oder ``None``, wenn es den Report nicht gibt.

        Wirft nicht bei fehlendem oder unlesbarem Report — ein korruptes
        oder unvollstaendiges Manifest zaehlt als fehlend, damit ein
        einzelner defekter Report nicht ``list``/``list_reports`` fuer alle
        anderen mitreisst.
        """
        ...

    def save(self, record: ReportRecord) -> ReportRecord:
        """Schreibt den Datensatz und gibt ihn zurueck.

        Erstellt das Ablageverzeichnis bei Bedarf. Kein automatisches
        Stempeln — ``ReportRecord`` hat kein ``updated_at``-Feld.
        """
        ...

    def list(self, simulation_id: Optional[str] = None) -> List[ReportRecord]:
        """Alle Reports, optional gefiltert nach Simulation.

        Reihenfolge: adapterabhaengig. Der Konsument
        (``ReportManager.list_reports``) sortiert selbst nach ``created_at``.
        """
        ...


def get_report_repository(reports_dir: Optional[str] = None) -> ReportRepository:
    """Die einzige Stelle, an der ein Consumer an ein Report-Repository kommt.

    Der Import des Adapters steht bewusst in der Funktion: ein Modul, das nur
    den Port braucht, soll die Ablage nicht mitladen.

    ``reports_dir`` ist der Ort der dateibasierten Ablage. Ohne Angabe faellt
    er auf ``<UPLOAD_FOLDER>/reports`` zurueck — denselben Pfad, den
    ``ReportManager.REPORTS_DIR`` bildet.

    Heute wird ausschliesslich der Dateiadapter geliefert. Ein
    Konfigurationsschalter kommt nicht — der PostgreSQL-Adapter folgt in
    #1588.
    """
    if reports_dir is None:
        reports_dir = os.path.join(Config.UPLOAD_FOLDER, "reports")

    from ..services.file_report_store import FileReportRepository

    return FileReportRepository(reports_dir)


__all__ = ["ReportRepository", "get_report_repository"]
