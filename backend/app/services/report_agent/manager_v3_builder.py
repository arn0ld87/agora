"""Erstellung und Rekonstruktion von ReportV3- und Report-Artefakten (Issue #1864)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ...contracts.report_record_contract import ReportRecord
from ...contracts.report_v3 import (
    DEFAULT_REPORT_MODE,
    RED_TEAM_FINDINGS_LIMIT,
    Claim as ReportV3Claim,
    DataGap as ReportV3DataGap,
    Hypothesis as ReportV3Hypothesis,
    ModelAttribution,
    ReportMode,
    ReportV3,
    SimulationContribution,
)
from ...models.report import Report, ReportOutline, ReportSection, ReportStatus
from ...utils.logger import get_logger
from ..evidence_migrations import normalize_persisted_evidence_map
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
from .simulation_contribution import compute_simulation_contribution

logger = get_logger("agora.report_agent")


def reset_review_state(cls: Any, report_id: str) -> None:
    """Issue #1340: Verwirft den Review-Stand eines vorherigen Laufs."""
    raw = cls.get_report_v3(report_id)
    if not isinstance(raw, dict):
        return
    if not raw.get("red_team_findings") and not raw.get("model_attribution"):
        return
    raw["red_team_findings"] = []
    raw["model_attribution"] = []
    cls._write_json_atomic(cls._get_report_v3_path(report_id), raw)
    logger.info(
        "Review-Stand des Vorlaufs fuer %s verworfen (neuer Generierungslauf)",
        report_id,
    )


def preserved_review_state(cls: Any, report_id: str) -> Dict[str, Any]:
    """Issue #1340: Felder, die nur nachgelagerte Stages befuellen koennen."""
    raw = cls.get_report_v3(report_id)
    if not isinstance(raw, dict):
        return {}
    preserved: Dict[str, Any] = {}

    findings = raw.get("red_team_findings")
    if isinstance(findings, list) and findings:
        if len(findings) <= RED_TEAM_FINDINGS_LIMIT and all(
            isinstance(item, str) for item in findings
        ):
            preserved["red_team_findings"] = list(findings)
        else:
            logger.warning(
                "red_team_findings aus report-v3.json fuer %s nicht uebernommen: "
                "%d Eintraege, Typen %s",
                report_id,
                len(findings),
                sorted({type(item).__name__ for item in findings}),
            )

    attribution = raw.get("model_attribution")
    if isinstance(attribution, list) and attribution:
        try:
            preserved["model_attribution"] = [
                ModelAttribution.model_validate(item) for item in attribution
            ]
        except ValidationError as exc:
            logger.warning(
                "model_attribution aus report-v3.json fuer %s nicht uebernommen: %s",
                report_id,
                exc,
            )
    return preserved


def build_report_v3(
    cls: Any,
    report: Report,
    evidence_map: Dict[str, Any],
    *,
    report_mode: ReportMode = DEFAULT_REPORT_MODE,
) -> ReportV3:
    """Baut das kanonische ReportV3-Artefakt aus Report und Evidenzkarte."""
    evidence_map = normalize_persisted_evidence_map(evidence_map) or evidence_map
    evidence_index = dict(evidence_map.get("evidence_index") or {})
    claims: List[ReportV3Claim] = []
    data_gaps: List[ReportV3DataGap] = []
    hypotheses: List[ReportV3Hypothesis] = []
    for section in evidence_map.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_index = int(section.get("section_index") or 0)
        claims.extend(
            _extract_claims_for_section(
                section.get("claims"),
                section_index=section_index,
                evidence_index=evidence_index,
                report_mode=report_mode,
            )
        )
        hypothesis_slots: list[tuple[str, list[dict[str, Any]]]] = [
            ("H", list(section.get("hypotheses") or [])),
            ("HA", list(section.get("hypotheses_appendix") or [])),
        ]
        hypothesis_export_ids = _build_hypothesis_export_ids(
            hypothesis_slots, section_index=section_index
        )
        data_gaps.extend(
            _extract_data_gaps_for_section(
                section.get("data_gaps"),
                section_index=section_index,
                hypothesis_export_ids=hypothesis_export_ids,
            )
        )
        hypotheses.extend(
            _extract_hypotheses_for_section(
                hypothesis_slots, section_index=section_index
            )
        )

    metadata_kwargs = _build_metadata_kwargs(
        evidence_map.get("sections") or [], evidence_index
    )
    claims = _dedup_claims_with_log(claims)
    preserved = cls._preserved_review_state(report.report_id)
    return ReportV3(
        report_id=report.report_id,
        generated_at=datetime.now(timezone.utc),
        evidence_index=evidence_index,
        report_mode=report_mode,
        claims=claims,
        data_gaps=data_gaps,
        hypotheses=hypotheses,
        **preserved,
        simulation_snapshot=report.simulation_snapshot,
        simulation_contribution=SimulationContribution.model_validate(
            compute_simulation_contribution(evidence_map, exported_claims=claims)
        ),
        **metadata_kwargs,
    )


def build_report_from_record(
    cls: Any, report_id: str, record: ReportRecord
) -> Optional[Report]:
    """Baut das ``Report``-Domain-Objekt aus einem ``ReportRecord``."""
    data = record.to_dict()

    outline_data = data.get("outline")
    if not outline_data:
        outline_data = cls._read_json_safe(cls._get_outline_path(report_id))

    outline = None
    if outline_data:
        sections = []
        for s in outline_data.get("sections", []):
            stored_desc = s.get("description") or s.get("content") or ""
            sections.append(ReportSection(
                title=s["title"],
                content=s.get("content", ""),
                description=stored_desc if stored_desc.strip() else "—",
                kind=str(s.get("kind") or "generic"),
            ))
        outline = ReportOutline(
            title=outline_data["title"],
            summary=outline_data["summary"],
            sections=sections,
        )

    markdown_content = data.get("markdown_content", "")
    if not markdown_content:
        full_report_path = cls._get_report_markdown_path(report_id)
        if os.path.exists(full_report_path):
            with open(full_report_path, "r", encoding="utf-8") as f:
                markdown_content = f.read()
    evidence_map = cls.get_evidence_map(report_id)

    return Report(
        report_id=data["report_id"],
        simulation_id=data["simulation_id"],
        graph_id=data["graph_id"],
        simulation_requirement=data["simulation_requirement"],
        status=ReportStatus(data["status"]),
        outline=outline,
        markdown_content=markdown_content,
        missing_sections=list(data.get("missing_sections") or []),
        created_at=data.get("created_at", ""),
        completed_at=data.get("completed_at", ""),
        error=data.get("error"),
        has_evidence=bool(
            data.get("has_evidence") or (evidence_map and evidence_map.get("sections"))
        ),
        evidence_sections=int(
            data.get("evidence_sections", 0)
            or len((evidence_map or {}).get("sections", []))
        ),
        simulation_snapshot=data.get("simulation_snapshot"),
        run_degradations=list(data.get("run_degradations") or []),
    )


__all__ = [
    "_CLAIM_TYPES",
    "_VALID_CONFIDENCE",
    "_text_confidence_for",
    "_dedup_claims_with_log",
    "_bind_and_dedup_thresholds",
    "_claim_type_of",
    "_wording_confidence",
    "_count_independent_sources",
    "_valid_evidence_refs_for_claim",
    "_should_downgrade_single_source",
    "_extract_claims_for_section",
    "_build_hypothesis_export_ids",
    "_extract_data_gaps_for_section",
    "_parse_optional_int",
    "_parse_clamped_confidence",
    "_extract_hypotheses_for_section",
    "_build_metadata_kwargs",
    "reset_review_state",
    "preserved_review_state",
    "build_report_v3",
    "build_report_from_record",
]
