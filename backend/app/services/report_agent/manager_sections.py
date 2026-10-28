"""Section-, Outline-, Progress- und Event-Methoden für ReportManager."""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from ...models.report import ReportOutline, ReportSection
from ...utils.logger import get_logger
from . import manager_markdown as _md
from .storage import (
    get_generated_sections as storage_get_generated_sections,
    write_outline,
    write_section_markdown,
)

logger = get_logger("agora.report_agent")


if TYPE_CHECKING:
    class _ManagerMeta(type):
        def __getattr__(cls, name: str) -> Any: ...
else:
    _ManagerMeta = type


class ReportManagerSectionsMixin(metaclass=_ManagerMeta):
    """Mixin für Abschnitts-, Outline-, Fortschritts- und Run-Event-Verwaltung."""

    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        cls._ensure_report_folder(report_id)
        write_outline(cls._get_outline_path(report_id), outline.to_dict())
        logger.info("Outline saved: %s", report_id)

    @classmethod
    def prepare_content_for_evidence(cls, content: str) -> str:
        return _md.prepare_content_for_evidence(cls, content)

    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection,
    ) -> str:
        cls._ensure_report_folder(report_id)
        cleaned_content = cls._clean_section_content(section.content, section.title)
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        write_section_markdown(file_path, section.title, cleaned_content)
        logger.info("Section saved: %s/%s", report_id, file_suffix)
        return file_path

    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        return _md.clean_section_content(cls, content, section_title)

    @classmethod
    def update_progress(
        cls,
        report_id: str,
        status: str,
        progress: int,
        message: str,
        current_section: Optional[str] = None,
        completed_sections: Optional[List[str]] = None,
    ) -> None:
        cls._ensure_report_folder(report_id)
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat(),
        }
        cls._write_json_atomic(cls._get_progress_path(report_id), progress_data)

    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        return cls._read_json_safe(cls._get_progress_path(report_id))

    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        return storage_get_generated_sections(cls.REPORTS_DIR, report_id)

    @classmethod
    def _save_run_event_indices(
        cls, report_id: str, key: str, section_indices: Iterable[int]
    ) -> None:
        existing = cls._read_json_safe(cls._get_run_events_path(report_id)) or {}
        existing[key] = sorted({int(index) for index in section_indices})
        cls._write_json_atomic(cls._get_run_events_path(report_id), existing)

    @classmethod
    def _load_run_event_indices(cls, report_id: str, key: str) -> set:
        data = cls._read_json_safe(cls._get_run_events_path(report_id)) or {}
        return {int(index) for index in (data.get(key) or [])}

    @classmethod
    def save_work_trace_removed_sections(
        cls, report_id: str, section_indices: Iterable[int]
    ) -> None:
        cls._save_run_event_indices(
            report_id, "work_trace_removed_sections", section_indices
        )

    @classmethod
    def load_work_trace_removed_sections(cls, report_id: str) -> set:
        return cls._load_run_event_indices(report_id, "work_trace_removed_sections")

    @classmethod
    def save_forced_final_sections(
        cls, report_id: str, section_indices: Iterable[int]
    ) -> None:
        cls._save_run_event_indices(report_id, "forced_final_sections", section_indices)

    @classmethod
    def load_forced_final_sections(cls, report_id: str) -> set:
        return cls._load_run_event_indices(report_id, "forced_final_sections")

    @classmethod
    def save_metadata_failed_sections(
        cls, report_id: str, section_indices: Iterable[int]
    ) -> None:
        cls._save_run_event_indices(
            report_id, "metadata_failed_sections", section_indices
        )

    @classmethod
    def load_metadata_failed_sections(cls, report_id: str) -> set:
        return cls._load_run_event_indices(report_id, "metadata_failed_sections")

    @classmethod
    def save_quote_validation_failed_sections(
        cls, report_id: str, section_indices: Iterable[int]
    ) -> None:
        cls._save_run_event_indices(
            report_id, "quote_validation_failed_sections", section_indices
        )

    @classmethod
    def load_quote_validation_failed_sections(cls, report_id: str) -> set:
        return cls._load_run_event_indices(
            report_id, "quote_validation_failed_sections"
        )

    @classmethod
    def save_fallback_outline_used(cls, report_id: str, used: bool) -> None:
        existing = cls._read_json_safe(cls._get_run_events_path(report_id)) or {}
        existing["fallback_outline_used"] = bool(used)
        cls._write_json_atomic(cls._get_run_events_path(report_id), existing)

    @classmethod
    def load_fallback_outline_used(cls, report_id: str) -> bool:
        data = cls._read_json_safe(cls._get_run_events_path(report_id)) or {}
        return bool(data.get("fallback_outline_used", False))
