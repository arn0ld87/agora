"""Slice 3 (Issue #495): Hypothesen-Cap + Appendix pro Section.

Dedup via Token-Set-Ratio (rapidfuzz) ≥ 0.88, Sort by confidence_score desc,
Split: [:5] visible, [5:] appendix.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agora.hypothesis_cap")

_DEDUP_THRESHOLD = 88  # rapidfuzz score 0–100
_VISIBLE_CAP = 5
_RATIONALE_CONCAT_MAX = 200
# Issue #1073: muss exakt dem Contract-Limit entsprechen. Quelle der Wahrheit:
# ReportSectionModel.hypotheses_appendix in
# backend/app/contracts/report_contract.py (max_length=50).
_APPENDIX_CAP = 50


def _token_set_ratio(a: str, b: str) -> float:
    """Returns 0–100 token-set similarity via rapidfuzz."""
    from rapidfuzz.fuzz import token_set_ratio  # noqa: PLC0415
    return token_set_ratio(a, b)


def dedup_and_cap_hypotheses(
    hypotheses: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Dedup, sort, split per-section hypotheses.

    Args:
        hypotheses: list of raw hypothesis dicts (from _finalize_section_claims).

    Returns:
        (visible, appendix) where visible has ≤5 items.
    """
    if not hypotheses:
        return [], []

    # --- Dedup -----------------------------------------------------------------
    deduped: list[dict[str, Any]] = []
    for candidate in hypotheses:
        candidate_text = str(candidate.get("hypothesis_text") or "").strip()
        merged = False
        for existing in deduped:
            existing_text = str(existing.get("hypothesis_text") or "").strip()
            if _token_set_ratio(candidate_text, existing_text) >= _DEDUP_THRESHOLD:
                # Merge: keep lowest ID (already in existing), concat rationale
                existing_rationale = str(existing.get("rationale") or "")
                candidate_rationale = str(candidate.get("rationale") or "")
                if candidate_rationale and candidate_rationale != existing_rationale:
                    combined = f"{existing_rationale}; {candidate_rationale}"
                    existing["rationale"] = combined[:_RATIONALE_CONCAT_MAX]
                # Merge suggested_evidence (deduplicated union)
                existing_ev = list(existing.get("suggested_evidence") or [])
                for ev in candidate.get("suggested_evidence") or []:
                    if ev not in existing_ev:
                        existing_ev.append(ev)
                existing["suggested_evidence"] = existing_ev[:5]
                logger.debug(
                    "hypothesis_cap: merged '%s...' into '%s...'",
                    candidate_text[:40],
                    existing_text[:40],
                )
                merged = True
                break
        if not merged:
            deduped.append(dict(candidate))

    # --- Sort ------------------------------------------------------------------
    def _sort_key(h: dict[str, Any]) -> tuple[float, int]:
        score = float(h.get("confidence_score") or 0.0)
        ev_len = len(h.get("suggested_evidence") or [])
        return (-score, -ev_len)

    deduped.sort(key=_sort_key)

    # --- Split -----------------------------------------------------------------
    visible = deduped[:_VISIBLE_CAP]
    appendix = deduped[_VISIBLE_CAP:]

    # --- Hard cap (Issue #1073) -------------------------------------------------
    # deduped ist bereits nach Confidence absteigend sortiert (_sort_key), daher
    # verwirft der Slice hier ausschließlich die schwächsten Einträge am Ende.
    if len(appendix) > _APPENDIX_CAP:
        dropped = appendix[_APPENDIX_CAP:]
        appendix = appendix[:_APPENDIX_CAP]
        logger.warning(
            "hypothesis_cap: appendix exceeded contract limit of %d, "
            "dropped %d weakest hypotheses (lowest confidence_score)",
            _APPENDIX_CAP,
            len(dropped),
        )

    return visible, appendix
