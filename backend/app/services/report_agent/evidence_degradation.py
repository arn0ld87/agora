from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from pydantic import ValidationError

from .evidence_claims import _record_text_confidence_downgrade

_MIN_HYPOTHESIS_TEXT_LEN = 8
_MAX_HYPOTHESIS_FIELD_LEN = 1000
_FALLBACK_RATIONALE = (
    "Automatisch aus einem Claim ohne ausreichende Evidence in eine "
    "Hypothese überführt, da der ursprüngliche Validierungsfehler keine "
    "verwertbare Begründung lieferte."
)


def _collect_existing_hypothesis_ids(section: Dict[str, Any]) -> set:
    ids: set = set()
    for list_name in ("hypotheses", "hypotheses_appendix"):
        for entry in section.get(list_name) or []:
            if isinstance(entry, dict):
                hid = entry.get("hypothesis_id")
                if hid:
                    ids.add(hid)
    return ids


def _next_hypothesis_id(existing: set) -> str:
    i = 1
    while True:
        candidate = f"hypothesis_{i:02d}"
        if candidate not in existing:
            return candidate
        i += 1


def degrade_sections_for_violations(
    sections: List[Dict[str, Any]],
    error: "ValidationError",
    *,
    logger: Any = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Repariert Sections nach einem fehlgeschlagenen Contract-Validate."""
    repaired: List[Dict[str, Any]] = copy.deepcopy(sections)
    violations: List[Dict[str, Any]] = []

    claims_to_remove: Dict[int, set] = {}
    hyps_to_remove: Dict[Tuple[int, str], set] = {}
    processed_claims: set = set()
    processed_hyps: set = set()

    def _log_violation(entry: Dict[str, Any]) -> None:
        violations.append(entry)
        if logger is not None:
            logger.warning(
                "degrade_sections_for_violations: section=%s claim_id=%s "
                "violation=%s action=%s detail=%s",
                entry["section_index"],
                entry["claim_id"],
                entry["violation"],
                entry["action"],
                entry["detail"],
            )

    for err in error.errors():
        loc = err.get("loc") or ()
        violation_type = str(err.get("type") or "unknown")
        detail = str(err.get("msg") or "")[:500]
        if len(loc) < 4 or loc[0] != "sections":
            section_claim_match = re.search(r"\bSection ([^ ]+) Claim ([^:]+):", detail)
            claim_match = re.search(r"\bClaim ([^:]+):", detail)
            target_section = section_claim_match.group(1) if section_claim_match else None
            if section_claim_match:
                target_id = section_claim_match.group(2)
            elif claim_match:
                target_id = claim_match.group(1)
            else:
                target_id = None
            if target_id:
                targeted = False
                for fallback_si, fallback_section in enumerate(repaired):
                    if (
                        target_section is not None
                        and str(fallback_section.get("section_index")) != target_section
                    ):
                        continue
                    for fallback_ci, claim in enumerate(fallback_section.get("claims") or []):
                        if not isinstance(claim, dict) or claim.get("claim_id") != target_id:
                            continue
                        if (fallback_si, fallback_ci) in processed_claims:
                            break
                        processed_claims.add((fallback_si, fallback_ci))
                        if claim.get("evidence"):
                            _record_text_confidence_downgrade(
                                claim,
                                from_label=str(claim.get("confidence_label") or ""),
                                to_label="low",
                            )
                            claim["confidence_label"] = "low"
                            _log_violation(
                                {
                                    "section_index": fallback_section.get("section_index", 0),
                                    "claim_id": target_id,
                                    "violation": violation_type,
                                    "action": "downgraded_to_low",
                                    "detail": detail,
                                }
                            )
                        targeted = True
                        break
                    if targeted:
                        break
            continue

        si = loc[1]
        kind = loc[2]
        if not isinstance(si, int) or not (0 <= si < len(repaired)):
            continue
        section = repaired[si]
        section_index_value = section.get("section_index", 0)
        if kind == "claims":
            ci = loc[3]
            claims_list = section.get("claims") or []
            if not isinstance(ci, int) or not (0 <= ci < len(claims_list)):
                continue
            if (si, ci) in processed_claims:
                continue
            processed_claims.add((si, ci))
            claim = claims_list[ci]
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or "")
            evidence = claim.get("evidence") or []

            if evidence:
                _record_text_confidence_downgrade(
                    claim,
                    from_label=str(claim.get("confidence_label") or ""),
                    to_label="low",
                )
                claim["confidence_label"] = "low"
                _log_violation(
                    {
                        "section_index": section_index_value,
                        "claim_id": claim_id,
                        "violation": violation_type,
                        "action": "downgraded_to_low",
                        "detail": detail,
                    }
                )
                continue

            claims_to_remove.setdefault(si, set()).add(ci)
            claim_text = claim.get("claim_text")
            stripped_text = claim_text.strip() if isinstance(claim_text, str) else ""

            if len(stripped_text) >= _MIN_HYPOTHESIS_TEXT_LEN:
                existing_ids = _collect_existing_hypothesis_ids(section)
                new_id = _next_hypothesis_id(existing_ids)
                hypothesis_text = stripped_text[:_MAX_HYPOTHESIS_FIELD_LEN]
                rationale = (
                    detail.strip()
                    if len(detail.strip()) >= _MIN_HYPOTHESIS_TEXT_LEN
                    else _FALLBACK_RATIONALE
                )
                rationale = rationale[:_MAX_HYPOTHESIS_FIELD_LEN]
                new_hypothesis = {
                    "hypothesis_id": new_id,
                    "hypothesis_text": hypothesis_text,
                    "rationale": rationale,
                }
                section.setdefault("hypotheses", []).append(new_hypothesis)
                _log_violation(
                    {
                        "section_index": section_index_value,
                        "claim_id": claim_id,
                        "violation": violation_type,
                        "action": "moved_to_hypotheses",
                        "detail": detail,
                    }
                )
            else:
                _log_violation(
                    {
                        "section_index": section_index_value,
                        "claim_id": claim_id,
                        "violation": violation_type,
                        "action": "dropped",
                        "detail": detail,
                    }
                )

        elif kind in ("hypotheses", "hypotheses_appendix"):
            hi = loc[3]
            hyp_list = section.get(kind) or []
            if not isinstance(hi, int) or not (0 <= hi < len(hyp_list)):
                continue
            key = (si, kind)
            if (key, hi) in processed_hyps:
                continue
            processed_hyps.add((key, hi))
            hyp_entry = hyp_list[hi]
            hyp_id = ""
            if isinstance(hyp_entry, dict):
                hyp_id = str(hyp_entry.get("hypothesis_id") or "")
            hyps_to_remove.setdefault(key, set()).add(hi)
            _log_violation(
                {
                    "section_index": section_index_value,
                    "claim_id": hyp_id,
                    "violation": violation_type,
                    "action": "dropped",
                    "detail": detail,
                }
            )

    for si, indices in claims_to_remove.items():
        claims_list = repaired[si].get("claims")
        if not isinstance(claims_list, list):
            continue
        for idx in sorted(indices, reverse=True):
            del claims_list[idx]

    for (si, list_name), indices in hyps_to_remove.items():
        hyp_list = repaired[si].get(list_name)
        if not isinstance(hyp_list, list):
            continue
        for idx in sorted(indices, reverse=True):
            del hyp_list[idx]

    return repaired, violations


__all__ = [
    "_FALLBACK_RATIONALE",
    "_MAX_HYPOTHESIS_FIELD_LEN",
    "_MIN_HYPOTHESIS_TEXT_LEN",
    "_collect_existing_hypothesis_ids",
    "_next_hypothesis_id",
    "degrade_sections_for_violations",
]
