"""
Service for querying report generation status.
"""

from ..services.report_agent import ReportManager, ReportStatus
from ..services.run_registry import RunRegistry
from ..models.task import TaskManager
from ..utils.logger import get_logger

logger = get_logger(__name__)
run_registry = RunRegistry()


class ReportStatusService:
    @staticmethod
    def map_outline_for_contract(outline: dict | None) -> dict | None:
        """Map the dataclass outline shape onto the v2 contract shape."""
        if not outline:
            return None
        sections: list[dict] = []
        for raw in outline.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            sections.append({
                "title": raw.get("title") or "Section",
                "description": raw.get("description") or raw.get("content") or "—",
            })
        return {
            "title": outline.get("title") or "Report",
            "summary": outline.get("summary") or "—",
            "sections": sections,
        }

    @classmethod
    def get_status(cls, task_id=None, simulation_id=None, report_id=None):
        task_manager = TaskManager()

        # ── 0) Prefer persisted run-registry status for report-specific polls ──
        if report_id:
            run = run_registry.get_latest_by_linked_id("report_id", report_id, run_type="report_generate")
            if run:
                progress_state = ReportManager.get_progress(report_id) or {}
                report_obj = ReportManager.get_report(report_id)
                generated_sections = {}
                for section in ReportManager.get_generated_sections(report_id):
                    generated_sections[section.get("section_index")] = {"content": section.get("content", "")}
                data = {
                    "simulation_id": run.get("linked_ids", {}).get("simulation_id") or simulation_id,
                    "report_id": report_id,
                    "run_id": run.get("run_id"),
                    "status": run.get("status"),
                    "progress": run.get("progress", 0),
                    "message": progress_state.get("message") or run.get("message", ""),
                    "error": run.get("error"),
                    "missing_sections": list(getattr(report_obj, "missing_sections", []) or []),
                    "outline": cls.map_outline_for_contract(report_obj.outline.to_dict()) if report_obj and report_obj.outline else None,
                    "sections": generated_sections,
                    "current_section_index": len(progress_state.get("completed_sections") or []),
                }
                if run.get("status") in {"completed", "failed", "paused", "stopped", "processing", "pending"}:
                    return data

        # ── 1) Resolve task_id + simulation_id from report_id if needed ────
        if report_id and not task_id:
            existing_report = ReportManager.get_report(report_id)
            if existing_report:
                # Already persisted — use its definitive status.
                sim_id = existing_report.simulation_id or simulation_id
                if existing_report.status == ReportStatus.COMPLETED:
                    return {
                        "simulation_id": sim_id,
                        "report_id": report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": "Report generated",
                        "already_completed": True,
                    }
                if existing_report.status == ReportStatus.FAILED:
                    return {
                        "simulation_id": sim_id,
                        "report_id": report_id,
                        "status": "failed",
                        "progress": 0,
                        "message": "Report generation failed",
                        "error": getattr(existing_report, "error", "") or "",
                    }
                simulation_id = sim_id
            # Either way, try to find the live task by metadata.
            try:
                for t in task_manager.list_tasks(task_type="report_generate") or []:
                    meta = (t.get("metadata") if isinstance(t, dict) else getattr(t, "metadata", {})) or {}
                    if meta.get("report_id") == report_id:
                        task_id = t.get("task_id") if isinstance(t, dict) else getattr(t, "task_id", None)
                        if not simulation_id:
                            simulation_id = meta.get("simulation_id")
                        break
            except Exception as lookup_exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning("report_id → task lookup failed for report_id=%s: %s", report_id, lookup_exc)

        # ── 2) If we have a task, that's authoritative ─────────────────────
        if task_id:
            task = task_manager.get_task(task_id)
            if task:
                payload = task.to_dict()
                if simulation_id and "simulation_id" not in payload:
                    payload["simulation_id"] = simulation_id
                if report_id:
                    payload["report_id"] = report_id
                return payload
            # Task id was provided but stale (e.g. server restart) — fall through.
            logger.info("task_id %s not found, falling back [simulation_id=%s, report_id=%s]", task_id, simulation_id, report_id)

        # ── 3) Only simulation_id known — look up *any* completed report ───
        if simulation_id and not report_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return {
                    "simulation_id": simulation_id,
                    "report_id": existing_report.report_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Report generated",
                    "already_completed": True
                }

        # ── 4) Fallback — caller keeps polling, we acknowledge ─────────────
        if report_id or simulation_id:
            return {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "status": "generating",
                "progress": 0,
                "message": "Task handle unknown — waiting for report completion",
            }

        from ..utils.api_errors import ApiErrorCode
        raise ValueError(ApiErrorCode.VALIDATION_FAILED)
