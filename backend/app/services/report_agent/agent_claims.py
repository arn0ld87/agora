from __future__ import annotations

import re
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional


from ..evidence_entailment import SCENARIO_ROLE_REASON_PREFIX

if TYPE_CHECKING:
    pass

# S5: diese Item-Typen sind Modell-Output, keine Evidence. Sie dürfen
# nicht im `evidence`-Array eines Claims stehen, sondern im separaten
# `audit_trail`-Feld.
FORBIDDEN_EVIDENCE_TYPES = frozenset(
    {
        "model_generated_inference",
        "section_synthesis",
    }
)

#: Issue #1319: `suggested_fix` in ``data_gaps`` war identisch mit ``claim_text``
#: (Kopie des ersten Audit-Snippets) — kein echter naechster Schritt. Der Text
#: wird jetzt aus dem `gap_reason` abgeleitet.
_GAP_SUGGESTED_FIX: Dict[str, str] = {
    "no_evidence_bound": (
        "Keine Quelle gebunden — Beleg gezielt recherchieren oder die Aussage streichen."
    ),
    "related_evidence_only": (
        "Evidence bindet thematisch, aber keine stützt die Aussage — "
        "Quelle mit direktem Aussagebezug suchen."
    ),
    "source_information_absent": (
        "Zu dieser Aussage liegt in keiner verfügbaren Quelle etwas vor — "
        "Quelle beschaffen oder die Aussage streichen."
    ),
}
_GAP_SUGGESTED_FIX_DEFAULT = (
    "Beleglage prüfen und passende Quelle nachreichen oder die Aussage streichen."
)

#: Claim-Typen ohne Wahrheitswert über die Welt (Issue #1400). Ohne Beleg
#: werden sie Hypothese, aber keine Datenlücke. ``analytical`` fehlt bewusst:
#: eine Analyse stützt sich auf Tatsachen-Prämissen.
_NON_FACTUAL_CLAIM_TYPES = frozenset({"recommendation", "structural"})


def _is_non_factual_claim(claim: Dict[str, Any]) -> bool:
    return claim.get("claim_type") in _NON_FACTUAL_CLAIM_TYPES


def _counts_for_claim(evidence_item: Dict[str, Any], evidence_index: Mapping[str, Any]) -> bool:
    """Zaehlt dieser Beleg fuer eine Confidence-Stufe? (ADR-0022 §4, #1808)"""
    from . import agent as _agent_mod

    if not _agent_mod.counts_for_confidence(evidence_item):
        return False
    record = evidence_index.get(str(evidence_item.get("evidence_id") or ""))
    return _agent_mod.counts_for_confidence(record) if isinstance(record, Mapping) else True


def _count_scenario_bindings(claim: Dict[str, Any]) -> int:
    """Bindungen, die nur wegen ihrer Dokument-Rolle nicht stützen (#1240)."""
    return sum(
        1
        for item in claim.get("evidence") or []
        if isinstance(item, dict)
        and str(item.get("entailment_reason") or "").startswith(SCENARIO_ROLE_REASON_PREFIX)
    )


def _typed_confidence(
    chunk: str,
    score: float,
    label: str,
    audit_trail: List[Dict[str, Any]],
) -> tuple[str, float, str]:
    """Typisiert den Claim und wendet den Typ-Boden an (Issue #1400)."""
    from . import agent as _agent_mod

    claim_type = _agent_mod.classify_claim_type(chunk).value
    floored = _agent_mod.apply_claim_type_floor(claim_type, score, label)
    if floored != (score, label):
        audit_trail.append(
            {
                "type": "claim_type_floor_applied",
                "claim_type": claim_type,
                "from_label": label,
                "value": floored[0],
                "source": "confidence_calculator.apply_claim_type_floor",
            }
        )
    return claim_type, floored[0], floored[1]


class ReportAgentClaimsMixin:
    """Claim-Extraktion, Hypothesen-Routing, Section-Finalisierung und Persistenz für ReportAgent."""

    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _build_claims_for_section(
        self,
        content: str,
        heartbeat: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, Any]]:
        from . import agent as _agent_mod

        raw_chunks = [
            part.strip() for part in re.split(r"\n\s*\n", (content or "").strip()) if part.strip()
        ]
        chunks = [c for c in raw_chunks if self._is_claim_candidate(c)]
        atomic_chunks: List[str] = []
        for chunk in chunks:
            atoms = [a for a in self._atomize_claim_chunk(chunk) if self._is_atomic_claim(a)]
            if atoms:
                atomic_chunks.extend(atoms)
                continue
            if not self._is_discourse_sentence(chunk):
                atomic_chunks.append(chunk)
        chunks = _agent_mod.split_claim_chunks(atomic_chunks)
        claims = []
        evidence_index = (self.evidence_map or {}).get("evidence_index") or {}
        global_items = [
            deepcopy(evidence_index[evidence_id])
            for evidence_id in (self.evidence_map or {}).get("global_evidence_refs", [])
            if evidence_id in evidence_index
        ]
        direct_items = [
            deepcopy(item)
            for item in self._active_section_evidence
            if item.get("type") not in _agent_mod.FORBIDDEN_EVIDENCE_TYPES
        ]
        embedder = self._try_get_embedder()
        pool = self._candidate_pool(direct_items, global_items, evidence_index, embedder)
        for index, chunk in enumerate(chunks, 1):
            if heartbeat is not None:
                heartbeat(f"Claim {index}/{len(chunks)}")
            audit_trail = [
                _agent_mod.EvidenceItem(
                    type="model_generated_inference",
                    source="section_synthesis",
                    tool_name="section_synthesis",
                    snippet=self._truncate(chunk),
                    raw={"content": chunk},
                ).to_dict()
            ]
            for unresolved in getattr(self, "_active_section_unresolved_evidence", [])[:10]:
                audit_trail.append(
                    {
                        "type": "unresolved_evidence",
                        "source": str(unresolved.get("source") or "report_tool"),
                        "snippet": self._truncate(str(unresolved.get("snippet") or "")),
                        "raw": {"reason": "missing_producer_key"},
                    }
                )

            bound: List[Dict[str, Any]] = []
            embedder_ok = False
            if embedder is not None and pool is not None:
                try:
                    bound = _agent_mod.bind_evidence_to_claim(
                        chunk,
                        pool.select(chunk),
                        pool.embed,
                        threshold=0.55,
                        top_k=5,
                        judge=self._try_get_entailment_judge(),
                        reserved_slots=_agent_mod.RESERVED_CANDIDATE_SLOTS,
                    )
                    embedder_ok = True
                except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    _agent_mod.reraise_if_budget_exceeded(exc)
                    _agent_mod.logger.warning(
                        f"EvidenceBinder failed, falling back to generic pool: {exc!r}"
                    )
                    self._embed_cache = None
                    embedder = None
                    pool = None
            if embedder_ok:
                evidence_items = bound
                direct_count = len(bound)
            else:
                evidence_items = [
                    {"evidence_id": item["evidence_id"]}
                    for item in direct_items
                    if item.get("evidence_id")
                ]
                direct_count = len(direct_items)

            current_index = (self.evidence_map or {}).get("evidence_index") or {}
            from .claim_qualification import resolve_claim_evidence_item

            resolved_evidence = [
                resolve_claim_evidence_item(binding, current_index)
                for binding in evidence_items
                if binding.get("evidence_id") in current_index
            ]

            penalty = _agent_mod.detect_contradiction_penalty(
                list(filter(_agent_mod.counts_for_confidence, resolved_evidence))
            )
            confidence_score, confidence_label = _agent_mod.compute_confidence(
                resolved_evidence,
                contradiction_penalty=penalty,
            )
            if penalty > 0.0:
                audit_trail.append(
                    {
                        "type": "contradiction_penalty_applied",
                        "value": penalty,
                        "source": "evidence_binder.detect_contradiction_penalty",
                    }
                )
            if not resolved_evidence:
                confidence_score, confidence_label = 0.15, "speculative"
                audit_trail.append(
                    {
                        "type": "model_generated_inference",
                        "source": "validator",
                        "tool_name": "evidence_validator",
                        "snippet": "no_direct_evidence_bound",
                        "raw": {"reason": "no_direct_evidence_bound"},
                    }
                )
            claim_type, confidence_score, confidence_label = _agent_mod._typed_confidence(
                chunk, confidence_score, confidence_label, audit_trail
            )
            support_count = direct_count + len(global_items)  # noqa: F841
            claim_dict = _agent_mod.ReportClaim(
                claim_id=f"claim_{index:02d}",
                claim_text=chunk,
                evidence=evidence_items,
                confidence_score=confidence_score,
                confidence_label=confidence_label,
                notes="Section-chunk level evidence mapping (schema_version 3).",
                claim_type=claim_type,
            ).to_dict()
            claim_dict["audit_trail"] = audit_trail
            claims.append(claim_dict)
        if not claims:
            claims.append(
                _agent_mod.ReportClaim(
                    claim_id="claim_01",
                    claim_text="No claim candidate extracted from this section.",
                    evidence=[],
                    confidence_score=0.0,
                    confidence_label="speculative",
                    notes="No section content captured.",
                ).to_dict()
            )
        return claims


__all__ = [
    "FORBIDDEN_EVIDENCE_TYPES",
    "ReportAgentClaimsMixin",
    "_GAP_SUGGESTED_FIX",
    "_GAP_SUGGESTED_FIX_DEFAULT",
    "_NON_FACTUAL_CLAIM_TYPES",
    "_count_scenario_bindings",
    "_counts_for_claim",
    "_is_non_factual_claim",
    "_typed_confidence",
]

