"""Report-Status — Contract fuer ``POST /api/report/generate/status``
(Issue #1174, Muster aus #1458).

``ReportStatusService.get_status`` loest den Status ueber eine Kette von
Strategien auf (siehe ``app/services/report_status.py``-Modul-Docstring).
Dieser Contract deckt vier dieser fuenf Stufen ab — Run-Registry,
persistierter Report, Simulation, Acknowledge-Polling —, die alle dieselbe
Envelope-Form teilen. Die fuenfte Stufe (ein lebender Task, ``Task.to_dict()``)
bleibt aussen vor: ``Task`` ist eine ueber viele Services geteilte, gesperrte
Dataclass; ihre Umstellung auf einen Pydantic-Contract waere ein eigener,
groesserer Schnitt.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

# Vereinigung der Status-Werte aus allen vier abgedeckten Stufen:
# Run-Registry reicht ihren Rohwert durch (inkl. "incomplete", Issue #1277-2),
# die anderen drei Stufen setzen "completed"/"failed"/"generating" fest.
ReportStatusValue = Literal[
    "pending",
    "processing",
    "paused",
    "completed",
    "failed",
    "stopped",
    "incomplete",
    "generating",
]

# Stabile i18n-Schluessel (Frontend: `i18n/statusMessage.ts`, Kataloge unter
# `report.*` in `locales/{de,en}.json`). Optional: "incomplete"/"stopped" aus
# der Run-Registry-Stufe tragen (noch) keinen Schluessel — beide sind
# Randzustaende ausserhalb dieses Fixes; das Frontend faellt fuer sie auf
# `message` zurueck, wie vor #1174.
ReportMessageKey = Literal[
    "report.generated",
    "report.failed",
    "report.awaiting_task",
    "report.generating",
]


class ReportStatusResponse(BaseModel):
    """Statusantwort der vier literal-/registry-basierten Stufen von
    ``ReportStatusService.get_status``.

    ``message`` bleibt neben ``message_key`` als Klartext-Fallback fuer
    Consumer, die den Schluessel noch nicht kennen (Rueckwaertskompat.).
    """

    model_config = _STRICT

    simulation_id: Optional[str] = None
    report_id: Optional[str] = None
    status: ReportStatusValue
    progress: int = Field(ge=0, le=100)
    message: str
    message_key: Optional[ReportMessageKey] = None
    error: Optional[str] = None
    already_completed: Optional[bool] = None

    # Nur in der Run-Registry-Stufe (`_status_from_run_registry`).
    run_id: Optional[str] = None
    missing_sections: Optional[list[str]] = None
    # Form gespiegelt aus `ReportExportService.map_outline_for_contract`
    # ({title, summary, sections}); bewusst nicht `ReportOutlineModel` —
    # dessen Validatoren (Pflicht-Sektionstitel, Mindestlaengen) gelten fuer
    # den fertigen Export, nicht fuer eine noch wachsende Live-Outline
    # waehrend der Generierung.
    outline: Optional[dict[str, Any]] = None
    sections: Optional[dict[int, dict[str, Any]]] = None
    current_section_index: Optional[int] = None


__all__ = ["ReportStatusResponse", "ReportStatusValue", "ReportMessageKey"]
