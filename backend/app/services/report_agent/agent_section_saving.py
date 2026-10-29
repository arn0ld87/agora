from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from pydantic import ValidationError

from .agent_hypotheses import ReportAgentHypothesesMixin
from .section_pipeline_steps import (
    _collect_evidence_refs_from_claim,
    _drop_unrepairable_section_entries,
    _extract_metadata_entry_claim_ids,
    _extract_metadata_entry_refs,
    _extract_verified_claims_and_evidence_ids,
    _filter_structured_metadata_against_verified_section,
    _find_metadata_entry_text,
    _is_metadata_entry_grounded,
    drop_unrepairable_section_entries,
    filter_structured_metadata_against_verified_section,
)
from .section_pipeline_types import SectionExecutionState

if TYPE_CHECKING:
    from .postprocess_timing import PostprocessPhaseTracker
    from .section_evidence_outcome import SectionEvidenceOutcome


class ReportAgentSectionSavingMixin(ReportAgentHypothesesMixin):
    """Section persistence and validation repair for ReportAgent."""

    if TYPE_CHECKING:
        evidence_map: Any
        _pending_section_metadata: Any

    def _ensure_normalized_evidence_map(self, report_id: str, _agent_mod: Any) -> Dict[str, str]:
        """Initialisiert oder normalisiert ``self.evidence_map`` und liefert ``id_remap``."""
        id_remap: Dict[str, str] = {}
        if self.evidence_map is None:
            self._init_evidence_map(report_id)
        else:
            self.evidence_map = (
                _agent_mod.normalize_persisted_evidence_map(self.evidence_map, remap_out=id_remap)
                or self.evidence_map
            )
            if id_remap:
                self._remap_active_evidence_ids(id_remap)
        self.evidence_map.setdefault("schema_version", _agent_mod.CURRENT_SCHEMA_VERSION)
        self.evidence_map.setdefault("evidence_index", {})
        self.evidence_map.setdefault("global_evidence_refs", [])
        return id_remap

    def _extract_and_finalize_section_claims(
        self,
        *,
        section_index: int,
        section_title: str,
        content: str,
        generation_failed: bool,
        id_remap: Dict[str, str],
        phase_tracker: Optional["PostprocessPhaseTracker"],
        _agent_mod: Any,
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        """Extrahiert und finalisiert die Claims der Sektion oder erzeugt einen Fallback-Gap."""
        if generation_failed:
            _agent_mod.logger.warning(
                "section %d (%r): Fallback-Inhalt — keine Claim-/Evidence-Extraktion.",
                section_index,
                section_title,
            )
            return (
                [],
                [],
                [
                    {
                        "gap_id": f"gap_{section_index:02d}",
                        "gap_reason": "Abschnitt konnte nicht generiert werden (LLM-Fehler).",
                        "claim_text": section_title,
                    }
                ],
                [],
            )

        def _phase(name: str):
            return phase_tracker.phase(name) if phase_tracker is not None else nullcontext()

        heartbeat_cb = phase_tracker.heartbeat if phase_tracker is not None else None
        with _phase("claim_extraction_and_evidence_binding"):
            extracted_claims = self._build_claims_for_section(content, heartbeat=heartbeat_cb)
        with _phase("claim_finalization"):
            claims, raw_hypotheses, data_gaps, gate_decisions = self._finalize_section_claims(
                extracted_claims
            )
        if id_remap:
            claims = _agent_mod._remap_claim_bindings(claims, id_remap)
        return claims, raw_hypotheses, data_gaps, gate_decisions

    def _merge_prose_hypotheses_and_gate_decisions(
        self,
        *,
        section_index: int,
        raw_hypotheses: List[Dict[str, Any]],
        gate_decisions: List[Dict[str, Any]],
        prose_entries: List[Any],
        _agent_mod: Any,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Führt Fließtext-Hypothesen, Gate-Entscheidungen und Hypothesen-Cap zusammen."""
        from .hypothesis_cap import dedup_and_cap_hypotheses  # noqa: PLC0415

        prose_hypotheses = [entry[0] for entry in prose_entries]
        combined_hypotheses = list(raw_hypotheses) + prose_hypotheses
        for position, hypothesis in enumerate(combined_hypotheses, start=1):
            if isinstance(hypothesis, dict):
                hypothesis["hypothesis_id"] = f"hypothesis_{position:02d}"
        gate_decisions.extend(_agent_mod.prose_gate_decisions(prose_entries, self._truncate))
        if gate_decisions:
            self.evidence_map["gate_decision_log"] = list(
                self.evidence_map.get("gate_decision_log") or []
            ) + [{**decision, "section_index": section_index} for decision in gate_decisions]

        coverage_ledger = _agent_mod.ledger_for(self)
        if coverage_ledger:
            self.evidence_map["evidence_coverage_ledger"] = coverage_ledger.as_payload()

        hypotheses_visible, hypotheses_appendix = dedup_and_cap_hypotheses(combined_hypotheses)
        return hypotheses_visible, hypotheses_appendix, gate_decisions

    def _validate_and_persist_evidence_map(
        self,
        *,
        report_id: str,
        section_index: int,
        section_title: str,
        content: str,
        section_entry: Dict[str, Any],
        _agent_mod: Any,
    ) -> Dict[str, Any]:
        """Fügt den Section-Eintrag ein, validiert/repariert EvidenceMapModel und speichert atomar."""
        existing_sections = _agent_mod.normalize_sections_for_contract(
            [s for s in self.evidence_map["sections"] if s.get("section_index") != section_index],
            evidence_index=_agent_mod.ReportAgent._evidence_index_map(cast(Any, self)),
        )
        dedup_marker = self._section_dedup_check(
            new_summary=section_title or content[:200],
            existing=existing_sections,
        )
        if dedup_marker is not None:
            claims = section_entry.get("claims") or []
            if claims:
                claims[0].setdefault("audit_trail", []).append(dedup_marker)
        existing_sections.append(section_entry)
        existing_sections.sort(key=lambda item: item.get("section_index", 0))
        self.evidence_map["sections"] = _agent_mod.normalize_sections_for_contract(
            existing_sections,
            evidence_index=_agent_mod.ReportAgent._evidence_index_map(cast(Any, self)),
            logger=_agent_mod.logger,
        )
        try:
            validated = _agent_mod.EvidenceMapModel.model_validate(self.evidence_map).model_dump(
                mode="json"
            )
        except ValidationError as first_error:
            repaired_sections, violations = _agent_mod.degrade_sections_for_violations(
                self.evidence_map["sections"],
                first_error,
                logger=_agent_mod.logger,
            )
            self.evidence_map["sections"] = repaired_sections
            self.evidence_map["degradation_log"] = (
                list(self.evidence_map.get("degradation_log") or []) + violations
            )
            _agent_mod.logger.warning(
                "_save_evidence_section: section=%d ValidationError repariert — %d Verstoss/Verstösse.",
                section_index,
                len(violations),
            )
            try:
                validated = _agent_mod.EvidenceMapModel.model_validate(
                    self.evidence_map
                ).model_dump(mode="json")
            except ValidationError as second_error:
                removed_entries = _drop_unrepairable_section_entries(
                    self.evidence_map["sections"], second_error
                )
                self.evidence_map["degradation_log"] = (
                    list(self.evidence_map.get("degradation_log") or []) + removed_entries
                )
                _agent_mod.logger.warning(
                    "_save_evidence_section: section=%d zweiter ValidationError — %d Eintrag/Einträge hart entfernt.",
                    section_index,
                    len(removed_entries),
                )
                validated = _agent_mod.EvidenceMapModel.model_validate(
                    self.evidence_map
                ).model_dump(mode="json")
        _agent_mod.cap_section_key_takeaways(validated, section_index)
        self.evidence_map = validated
        _agent_mod.ReportManager.save_evidence_map(report_id, validated)
        return validated

    def _save_evidence_section(
        self,
        report_id: str,
        section_index: int,
        section_title: str,
        content: str,
        *,
        section_state: Optional[SectionExecutionState] = None,
    ) -> "SectionEvidenceOutcome":
        """Extrahiert Claims, bindet Evidence und persistiert die Evidenzkarte."""
        from . import agent as _agent_mod
        from .output_contract import is_fallback_content  # noqa: PLC0415

        state = section_state or SectionExecutionState.from_agent_pending(
            self,
            section_index=section_index,
            title=section_title,
            content=content,
        )
        state.sync_from_agent_hooks(self)

        report_logger = getattr(self, "report_logger", None)
        phase_tracker: Optional[PostprocessPhaseTracker] = None
        if report_logger is not None:
            phase_tracker = _agent_mod.PostprocessPhaseTracker(
                report_id,
                section_index=section_index,
                section_title=section_title,
                report_logger=report_logger,
                report_manager=_agent_mod.ReportManager,
            )

        id_remap = ReportAgentSectionSavingMixin._ensure_normalized_evidence_map(
            self, report_id, _agent_mod
        )
        generation_failed = is_fallback_content(content)
        claims, raw_hypotheses, data_gaps, gate_decisions = (
            ReportAgentSectionSavingMixin._extract_and_finalize_section_claims(
                self,
                section_index=section_index,
                section_title=section_title,
                content=content,
                generation_failed=generation_failed,
                id_remap=id_remap,
                phase_tracker=phase_tracker,
                _agent_mod=_agent_mod,
            )
        )

        prose_entries = state.prose_hypotheses or (
            getattr(self, "_pending_prose_hypotheses", {}) or {}
        ).get(section_index, [])
        hypotheses_visible, hypotheses_appendix, gate_decisions = (
            ReportAgentSectionSavingMixin._merge_prose_hypotheses_and_gate_decisions(
                self,
                section_index=section_index,
                raw_hypotheses=raw_hypotheses,
                gate_decisions=gate_decisions,
                prose_entries=prose_entries,
                _agent_mod=_agent_mod,
            )
        )

        raw_metadata = state.raw_metadata or (
            getattr(self, "_pending_section_metadata", {}) or {}
        ).get(section_index, {})
        filtered_metadata = _filter_structured_metadata_against_verified_section(
            raw_metadata,
            verified_claims=claims,
            persisted_content=content,
        )
        state.filtered_metadata = filtered_metadata
        if hasattr(self, "_pending_section_metadata") and isinstance(
            self._pending_section_metadata, dict
        ):
            self._pending_section_metadata[section_index] = filtered_metadata

        quote_validation_failed = bool(
            state.quote_validation_failed
            or (getattr(self, "_pending_quote_validation_failed", {}) or {}).get(
                section_index, False
            )
        )
        unbound_refs = list(
            state.unbound_evidence_refs
            or (getattr(self, "_pending_unbound_evidence_refs", {}) or {}).get(section_index, [])
        )
        unverified_statements = list(
            state.unverified_statements
            or (getattr(self, "_pending_unverified_statements", {}) or {}).get(section_index, [])
        )

        section_entry = {
            "section_index": section_index,
            "section_title": section_title,
            "section_summary": self._truncate(content, 400),
            "claims": claims,
            "hypotheses": hypotheses_visible,
            "hypotheses_appendix": hypotheses_appendix,
            "data_gaps": data_gaps,
            "structured_metadata": filtered_metadata,
            "generation_failed": generation_failed,
            "quote_validation_failed": quote_validation_failed,
            "unbound_evidence_refs": unbound_refs,
            "unverified_statements": unverified_statements,
        }
        if phase_tracker is not None:
            phase_tracker.start_phase("evidence_map_persistence")

        validated = ReportAgentSectionSavingMixin._validate_and_persist_evidence_map(
            self,
            report_id=report_id,
            section_index=section_index,
            section_title=section_title,
            content=content,
            section_entry=section_entry,
            _agent_mod=_agent_mod,
        )
        if phase_tracker is not None:
            phase_tracker.end_phase()
        outcome = _agent_mod.SectionEvidenceOutcome.from_persisted_section(
            validated,
            section_index,
            gate_decisions=gate_decisions,
            generation_failed=generation_failed,
        )
        state.evidence_outcome = outcome
        return outcome

    def _record_section_metadata(self, section_index: int, metadata: Dict[str, Any]) -> None:
        """Merkt die Struktur-Metadaten eines Abschnitts für ReportV3 vor."""
        if not metadata:
            return
        if not hasattr(self, "_pending_section_metadata") or self._pending_section_metadata is None:
            self._pending_section_metadata = {}
        self._pending_section_metadata[section_index] = metadata


__all__ = [
    "ReportAgentSectionSavingMixin",
    "ReportAgentHypothesesMixin",
    "_collect_evidence_refs_from_claim",
    "_drop_unrepairable_section_entries",
    "_extract_metadata_entry_claim_ids",
    "_extract_metadata_entry_refs",
    "_extract_verified_claims_and_evidence_ids",
    "_filter_structured_metadata_against_verified_section",
    "_find_metadata_entry_text",
    "_is_metadata_entry_grounded",
    "drop_unrepairable_section_entries",
    "filter_structured_metadata_against_verified_section",
]
