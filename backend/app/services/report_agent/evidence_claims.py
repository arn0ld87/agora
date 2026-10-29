from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...contracts.report_contract import counts_for_confidence
from .claim_qualification import (  # noqa: F401
    CLAIM_RELATIVE_FIELDS as _CLAIM_RELATIVE_FIELDS,
    _VERIFIED_STRONG_MATCH,
    count_supporting_stakeholder_groups as _count_supporting_stakeholder_groups,
    has_agent_grounded_evidence,
    resolve_claim_evidence_list as _resolved_evidence,
    verified_reachable as _verified_reachable,
)


def _hand_work_downgrade_target(
    claim: Dict[str, Any], *, evidence_index: Optional[Dict[str, Any]]
) -> Optional[str]:
    """Zielstufe, falls das Label nur mit Handarbeit zustande käme (ADR-0022 §4).

    Nur ``verified`` kann das. Die Stufe verlangt einen starken Match *und* zwei
    unabhängige Quellen, und eine Handeingabe im Graphen liefert von beidem: sie
    ist eine eigene Quelle und trägt einen Retrieval-Score. Ein Claim, der sie
    nur deshalb ``verified`` ist, darf sie nicht als Begründung tragen.

    ``high`` kann nicht daran hängen: Anker 4 aus ADR-0002 verlangt zwei
    Rollenfamilien unter ``agent_quote``, und ein ``graph_relation``-Item ist
    strukturell keine Stimme. Diese Regel ist damit *zusätzlich* und lässt
    Anker 4 und 5 unangetastet.

    Ohne Handarbeits-Evidence kommt ``None`` zurück — Bestandsreports bleiben
    byte-gleich. Herabgestuft wird, nicht abgebrochen: der Claim bleibt sichtbar.
    """
    if claim.get("confidence_label") != "verified":
        return None
    resolved = _resolved_evidence(claim.get("evidence") or [], evidence_index)
    counted = [entry for entry in resolved if counts_for_confidence(entry)]
    if len(counted) == len(resolved):
        return None
    return None if _verified_reachable(counted) else "high"


TEXT_CONFIDENCE_DOWNGRADE_EVENT = "text_confidence_downgraded"
"""``audit_trail``-Ereignis: der Wortlaut stammt aus einer hoeheren Stufe."""


def _record_text_confidence_downgrade(
    claim: Dict[str, Any], *, from_label: str, to_label: str
) -> None:
    """Haelt fest, unter welchem Label der ``claim_text`` entstanden ist (#1012)."""
    if claim.get("claim_type") not in (None, "empirical"):
        return
    trail = claim.get("audit_trail")
    if not isinstance(trail, list):
        trail = []
    if any(
        isinstance(entry, dict) and entry.get("event") == TEXT_CONFIDENCE_DOWNGRADE_EVENT
        for entry in trail
    ):
        return
    claim["audit_trail"] = [
        *trail,
        {
            "event": TEXT_CONFIDENCE_DOWNGRADE_EVENT,
            "text_confidence_label": from_label,
            "to": to_label,
            "issue": "1012",
        },
    ]


def text_confidence_label_of(claim: Dict[str, Any]) -> str | None:
    """Die Stufe, unter der der Wortlaut entstand — oder ``None``.

    ``None`` heisst: nicht abgestuft, der Wortlaut passt zum Label. Das ist
    der Normalfall und darf nicht mit "unbekannt" verwechselt werden.
    """
    trail = claim.get("audit_trail")
    if not isinstance(trail, list):
        return None
    for entry in trail:
        if isinstance(entry, dict) and entry.get("event") == TEXT_CONFIDENCE_DOWNGRADE_EVENT:
            label = entry.get("text_confidence_label")
            return str(label) if label else None
    return None


def downgrade_medium_without_agent_grounded(
    claim: Dict[str, Any],
    *,
    evidence_index: Dict[str, Any] | None = None,
    logger: Any = None,
) -> Dict[str, Any] | None:
    """Senkt ``medium`` auf ``low``, wenn ADR-0002 Stufe agent_grounded fehlt."""
    if str(claim.get("confidence_label") or "").lower() != "medium":
        return None
    evidence = claim.get("evidence") or []
    if has_agent_grounded_evidence(evidence, evidence_index=evidence_index or {}):
        return None

    claim["confidence_label"] = "low"
    claim_id = str(claim.get("claim_id") or "<no-id>")
    if logger is not None:
        logger.warning(
            "downgrade_medium_without_agent_grounded: %s medium → low (%s)",
            claim_id,
            "nicht agent_grounded",
        )
    detail = (
        "medium verlangt agent_quote (mit Zitat) UND seed_corpus "
        "(ADR-0002 Stufe agent_grounded) oder stützende agent_action-Belege "
        "von mindestens zwei verschiedenen Stimmen — Komposition nicht "
        "erfüllt, Claim als low geführt."
    )
    return {
        "claim_id": claim_id,
        "violation": "medium_without_agent_grounded_evidence",
        "action": "downgraded_to_low",
        "detail": detail[:500],
    }


def auto_downgrade_unsupported_high_claims(
    claims: List[Dict[str, Any]],
    *,
    evidence_index: Optional[Dict[str, Any]] = None,
    logger: Any = None,
) -> List[Dict[str, Any]]:
    """Senkt ``confidence_label`` von ``high``/``verified`` ab, wenn die
    Cross-Stakeholder-Anforderung aus ADR-0002 (Anker 4) nicht erfüllt ist.
    """
    downgraded: List[Dict[str, Any]] = []
    for raw in claims:
        if not isinstance(raw, dict):
            downgraded.append(raw)
            continue
        item = dict(raw)
        label = item.get("confidence_label")
        if label in ("high", "verified"):
            groups = _count_supporting_stakeholder_groups(
                _resolved_evidence(item.get("evidence") or [], evidence_index)
            )
            if groups < 2:
                evidence = item.get("evidence") or []
                target = (
                    "medium"
                    if has_agent_grounded_evidence(evidence, evidence_index=evidence_index)
                    else "low"
                )
                claim_id = item.get("claim_id", "<no-id>")
                if logger is not None:
                    logger.warning(
                        "auto_downgrade_unsupported_high_claims: %s '%s' → '%s' "
                        "(nur %d stützende Stakeholder-Gruppe(n), 2 erforderlich; "
                        "agent_grounded=%s)",
                        claim_id,
                        label,
                        target,
                        groups,
                        target == "medium",
                    )
                item["confidence_label"] = target
                _record_text_confidence_downgrade(item, from_label=label, to_label=target)
            else:
                hand_work_target = _hand_work_downgrade_target(item, evidence_index=evidence_index)
                if hand_work_target is not None:
                    claim_id = item.get("claim_id", "<no-id>")
                    if logger is not None:
                        logger.warning(
                            "auto_downgrade_unsupported_high_claims: %s '%s' → '%s' "
                            "(Stufe nur mit manueller oder bearbeiteter "
                            "Graph-Evidence gedeckt, ADR-0022)",
                            claim_id,
                            label,
                            hand_work_target,
                        )
                    item["confidence_label"] = hand_work_target
                    _record_text_confidence_downgrade(
                        item, from_label=label, to_label=hand_work_target
                    )
        downgraded.append(item)
    return downgraded


def normalize_claims_for_contract(
    claims: List[Dict[str, Any]],
    *,
    evidence_index: Optional[Dict[str, Any]] = None,
    logger: Any = None,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for claim in claims:
        item = dict(claim)
        item.pop("claim", None)
        item.pop("confidence", None)
        item.pop("evidence_items", None)
        normalized.append(item)
    return auto_downgrade_unsupported_high_claims(
        normalized, evidence_index=evidence_index, logger=logger
    )


_PLACEHOLDER_TEXTS = frozenset({"", "---", "—", "–", "n/a", "n.a.", "tbd", "todo", "?"})


def _is_placeholder(value: Any) -> bool:
    """True wenn ein LLM-Text-Feld ein Platzhalter ist (leer, ``---``, ``n/a`` …)."""
    if not isinstance(value, str):
        return value is None
    return value.strip().lower() in _PLACEHOLDER_TEXTS


def _filter_placeholder_items(
    items: List[Dict[str, Any]],
    text_field: str,
    *,
    logger: Any = None,
    item_kind: str = "item",
) -> List[Dict[str, Any]]:
    """Wirft Items mit leerem/Platzhalter-Text-Feld raus."""
    keep: List[Dict[str, Any]] = []
    dropped = 0
    for entry in items or []:
        if not isinstance(entry, dict):
            keep.append(entry)
            continue
        if _is_placeholder(entry.get(text_field)):
            dropped += 1
            continue
        keep.append(entry)
    if dropped and logger is not None:
        logger.warning(
            "normalize_sections_for_contract: %d %s mit leerem/Platzhalter-%s entfernt",
            dropped,
            item_kind,
            text_field,
        )
    return keep


def normalize_sections_for_contract(
    sections: List[Dict[str, Any]],
    *,
    evidence_index: Optional[Dict[str, Any]] = None,
    logger: Any = None,
) -> List[Dict[str, Any]]:
    normalized_sections: List[Dict[str, Any]] = []
    for section in sections:
        item = {k: v for k, v in dict(section).items() if k != "schema_version"}
        item["section_title"] = (item.get("section_title") or "Recovered section").strip()
        summary = (
            item.get("section_summary") or item.get("section_title") or "Recovered summary"
        ).strip()
        item["section_summary"] = summary or "Recovered summary"
        item["claims"] = normalize_claims_for_contract(
            item.get("claims") or [], evidence_index=evidence_index, logger=logger
        )
        item["hypotheses"] = _filter_placeholder_items(
            list(item.get("hypotheses") or []),
            "hypothesis_text",
            logger=logger,
            item_kind="hypotheses",
        )
        item["hypotheses_appendix"] = _filter_placeholder_items(
            list(item.get("hypotheses_appendix") or []),
            "hypothesis_text",
            logger=logger,
            item_kind="hypotheses_appendix",
        )
        item["data_gaps"] = _filter_placeholder_items(
            list(item.get("data_gaps") or []),
            "claim_text",
            logger=logger,
            item_kind="data_gaps",
        )
        normalized_sections.append(item)
    return normalized_sections


__all__ = [
    "TEXT_CONFIDENCE_DOWNGRADE_EVENT",
    "_CLAIM_RELATIVE_FIELDS",
    "_PLACEHOLDER_TEXTS",
    "_VERIFIED_STRONG_MATCH",
    "_count_supporting_stakeholder_groups",
    "_filter_placeholder_items",
    "_hand_work_downgrade_target",
    "_is_placeholder",
    "_record_text_confidence_downgrade",
    "_resolved_evidence",
    "_verified_reachable",
    "auto_downgrade_unsupported_high_claims",
    "downgrade_medium_without_agent_grounded",
    "has_agent_grounded_evidence",
    "normalize_claims_for_contract",
    "normalize_sections_for_contract",
    "text_confidence_label_of",
]
