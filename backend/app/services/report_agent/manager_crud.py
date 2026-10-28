"""CRUD-Operationen und Repository-Anbindung für ReportManager."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import ValidationError

from ...contracts.report_record_contract import ReportRecord
from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ReportMode
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from . import manager_v3_builder as _v3

logger = get_logger("agora.report_agent")


if TYPE_CHECKING:
    class _ManagerMeta(type):
        def __getattr__(cls, name: str) -> Any: ...
else:
    _ManagerMeta = type


class ReportManagerCrudMixin(metaclass=_ManagerMeta):
    """Mixin für Report CRUD-Operationen und Persistenz."""

    @classmethod
    def save_report(
        cls,
        report: Report,
        *,
        report_mode: ReportMode = DEFAULT_REPORT_MODE,
    ) -> None:
        """SavereportmetainformationandcompleteReport"""
        cls._ensure_report_folder(report.report_id)

        evidence_map = cls.get_evidence_map(report.report_id)
        report.has_evidence = bool(evidence_map and evidence_map.get("sections"))
        report.evidence_sections = len((evidence_map or {}).get("sections", []))

        cls._get_repository().save(ReportRecord.from_dict(report.to_dict()))

        if report.outline:
            cls.save_outline(report.report_id, report.outline)

        if (
            report.status in (ReportStatus.COMPLETED, ReportStatus.INCOMPLETE)
            and evidence_map
        ):
            try:
                cls.save_report_v3(
                    cls.build_report_v3(report, evidence_map, report_mode=report_mode)
                )
            except ValidationError as exc:
                logger.warning(
                    "report-v3 artifact skipped for %s: %s", report.report_id, exc
                )

        logger.info("report saved (meta + v3-json): %s", report.report_id)

    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """getreport"""
        record = cls._get_repository().get(report_id)
        if record is None:
            return None
        return cls._build_report_from_record(report_id, record)

    @classmethod
    def _stored_records(cls) -> List[tuple[str, ReportRecord]]:
        repository = cls._get_repository()
        stored: List[tuple[str, ReportRecord]] = []
        for key in repository.list_ids():
            record = repository.get(key)
            if record is not None:
                stored.append((key, record))
        return stored

    @classmethod
    def _build_report_from_record(
        cls, report_id: str, record: ReportRecord
    ) -> Optional[Report]:
        return _v3.build_report_from_record(cls, report_id, record)

    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        for key, record in cls._stored_records():
            if record.simulation_id != simulation_id:
                continue
            report = cls._build_report_from_record(key, record)
            if report:
                return report
        return None

    @classmethod
    def list_reports(
        cls, simulation_id: Optional[str] = None, limit: int = 50
    ) -> List[Report]:
        reports = []
        for key, record in cls._stored_records():
            if simulation_id is not None and record.simulation_id != simulation_id:
                continue
            report = cls._build_report_from_record(key, record)
            if report:
                reports.append(report)

        reports.sort(key=lambda r: r.created_at, reverse=True)
        return reports[:limit]

    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        import shutil

        deleted = cls._get_repository().delete(report_id)

        folder_path = cls._get_report_folder(report_id)
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info("Report folder deleted: %s", report_id)
            deleted = True

        for suffix in (".md", ".json"):
            legacy_path = os.path.join(cls.REPORTS_DIR, f"{report_id}{suffix}")
            if os.path.exists(legacy_path):
                os.remove(legacy_path)
                deleted = True

        return deleted
