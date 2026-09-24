"""Vertrag fuer Report-Metadaten (Issue #1580, Plan-PR 9 Teil 1).

Dieser Vertrag beschreibt ausschliesslich die Metadaten eines Reports — den
Inhalt von ``reports/<report_id>/meta.json``. Die begleitenden Artefakte
(``report-v3.json``, ``outline.json``, ``section_XX.md``, ``progress.json``,
``evidence_map.json``, ``agent_log.jsonl``, ``console_log.txt``,
``run_events.json``) sind keine Metadaten im Sinne dieses Vertrags — sie sind
Plan-§11-Klasse-B-Inhalte (grosse/strukturierte Report-Inhalte) und bleiben
Dateien, die direkt ueber ``report_agent/storage.py`` gelesen/geschrieben
werden. Sie laufen NICHT durch ``ReportRepository``.

``outline`` und ``simulation_snapshot`` bleiben als generische ``dict``
stehen statt als eigene Pydantic-Modelle: beide sind bereits an anderer
Stelle vertraglich gefasst (``ReportOutline``/Simulationszustand) und dieser
Vertrag soll die Ablage von ``meta.json`` 1:1 abbilden, nicht eine zweite
Modellierung derselben Struktur einfuehren. Dieselbe Entscheidung trifft
``run_record_contract.py`` fuer ``artifacts``/``metadata``.

Fuenf Felder sind Pflicht, weil der heutige Ladepfad
(``ReportManager.get_report``) sie ohne Rueckfallwert aus dem Dict liest
(``data['report_id']`` usw.) und bei Abwesenheit ohnehin scheitert:
``report_id``, ``simulation_id``, ``graph_id``, ``simulation_requirement``,
``status``. Alle uebrigen Felder haben Vorgabewerte, weil der heutige
Ladepfad sie ebenfalls ueber ``.get(...)`` mit Rueckfallwert liest — ein
Altbestand ohne diese Felder (z. B. vor Einfuehrung von
``simulation_snapshot``, Issue #1192) bleibt damit lesbar.

``status`` ist bewusst ``str`` und nicht ``ReportStatus``: der Vertrag soll
keine Laufzeit-Abhaengigkeit zu ``app.models.report`` tragen. Die Umwandlung
in ``ReportStatus`` bleibt Sache von ``ReportManager``.

Der Vertrag ist ein interner Persistenzvertrag, kein API-Vertrag. Er wird
nicht in ``dump_schemas`` aufgenommen und hat kein ``schemas/``-Gegenstueck
(wie ``simulation_record_contract.py`` und ``run_record_contract.py``).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReportRecord(BaseModel):
    """Metadaten eines Reports — der Inhalt von ``meta.json``.

    ``to_dict``/``from_dict`` halten das Format von ``meta.json``
    unveraendert, damit eine bestehende Installation nach diesem Umbau
    dieselbe Datei liest und schreibt wie davor.
    """

    model_config = ConfigDict(extra="ignore")

    report_id: str = Field(..., min_length=1)
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: str

    outline: Optional[dict[str, Any]] = None
    markdown_content: str = ""
    missing_sections: list[str] = Field(default_factory=list)
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    has_evidence: bool = False
    evidence_sections: int = 0
    # Issue #1192: fehlt bei Reports, die vor der Einfuehrung geschrieben
    # wurden — dort bleibt der Stand unbekannt (``None``).
    simulation_snapshot: Optional[dict[str, Any]] = None
    run_degradations: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert fuer ``meta.json``.

        Ausdruecklich handgeschrieben statt ``model_dump()``: Schluessel und
        Reihenfolge entsprechen ``Report.to_dict()``, damit eine bestehende
        Ablage nach dem Umbau identisch aussieht.
        """
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status,
            "outline": self.outline,
            "markdown_content": self.markdown_content,
            "missing_sections": list(self.missing_sections),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "has_evidence": self.has_evidence,
            "evidence_sections": self.evidence_sections,
            "simulation_snapshot": self.simulation_snapshot,
            "run_degradations": list(self.run_degradations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReportRecord":
        """Liest einen Datensatz aus der Ablage.

        Die fuenf Pflichtfelder wirft bei Abwesenheit eine
        ``pydantic.ValidationError`` — genau wie der bisherige Ladepfad bei
        einem fehlenden Schluessel mit ``KeyError`` scheiterte. Alle
        uebrigen Felder fallen auf ihre Vorgabewerte zurueck; unbekannte
        Schluessel werden verworfen (``extra="ignore"``).
        """
        return cls.model_validate(data)


__all__ = ["ReportRecord"]
