# ruff: noqa: F401, E402, F811
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ...config import Config
from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ReportMode, ReportV3
from ...models.report import Report, ReportOutline, ReportSection, ReportStatus
from ...repositories.report_repository import ReportRepository, get_report_repository
from ...utils.logger import get_logger
from . import manager_markdown as _md
from . import manager_v3_builder as _v3
from .claim_provenance import (
    derive_aggregation_basis,
    derive_confidence_scope as _derive_confidence_scope,
    resolve_voice_key,
)
from .manager_claims import (
    _CLAIM_TYPES,
    _VALID_CONFIDENCE,
    _bind_and_dedup_thresholds,
    _build_hypothesis_export_ids,
    _build_metadata_kwargs,
    _claim_type_of,
    _count_independent_sources,
    _dedup_claims_with_log,
    _extract_claims_for_section,
    _extract_data_gaps_for_section,
    _extract_hypotheses_for_section,
    _parse_clamped_confidence,
    _parse_optional_int,
    _should_downgrade_single_source,
    _text_confidence_for,
    _valid_evidence_refs_for_claim,
    _wording_confidence,
)
from .manager_crud import ReportManagerCrudMixin
from .manager_markdown import (
    _SIMULATED_QUOTE_ATTR_RE,
    _SIMULATED_QUOTE_TAG_RE,
    _render_simulated_quote_blocks,
)
from .manager_sections import ReportManagerSectionsMixin
from .storage import (
    ensure_report_folder,
    ensure_reports_dir,
    get_agent_log_path,
    get_console_log_path,
    get_evidence_map_path,
    get_generated_sections as storage_get_generated_sections,
    get_outline_path,
    get_progress_path,
    get_report_folder,
    get_report_markdown_path,
    get_report_path,
    get_report_v3_markdown_path,
    get_report_v3_path,
    get_run_events_path as storage_get_run_events_path,
    get_section_path,
    read_agent_log,
    read_console_log,
    read_json_safe,
    write_json_atomic,
    write_outline,
    write_section_markdown,
)

logger = get_logger("agora.report_agent")


class ReportManager(ReportManagerSectionsMixin, ReportManagerCrudMixin):
    """Persistence and retrieval facade for generated reports."""

    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, "reports")

    @classmethod
    def _ensure_reports_dir(cls):
        """ensurereportroot directory exists"""
        ensure_reports_dir(cls.REPORTS_DIR)

    @classmethod
    def _get_repository(cls) -> ReportRepository:
        return get_report_repository(cls.REPORTS_DIR)

    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        return get_report_folder(cls.REPORTS_DIR, report_id)

    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        return ensure_report_folder(cls.REPORTS_DIR, report_id)

    @classmethod
    def save_evidence_density(cls, report_id: str, density: Any) -> str:
        from .evidence_density import save_evidence_density

        return save_evidence_density(cls._ensure_report_folder(report_id), density)

    @classmethod
    def get_evidence_density(cls, report_id: str) -> Optional[Any]:
        from .evidence_density import read_evidence_density

        return read_evidence_density(cls._get_report_folder(report_id))

    @classmethod
    def get_stance_analysis(cls, report_id: str) -> Optional[Any]:
        from .stance_analysis import read_stance_analysis

        return read_stance_analysis(cls._get_report_folder(report_id))

    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        return get_report_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        return get_report_markdown_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_report_v3_path(cls, report_id: str) -> str:
        return get_report_v3_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_report_v3_markdown_path(cls, report_id: str) -> str:
        return get_report_v3_markdown_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        return get_outline_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        return get_progress_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        return get_section_path(cls.REPORTS_DIR, report_id, section_index)

    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        return get_agent_log_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        return get_console_log_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_evidence_map_path(cls, report_id: str) -> str:
        return get_evidence_map_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_run_events_path(cls, report_id: str) -> str:
        return storage_get_run_events_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _write_json_atomic(cls, path: str, payload: Any) -> None:
        write_json_atomic(path, payload)

    @classmethod
    def _read_json_safe(cls, path: str) -> Optional[Dict[str, Any]]:
        return read_json_safe(path, logger)

    @classmethod
    def get_console_log(cls, report_id: str) -> Optional[str]:
        return read_console_log(cls._get_console_log_path(report_id))

    @classmethod
    def get_console_log_stream(cls, report_id: str):
        return cls._get_console_log_path(report_id)

    @classmethod
    def get_agent_log(cls, report_id: str) -> Optional[str]:
        return read_agent_log(cls._get_agent_log_path(report_id))

    @classmethod
    def get_agent_log_stream(cls, report_id: str):
        return cls._get_agent_log_path(report_id)

    @classmethod
    def save_evidence_map(cls, report_id: str, data: Dict[str, Any]) -> None:
        cls._ensure_report_folder(report_id)
        cls._write_json_atomic(cls._get_evidence_map_path(report_id), data)

    @classmethod
    def get_evidence_map(cls, report_id: str) -> Optional[Dict[str, Any]]:
        return cls._read_json_safe(cls._get_evidence_map_path(report_id))

    @classmethod
    def save_report_v3(cls, report_v3: ReportV3) -> None:
        cls._ensure_report_folder(report_v3.report_id)
        cls._write_json_atomic(
            cls._get_report_v3_path(report_v3.report_id),
            report_v3.model_dump(mode="json"),
        )

    @classmethod
    def get_report_v3(cls, report_id: str) -> Optional[Dict[str, Any]]:
        return cls._read_json_safe(cls._get_report_v3_path(report_id))

    @classmethod
    def build_report_v3_markdown(cls, report_id: str) -> Optional[str]:
        return _md.build_report_v3_markdown(cls, report_id)

    @classmethod
    def reset_review_state(cls, report_id: str) -> None:
        _v3.reset_review_state(cls, report_id)

    @classmethod
    def _preserved_review_state(cls, report_id: str) -> Dict[str, Any]:
        return _v3.preserved_review_state(cls, report_id)

    @classmethod
    def build_report_v3(
        cls,
        report: Report,
        evidence_map: Dict[str, Any],
        *,
        report_mode: ReportMode = DEFAULT_REPORT_MODE,
    ) -> ReportV3:
        return _v3.build_report_v3(
            cls, report, evidence_map, report_mode=report_mode
        )

    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        return _md.assemble_full_report(cls, report_id, outline)

    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        return _md.post_process_report(cls, content, outline)


__all__ = [
    "ReportManager",
    "Report",
    "ReportOutline",
    "ReportSection",
    "ReportStatus",
    "_CLAIM_TYPES",
    "_VALID_CONFIDENCE",
    "_SIMULATED_QUOTE_ATTR_RE",
    "_SIMULATED_QUOTE_TAG_RE",
    "_bind_and_dedup_thresholds",
    "_build_hypothesis_export_ids",
    "_build_metadata_kwargs",
    "_claim_type_of",
    "_count_independent_sources",
    "_dedup_claims_with_log",
    "_extract_claims_for_section",
    "_extract_data_gaps_for_section",
    "_extract_hypotheses_for_section",
    "_parse_clamped_confidence",
    "_parse_optional_int",
    "_render_simulated_quote_blocks",
    "_should_downgrade_single_source",
    "_text_confidence_for",
    "_valid_evidence_refs_for_claim",
    "_wording_confidence",
    "derive_aggregation_basis",
    "_derive_confidence_scope",
    "resolve_voice_key",
]
