"""Hypothesis and claim finalization mixin for ReportAgent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportAgentHypothesesMixin:
    """Methods for hypothesis routing, unverified statement recording, and claim finalization."""

    if TYPE_CHECKING:
        _pending_prose_hypotheses: Optional[Dict[int, List[Any]]]
        _pending_unverified_statements: Optional[Dict[int, List[Dict[str, Any]]]]
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _record_prose_hypotheses(
        self,
        section_index: int,
        flagged: List[Any],
    ) -> None:
        """Merkt beanstandete Fließtext-Aussagen als Hypothesen vor."""
        if not flagged:
            return
        if not hasattr(self, "_pending_prose_hypotheses") or self._pending_prose_hypotheses is None:
            self._pending_prose_hypotheses = {}
        bucket = self._pending_prose_hypotheses.setdefault(section_index, [])
        for offset, statement in enumerate(flagged, start=len(bucket) + 1):
            bucket.append((statement.as_hypothesis(offset), statement))

    def _record_unverified_statements(
        self,
        section_index: int,
        unverified: List[Any],
    ) -> None:
        """Merkt die im Fließtext belassenen, unbelegten Aussagen vor."""
        if not unverified:
            return
        if (
            not hasattr(self, "_pending_unverified_statements")
            or self._pending_unverified_statements is None
        ):
            self._pending_unverified_statements = {}
        bucket = self._pending_unverified_statements.setdefault(section_index, [])
        for statement in unverified:
            bucket.append(
                {
                    "statement_text": str(statement.text)[:1000],
                    "verdict": str(getattr(statement.verdict, "value", statement.verdict)),
                    "reason": str(statement.reason)[:200],
                }
            )

    def _route_claim_to_hypothesis(
        self,
        claim: Dict[str, Any],
        *,
        related_only: int,
        has_evidence: bool,
        label: str,
        hypotheses: List[Dict[str, Any]],
        data_gaps: List[Dict[str, Any]],
        gate_decisions: List[Dict[str, Any]],
    ) -> None:
        """Ohne eine einzige stützende Quelle ist die Aussage eine Hypothese."""
        from .agent_claims import _count_scenario_bindings, _is_non_factual_claim

        index = len(hypotheses) + 1
        claim_text = self._truncate(
            str(claim.get("claim_text") or claim.get("claim") or "").strip()
            or "No evidence-bound claim text available.",
            1000,
        )
        claim_type = claim.get("claim_type")
        non_factual = _is_non_factual_claim(claim)
        if non_factual:
            rationale = (
                f"Keine Tatsachenbehauptung (claim_type={claim_type}); ohne "
                "stützende Quelle nicht als validierter Claim geführt."
            )
        elif related_only:
            rationale = (
                f"{related_only} Quelle(n) sind thematisch verwandt, "
                "belegen die Aussage aber nicht (kein SUPPORTED-Urteil) "
                "— deshalb als Hypothese geführt."
            )
            scenario_count = _count_scenario_bindings(claim)
            if scenario_count:
                rationale += (
                    f" Davon {scenario_count} aus Szenario-/Erwartungstext des "
                    "Eingabedokuments: das ist Vorgabe des Testfalls, kein "
                    "Simulationsbefund."
                )
        else:
            rationale = (
                "Keine direkte Evidence gebunden; deshalb nicht als validierter Claim persistiert."
            )
        hypothesis_id = f"hypothesis_{index:02d}"
        hypothesis: Dict[str, Any] = {
            "hypothesis_id": hypothesis_id,
            "hypothesis_text": claim_text,
            "rationale": rationale,
            "suggested_evidence": self._suggested_evidence_from_claim_audit(claim),
        }
        if claim_type:
            hypothesis["claim_type"] = claim_type
        hypotheses.append(hypothesis)
        if non_factual:
            gate_decisions.append(
                {
                    "claim_id": str(claim.get("claim_id") or "<no-id>"),
                    "violation": "no_supporting_evidence",
                    "action": "moved_to_hypotheses",
                    "detail": f"[non_factual:{claim_type}] {rationale}"[:500],
                }
            )
            return
        gap_kind = self._append_data_gap_if_absent(
            claim_text,
            related_evidence_count=related_only,
            gap_id=f"gap_{index:02d}",
            hypothesis_id=hypothesis_id,
            data_gaps=data_gaps,
        )
        gate_decisions.append(
            {
                "claim_id": str(claim.get("claim_id") or "<no-id>"),
                "violation": (
                    "confidence_label_without_evidence"
                    if not has_evidence and label in ("medium", "high", "verified")
                    else "no_supporting_evidence"
                ),
                "action": "moved_to_hypotheses",
                "detail": f"[{gap_kind.value}] {rationale}"[:500],
            }
        )

    def _append_data_gap_if_absent(
        self,
        claim_text: str,
        *,
        related_evidence_count: int,
        gap_id: str,
        hypothesis_id: Optional[str],
        data_gaps: List[Dict[str, Any]],
        suggested_fix: Optional[str] = None,
    ) -> Any:
        """Trägt eine Datenlücke ein — aber nur, wenn wirklich eine vorliegt."""
        from . import agent as _agent_mod
        from .agent_claims import _GAP_SUGGESTED_FIX, _GAP_SUGGESTED_FIX_DEFAULT

        gap_kind = _agent_mod.classify_claim_gap(
            claim_text,
            related_evidence_count=related_evidence_count,
            evidence_pool=self._evidence_pool_for_gap_check(),
        )
        if gap_kind is not _agent_mod.ClaimGapKind.SOURCE_INFORMATION_ABSENT:
            return gap_kind

        gap_reason = "source_information_absent"
        entry: Dict[str, Any] = {
            "gap_id": gap_id,
            "claim_text": claim_text,
            "gap_reason": gap_reason,
            "suggested_fix": suggested_fix
            or _GAP_SUGGESTED_FIX.get(gap_reason, _GAP_SUGGESTED_FIX_DEFAULT),
        }
        if hypothesis_id is not None:
            entry["hypothesis_id"] = hypothesis_id
        data_gaps.append(entry)
        return gap_kind

    @staticmethod
    def _suggested_evidence_from_claim_audit(claim: Dict[str, Any]) -> List[str]:
        suggestions: List[str] = []
        for entry in claim.get("audit_trail") or []:
            if not isinstance(entry, dict):
                continue
            reason = entry.get("snippet") or entry.get("source") or entry.get("type")
            if reason == "no_direct_evidence_bound":
                suggestions.append("Direkte Evidence per Graph- oder Agent-Tool nachreichen.")
            elif reason:
                suggestions.append(str(reason)[:200])
        return suggestions[:5] or ["Direkte Evidence per Graph- oder Agent-Tool nachreichen."]

    def _finalize_section_claims(
        self,
        claims: List[Dict[str, Any]],
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        from . import agent as _agent_mod
        from .agent_claims import _counts_for_claim

        finalized_claims: List[Dict[str, Any]] = []
        hypotheses: List[Dict[str, Any]] = []
        data_gaps: List[Dict[str, Any]] = []
        gate_decisions: List[Dict[str, Any]] = []

        evidence_index = self._evidence_index_map()
        for claim in _agent_mod.normalize_claims_for_contract(
            claims, evidence_index=evidence_index
        ):
            evidence = claim.get("evidence") or []
            label = str(claim.get("confidence_label") or "").lower()

            evidence_ids = {
                str(item["evidence_id"])
                for item in evidence
                if isinstance(item, dict) and item.get("evidence_id")
            }
            supporting_ids = {
                str(item["evidence_id"])
                for item in evidence
                if isinstance(item, dict)
                and item.get("evidence_id")
                and item.get("supports_claim") is True
                and _counts_for_claim(item, evidence_index)
            }
            unkeyed_related = sum(
                1 for item in evidence if not isinstance(item, dict) or not item.get("evidence_id")
            )
            related_only = len(evidence_ids - supporting_ids) + unkeyed_related
            if not supporting_ids:
                self._route_claim_to_hypothesis(
                    claim,
                    related_only=related_only,
                    has_evidence=bool(evidence),
                    label=label,
                    hypotheses=hypotheses,
                    data_gaps=data_gaps,
                    gate_decisions=gate_decisions,
                )
                continue
            if not evidence and label in ("medium", "high", "verified"):
                index = len(data_gaps) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "No evidence-bound claim text available."
                )
                claim_text = self._truncate(claim_text, 1000)
                suggestions = self._suggested_evidence_from_claim_audit(claim)
                self._append_data_gap_if_absent(
                    claim_text,
                    related_evidence_count=0,
                    gap_id=f"gap_{index:02d}",
                    hypothesis_id=None,
                    data_gaps=data_gaps,
                    suggested_fix=suggestions[0] if suggestions else None,
                )
                continue

            evidence_index = self._evidence_index_map()
            decision = _agent_mod.downgrade_medium_without_agent_grounded(
                claim, evidence_index=evidence_index, logger=_agent_mod.logger
            )
            if decision is not None:
                gate_decisions.append(decision)

            finalized_claims.append(claim)

        return finalized_claims, hypotheses, data_gaps, gate_decisions


__all__ = ["ReportAgentHypothesesMixin"]
