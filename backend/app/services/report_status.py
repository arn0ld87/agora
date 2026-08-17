"""Service for querying report generation status.

``get_status`` beantwortet dieselbe Frage — „wie steht es um diesen Report?" —
aus vier verschiedenen Quellen, je nachdem, welche IDs der Aufrufer kennt und
was davon noch existiert. Die Quellen sind nach Verlässlichkeit geordnet und
werden der Reihe nach befragt:

0. **Run-Registry** — der persistierte Lauf, sofern sein Status terminal ist.
1. **Persistierter Report** — abgeschlossen oder gescheitert.
2. **Lebender Task** — der laufende Generierungs-Task.
3. **Simulation** — irgendein fertiger Report zu dieser Simulation.
4. **Acknowledge** — nichts gefunden, der Aufrufer soll weiterpollen.

Jede Stufe liefert entweder ein fertiges Statusdokument oder ``None``, worauf
die nächste übernimmt. Stufe 1 hat zusätzlich eine Nebenwirkung: findet sie
keinen abschließenden Status, versorgt sie ``task_id`` und ``simulation_id``
für die Stufen danach. Diese Nebenwirkung ist der Grund, warum die Kette ein
gemeinsames, veränderliches ``_StatusQuery`` reicht statt reiner Argumente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..services.report_agent import ReportManager, ReportStatus
from ..services.report_export import ReportExportService
from ..services.run_registry import RunRegistry
from ..models.task import TaskManager
from ..utils.logger import get_logger

logger = get_logger(__name__)
run_registry = RunRegistry()

# Run-Status, bei denen der Registry-Eintrag die Auskunft abschließt. Ein
# unbekannter Status beendet die Kette bewusst nicht — dann entscheiden die
# späteren Stufen.
_CONCLUSIVE_RUN_STATUSES = {
    "completed",
    "failed",
    "paused",
    "stopped",
    "processing",
    "pending",
}


@dataclass
class _StatusQuery:
    """Die IDs, mit denen die Auflösungskette arbeitet.

    Veränderlich, weil Stufe 1 ``task_id`` und ``simulation_id`` für die
    nachfolgenden Stufen nachträgt.
    """

    task_id: Optional[str] = None
    simulation_id: Optional[str] = None
    report_id: Optional[str] = None


def _status_from_run_registry(query: _StatusQuery) -> Optional[dict[str, Any]]:
    """Stufe 0 — der persistierte Lauf, sofern sein Status abschließend ist."""
    if not query.report_id:
        return None
    run = run_registry.get_latest_by_linked_id(
        "report_id", query.report_id, run_type="report_generate"
    )
    if not run:
        return None

    progress_state = ReportManager.get_progress(query.report_id) or {}
    report_obj = ReportManager.get_report(query.report_id)
    generated_sections = {
        section.get("section_index"): {"content": section.get("content", "")}
        for section in ReportManager.get_generated_sections(query.report_id)
    }
    data = {
        "simulation_id": run.get("linked_ids", {}).get("simulation_id")
        or query.simulation_id,
        "report_id": query.report_id,
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "progress": run.get("progress", 0),
        "message": progress_state.get("message") or run.get("message", ""),
        "error": run.get("error"),
        "missing_sections": list(getattr(report_obj, "missing_sections", []) or []),
        "outline": ReportStatusService.map_outline_for_contract(
            report_obj.outline.to_dict()
        )
        if report_obj and report_obj.outline
        else None,
        "sections": generated_sections,
        "current_section_index": len(progress_state.get("completed_sections") or []),
    }

    # Issue #1277-2: Run-Registry ``completed`` heißt „Run beendet", nicht
    # „Report vollständig". ``run_generate`` schreibt den Registry-Status auch
    # bei INCOMPLETE auf ``completed`` (Teilergebnis, kein Fehlschlag — siehe
    # #1006). Der Polling-Consumer (``/api/report/generate/status`` ->
    # ``useReportGeneration``) müsste sonst den completed-Branch nehmen und
    # würde die Lücke verschweigen. Der Report-Status ist die fachliche
    # Wahrheit; er gewinnt, wenn der Run terminal ist.
    if (
        run.get("status") == "completed"
        and report_obj is not None
        and report_obj.status == ReportStatus.INCOMPLETE
    ):
        data["status"] = "incomplete"

    if run.get("status") in _CONCLUSIVE_RUN_STATUSES:
        return data
    return None


def _status_from_persisted_report(query: _StatusQuery) -> Optional[dict[str, Any]]:
    """Stufe 1a — ein abgeschlossener oder gescheiterter Report entscheidet.

    Nebenwirkung: ist der Report weder fertig noch gescheitert, wird seine
    ``simulation_id`` für die späteren Stufen übernommen.
    """
    existing_report = ReportManager.get_report(query.report_id)
    if not existing_report:
        return None

    sim_id = existing_report.simulation_id or query.simulation_id
    if existing_report.status == ReportStatus.COMPLETED:
        return {
            "simulation_id": sim_id,
            "report_id": query.report_id,
            "status": "completed",
            "progress": 100,
            "message": "Report generated",
            "already_completed": True,
        }
    if existing_report.status == ReportStatus.FAILED:
        return {
            "simulation_id": sim_id,
            "report_id": query.report_id,
            "status": "failed",
            "progress": 0,
            "message": "Report generation failed",
            "error": getattr(existing_report, "error", "") or "",
        }
    query.simulation_id = sim_id
    return None


def _adopt_task_from_metadata(query: _StatusQuery, task_manager: TaskManager) -> None:
    """Stufe 1b — sucht den lebenden Task über die Report-ID in den Metadaten.

    Ein kaputter oder leerer Task-Store darf den Status-Endpunkt nicht
    umbringen; der Fehler wird geloggt und die Kette läuft weiter.
    """
    try:
        for task in task_manager.list_tasks(task_type="report_generate") or []:
            meta = (
                task.get("metadata")
                if isinstance(task, dict)
                else getattr(task, "metadata", {})
            ) or {}
            if meta.get("report_id") != query.report_id:
                continue
            query.task_id = (
                task.get("task_id")
                if isinstance(task, dict)
                else getattr(task, "task_id", None)
            )
            if not query.simulation_id:
                query.simulation_id = meta.get("simulation_id")
            return
    except Exception as lookup_exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "report_id → task lookup failed for report_id=%s: %s",
            query.report_id,
            lookup_exc,
        )


def _status_from_task(
    query: _StatusQuery, task_manager: TaskManager
) -> Optional[dict[str, Any]]:
    """Stufe 2 — ein lebender Task ist maßgeblich."""
    if not query.task_id:
        return None

    task = task_manager.get_task(query.task_id)
    if not task:
        # Task-ID war gesetzt, ist aber tot (z. B. Serverneustart) — die
        # späteren Stufen übernehmen.
        logger.info(
            "task_id %s not found, falling back [simulation_id=%s, report_id=%s]",
            query.task_id,
            query.simulation_id,
            query.report_id,
        )
        return None

    payload = task.to_dict()
    if query.simulation_id and "simulation_id" not in payload:
        payload["simulation_id"] = query.simulation_id
    if query.report_id:
        payload["report_id"] = query.report_id
    return payload


def _status_from_simulation(query: _StatusQuery) -> Optional[dict[str, Any]]:
    """Stufe 3 — irgendein fertiger Report zu dieser Simulation.

    Greift nur ohne bekannte ``report_id``: sonst käme hier ein fremder Report
    als Antwort auf die Frage nach einem bestimmten.
    """
    if not query.simulation_id or query.report_id:
        return None

    existing_report = ReportManager.get_report_by_simulation(query.simulation_id)
    if not existing_report or existing_report.status != ReportStatus.COMPLETED:
        return None
    return {
        "simulation_id": query.simulation_id,
        "report_id": existing_report.report_id,
        "status": "completed",
        "progress": 100,
        "message": "Report generated",
        "already_completed": True,
    }


def _acknowledge_polling(query: _StatusQuery) -> Optional[dict[str, Any]]:
    """Stufe 4 — nichts gefunden, aber die Frage war zulässig."""
    if not (query.report_id or query.simulation_id):
        return None
    return {
        "simulation_id": query.simulation_id,
        "report_id": query.report_id,
        "status": "generating",
        "progress": 0,
        "message": "Task handle unknown — waiting for report completion",
    }


class ReportStatusService:
    # Die Abbildung „Dataclass-Outline -> v2-Contract-Form" gehoert dem
    # Export-Service; ``api/report.py`` bezieht sie ebenfalls von dort. Hier
    # stand bis 17.08.2026 eine zweite, bis auf Typannotationen zeichengleiche
    # Kopie — zwei Orte fuer dieselbe Mapping-Regel, von denen ein Fix nur
    # einen erwischt haette.
    # ``staticmethod(...)`` ist hier nicht kosmetisch: als blosses
    # Klassenattribut wuerde die Funktion bei Zugriff ueber eine *Instanz*
    # ``self`` als erstes Argument gebunden bekommen und das Outline-Dict
    # verlieren.
    map_outline_for_contract = staticmethod(ReportExportService.map_outline_for_contract)

    @classmethod
    def get_status(
        cls,
        task_id: Optional[str] = None,
        simulation_id: Optional[str] = None,
        report_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Löst den Report-Status über die Quellen-Kette auf (siehe Modul-Docstring)."""
        query = _StatusQuery(
            task_id=task_id, simulation_id=simulation_id, report_id=report_id
        )
        task_manager = TaskManager()

        result = _status_from_run_registry(query)
        if result is not None:
            return result

        if query.report_id and not query.task_id:
            result = _status_from_persisted_report(query)
            if result is not None:
                return result
            _adopt_task_from_metadata(query, task_manager)

        for stage in (
            lambda: _status_from_task(query, task_manager),
            lambda: _status_from_simulation(query),
            lambda: _acknowledge_polling(query),
        ):
            result = stage()
            if result is not None:
                return result

        from ..utils.api_errors import ApiErrorCode

        raise ValueError(ApiErrorCode.VALIDATION_FAILED)
