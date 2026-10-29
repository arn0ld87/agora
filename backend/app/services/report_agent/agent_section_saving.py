from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from pydantic import ValidationError

from .agent_hypotheses import ReportAgentHypothesesMixin

if TYPE_CHECKING:
    from .section_evidence_outcome import SectionEvidenceOutcome
    from .postprocess_timing import PostprocessPhaseTracker


def _drop_unrepairable_section_entries(
    sections: List[Dict[str, Any]], second_error: ValidationError
) -> List[Dict[str, Any]]:
    """Entfernt nach fehlgeschlagener Erst-Reparatur verbleibende fehlerhafte Einträge."""
    indices_to_remove: Dict[Any, set] = {}
    removed_entries: List[Dict[str, Any]] = []
    for err in second_error.errors():
        loc = err.get("loc") or ()
        if len(loc) < 4 or loc[0] != "sections":
            continue
        si, kind, idx = loc[1], loc[2], loc[3]
        if kind not in ("claims", "hypotheses", "hypotheses_appendix"):
            continue
        if not isinstance(si, int) or not (0 <= si < len(sections)):
            continue
        entries = sections[si].get(kind) or []
        if not isinstance(idx, int) or not (0 <= idx < len(entries)):
            continue
        key = (si, kind)
        if idx in indices_to_remove.get(key, set()):
            continue
        indices_to_remove.setdefault(key, set()).add(idx)
        entry = entries[idx]
        entry_id = (
            str(entry.get("claim_id") or entry.get("hypothesis_id") or "")
            if isinstance(entry, dict)
            else ""
        )
        removed_entries.append(
            {
                "section_index": sections[si].get("section_index", 0),
                "claim_id": entry_id,
                "violation": str(err.get("type") or "unknown"),
                "action": "dropped",
                "detail": str(err.get("msg") or "")[:500],
            }
        )
    for (si, kind), indices in indices_to_remove.items():
        entries = sections[si].get(kind)
        if isinstance(entries, list):
            for i in sorted(indices, reverse=True):
                del entries[i]
    return removed_entries


def _collect_evidence_refs_from_claim(claim: Dict[str, Any], target: set[str]) -> None:
    """Sammelt alle Evidence-IDs und -Referenzen aus einem Claim-Dict."""
    for ev in claim.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("evidence_id"):
            target.add(str(ev["evidence_id"]).strip())
        elif isinstance(ev, str) and ev.strip():
            target.add(ev.strip())
    for ref in claim.get("evidence_refs") or []:
        if ref and str(ref).strip():
            target.add(str(ref).strip())
    for ref in claim.get("supporting_evidence_ids") or []:
        if ref and str(ref).strip():
            target.add(str(ref).strip())


def _extract_verified_claims_and_evidence_ids(
    verified_claims: Optional[List[Dict[str, Any]]],
) -> tuple[set[str], set[str]]:
    """Extrahiert verifizierte Claim-IDs und Evidence-IDs/Refs."""
    claim_ids: set[str] = set()
    evidence_ids: set[str] = set()
    if not verified_claims:
        return claim_ids, evidence_ids

    for c in verified_claims:
        if not isinstance(c, dict):
            continue
        cid = c.get("claim_id")
        if cid is not None and str(cid).strip():
            claim_ids.add(str(cid).strip())
        _collect_evidence_refs_from_claim(c, evidence_ids)

    return claim_ids, evidence_ids


_METADATA_TEXT_KEYS = (
    "text",
    "description",
    "title",
    "content",
    "recommendation",
    "risk",
    "action",
    "step",
    "milestone",
    "item",
    "titel",
    "beschreibung",
    "begruendung",
    "massnahme",
    "risiko",
    "meilenstein",
)


def _find_metadata_entry_text(entry: Dict[str, Any]) -> str:
    """Sucht den ersten nicht-leeren Textwert aus bekannten Metadatenfeldern."""
    for key in _METADATA_TEXT_KEYS:
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _extract_metadata_entry_refs(entry: Dict[str, Any]) -> List[str]:
    """Extrahiert alle Evidence-Referenzstrings aus einem Metadateneintrag."""
    raw = list(entry.get("evidence_refs") or []) + list(entry.get("supporting_evidence_ids") or [])
    return [str(r).strip() for r in raw if r and str(r).strip()]


def _is_metadata_entry_grounded(
    entry: Dict[str, Any],
    *,
    verified_claim_ids: set[str],
    verified_evidence_ids: set[str],
    persisted_content_lower: str,
    has_claims: bool,
    has_content: bool,
) -> bool:
    """Prüft, ob ein einzelner strukturierter Metadateneintrag ausreichend gestützt ist."""
    claim_id = entry.get("claim_id")
    has_claim_id = claim_id is not None and str(claim_id).strip() != ""

    entry_refs = _extract_metadata_entry_refs(entry)
    has_evidence_refs = bool(entry_refs)

    if has_claim_id and str(claim_id).strip() not in verified_claim_ids:
        return False

    if has_evidence_refs and not any(r in verified_evidence_ids for r in entry_refs):
        return False

    if not has_claims or not has_content:
        return False

    if not has_claim_id and not has_evidence_refs:
        entry_text = _find_metadata_entry_text(entry)
        if not entry_text:
            return False
        if entry_text[:60].lower() not in persisted_content_lower:
            return False

    return True


def _filter_structured_metadata_against_verified_section(
    structured_metadata: Optional[Dict[str, Any]],
    *,
    verified_claims: Optional[List[Dict[str, Any]]],
    persisted_content: Optional[str],
) -> Dict[str, Any]:
    """Filtert Metadaten-Listen gegen die verifizierten Claims und den Sektionsinhalt.

    Issue #1885 / Befund 3.1:
    - recommendations, change_recommendations, risks, timeline, next_steps konsistent filtern:
      - Wenn Eintrag claim_id besitzt: muss str(entry["claim_id"]) in verified_claim_ids sein.
      - Wenn Eintrag evidence_refs / supporting_evidence_ids besitzt: mindestens eine Referenz muss
        in den verifizierten Evidence-IDs der Sektion liegen.
      - Wenn verified_claims leer ist oder persisted_content leer ist: keine ungeerdeten Metadaten-Einträge
        dürfen überleben.
      - Wenn weder claim_id noch evidence_refs: Eintrag muss im persisted_content auffindbar sein.
    """
    if not structured_metadata or not isinstance(structured_metadata, dict):
        return {} if structured_metadata is not None else {}

    verified_claims_list = verified_claims or []
    persisted_content_str = persisted_content or ""
    persisted_content_lower = persisted_content_str.lower()
    has_claims = bool(verified_claims_list)
    has_content = bool(persisted_content_str.strip())

    claim_ids, evidence_ids = _extract_verified_claims_and_evidence_ids(verified_claims_list)

    target_keys = (
        "recommendations",
        "change_recommendations",
        "risks",
        "timeline",
        "next_steps",
        "items",
    )
    filtered: Dict[str, Any] = dict(structured_metadata)

    for key in target_keys:
        items = filtered.get(key)
        if not items or not isinstance(items, list):
            continue

        filtered[key] = [
            entry
            for entry in items
            if isinstance(entry, dict)
            and _is_metadata_entry_grounded(
                entry,
                verified_claim_ids=claim_ids,
                verified_evidence_ids=evidence_ids,
                persisted_content_lower=persisted_content_lower,
                has_claims=has_claims,
                has_content=has_content,
            )
        ]

    return filtered


class ReportAgentSectionSavingMixin(ReportAgentHypothesesMixin):
    """Section persistence and validation repair for ReportAgent."""

    if TYPE_CHECKING:
        evidence_map: Any
        _pending_section_metadata: Any

    def _save_evidence_section(
        self, report_id: str, section_index: int, section_title: str, content: str
    ) -> "SectionEvidenceOutcome":
        """Extrahiert Claims, bindet Evidence und persistiert die Evidenzkarte."""
        from . import agent as _agent_mod
        from .output_contract import is_fallback_content  # noqa: PLC0415

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

        def _phase(name: str):
            return phase_tracker.phase(name) if phase_tracker is not None else nullcontext()

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

        generation_failed = is_fallback_content(content)
        if generation_failed:
            _agent_mod.logger.warning(
                "section %d (%r): Fallback-Inhalt — keine Claim-/Evidence-Extraktion.",
                section_index,
                section_title,
            )
            claims: List[Dict[str, Any]] = []
            raw_hypotheses: List[Dict[str, Any]] = []
            gate_decisions: List[Dict[str, Any]] = []
            data_gaps: List[Dict[str, Any]] = [
                {
                    "gap_id": f"gap_{section_index:02d}",
                    "gap_reason": "Abschnitt konnte nicht generiert werden (LLM-Fehler).",
                    "claim_text": section_title,
                }
            ]
        else:
            heartbeat_cb = phase_tracker.heartbeat if phase_tracker is not None else None
            with _phase("claim_extraction_and_evidence_binding"):
                extracted_claims = self._build_claims_for_section(content, heartbeat=heartbeat_cb)
            with _phase("claim_finalization"):
                claims, raw_hypotheses, data_gaps, gate_decisions = self._finalize_section_claims(
                    extracted_claims
                )
            if id_remap:
                claims = _agent_mod._remap_claim_bindings(claims, id_remap)

        prose_entries = (getattr(self, "_pending_prose_hypotheses", {}) or {}).get(
            section_index, []
        )
        prose_hypotheses = [entry[0] for entry in prose_entries]
        raw_hypotheses = list(raw_hypotheses) + prose_hypotheses
        for _position, _hypothesis in enumerate(raw_hypotheses, start=1):
            if isinstance(_hypothesis, dict):
                _hypothesis["hypothesis_id"] = f"hypothesis_{_position:02d}"
        gate_decisions.extend(_agent_mod.prose_gate_decisions(prose_entries, self._truncate))
        if gate_decisions:
            self.evidence_map["gate_decision_log"] = list(
                self.evidence_map.get("gate_decision_log") or []
            ) + [{**decision, "section_index": section_index} for decision in gate_decisions]

        coverage_ledger = _agent_mod.ledger_for(self)
        if coverage_ledger:
            self.evidence_map["evidence_coverage_ledger"] = coverage_ledger.as_payload()

        from .hypothesis_cap import dedup_and_cap_hypotheses  # noqa: PLC0415

        hypotheses_visible, hypotheses_appendix = dedup_and_cap_hypotheses(raw_hypotheses)

        raw_metadata = (getattr(self, "_pending_section_metadata", {}) or {}).get(section_index, {})
        filtered_metadata = _filter_structured_metadata_against_verified_section(
            raw_metadata,
            verified_claims=claims,
            persisted_content=content,
        )
        if hasattr(self, "_pending_section_metadata") and isinstance(
            self._pending_section_metadata, dict
        ):
            self._pending_section_metadata[section_index] = filtered_metadata

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
            "unbound_evidence_refs": (
                getattr(self, "_pending_unbound_evidence_refs", {}) or {}
            ).get(section_index, []),
            "unverified_statements": (
                getattr(self, "_pending_unverified_statements", {}) or {}
            ).get(section_index, []),
        }
        if phase_tracker is not None:
            phase_tracker.start_phase("evidence_map_persistence")

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
        if phase_tracker is not None:
            phase_tracker.end_phase()
        return _agent_mod.SectionEvidenceOutcome.from_persisted_section(
            validated,
            section_index,
            gate_decisions=gate_decisions,
            generation_failed=generation_failed,
        )

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
    "_filter_structured_metadata_against_verified_section",
]
