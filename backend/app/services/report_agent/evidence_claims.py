from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ...contracts.report_contract import (
    counts_for_confidence,
    has_two_action_voices,
)
from ..confidence_calculator import _count_independent_sources

_CLAIM_RELATIVE_FIELDS = frozenset(
    {
        "match_score",
        "retrieval_score",
        "entailment",
        "entailment_reason",
        "supports_claim",
        "contradicts_claim",
    }
)


def _count_supporting_stakeholder_groups(evidence: List[Dict[str, Any]]) -> int:
    """Zähle die unterschiedlichen Stakeholder-Gruppen unter ``agent_quote``-Evidence,
    die den Claim stützen. Spiegelt die Logik aus
    ``ReportClaimModel.cross_stakeholder_for_high`` (ADR-0002, Anker 4).
    """
    groups: set = set()
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        if not counts_for_confidence(entry):
            continue
        if entry.get("source_kind") != "agent_quote":
            continue
        if not entry.get("supports_claim"):
            continue
        # Issue #1248: Gezaehlt wird das kontrollierte Rollenfamilien-Label,
        # nicht der frei formulierte Berufstitel — sonst zaehlen Wortwahl- und
        # Genusvarianten derselben Rolle als verschiedene Gruppen. Die
        # Praefixe halten die beiden Namensraeume auseinander; ohne sie waere
        # eine Familie "Lecturer" nicht von einem gleichnamigen Jobtitel zu
        # unterscheiden. Spiegelt ``report_contract._role_family_key``.
        family = entry.get("persona_role_family")
        family_key = " ".join(str(family or "").split()).casefold()
        # Issue #1248 (CodeRabbit PR #1260): Auffangtypen bezeichnen keine
        # Rollenfamilie. Spiegelt ``report_contract._GENERIC_ENTITY_TYPES``.
        if family_key and family_key not in {
            "person",
            "organization",
            "entity",
            "node",
            "unknown",
            "other",
        }:
            groups.add(f"family:{family_key}")
            continue
        group = entry.get("persona_stakeholder_group")
        if group:
            groups.add(f"title:{' '.join(str(group).split()).casefold()}")
    return len(groups)


def has_agent_grounded_evidence(
    evidence: List[Dict[str, Any]],
    *,
    evidence_index: Optional[Dict[str, Any]] = None,
) -> bool:
    """True, wenn die Evidence mind. 1 ``agent_quote`` (mit nicht-leerem
    ``quote``-Feld) UND mind. 1 ``seed_corpus`` enthält (ADR-0002 Stufe
    agent_grounded → rechtfertigt ``medium``) ODER stützende ``agent_action``-
    Belege von mind. zwei verschiedenen Stimmen (``voice_key``; ADR-0002-
    Nachtrag 2026-10-10, #1778, geteilter Helper ``has_two_action_voices``).
    Spiegelt
    ``ReportClaimModel.agent_grounded_for_medium`` (Issue #906 Defekt 1).
    Jeder Beleg muss den Claim ausdrücklich stützen (``supports_claim is
    True``), wie im medium-Validator ``_require_quote_and_seed`` seit #1894.
    Ohne diese Bedingung bliebe ein Claim hier ``medium``, den der Vertrag
    danach ablehnt — die API lieferte dann die ganze Map als
    ``evidence_omitted`` statt eines sichtbar herabgestuften Claims.
    Das Quote-Feld ist Pflicht (ADR-0002 Z. 54; Codex PR-Review #961 P2): ein
    zusammengefasstes Interview ohne Original-Zitat ist nicht agent_grounded.

    Mit ``evidence_index`` wird jede Referenz zuerst über ihre ``evidence_id``
    auf den kanonischen Record aufgelöst und nur ersatzweise am Inline-Eintrag
    gemessen. ``EvidenceMapModel.validate_evidence_cross_references`` urteilt
    ausschließlich über die Records; ohne diese Auflösung könnte ein Claim hier
    als agent_grounded gelten und dort trotzdem durchfallen — genau der
    Report-Abbruch, den der Aufrufer verhindern will.

    ADR-0022 §4: Evidence aus Handarbeit im Graphen zählt auch hier nicht. Eine
    von Hand angelegte oder bearbeitete Beziehung ist weder eine Stimme noch ein
    Korpusbeleg — sie kann den agent_grounded-Nachweis nicht liefern, auch wenn
    ihr Record sonst auf ``seed_corpus`` oder ``agent_quote`` fiele.
    """
    has_agent_quote = False
    has_seed_corpus = False
    action_voices: List[Tuple[Any, Any]] = []
    index = evidence_index or {}
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        record = index.get(str(entry.get("evidence_id") or ""))
        source = record if isinstance(record, dict) else entry
        if not counts_for_confidence(entry) or not counts_for_confidence(source):
            continue
        if entry.get("supports_claim") is False or source.get("supports_claim") is False:
            continue
        # ``supports_claim`` ist ein Binding-Feld, daher hat der Eintrag
        # Vorrang, ersatzweise der Record.
        if entry.get("supports_claim", source.get("supports_claim")) is not True:
            continue
        sk = source.get("source_kind")
        if sk == "agent_quote" and source.get("quote"):
            has_agent_quote = True
        elif sk == "seed_corpus":
            has_seed_corpus = True
        # ADR-0002-Nachtrag 2026-10-10 (#1778): stützende Aktionsbelege
        # zählen als Stimmen.
        action_voices.append((sk, source.get("voice_key")))
    return (has_agent_quote and has_seed_corpus) or has_two_action_voices(action_voices)


def _resolved_evidence(
    evidence: List[Dict[str, Any]], evidence_index: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Claim-Bindings auf ihre kanonischen Records auflösen (ab Schema v3).

    Herkunft und Quellenmetadaten stehen am Record; Match und Entailment
    bleiben claim-relative Binding-Felder. Nur diese dürfen den Record
    ergänzen, damit Inline-Metadaten keine kanonische Herkunft überschreiben.
    """
    index = evidence_index or {}
    resolved: List[Dict[str, Any]] = []
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        record = index.get(str(entry.get("evidence_id") or ""))
        if isinstance(record, dict):
            resolved.append(
                dict(record)
                | {key: value for key, value in entry.items() if key in _CLAIM_RELATIVE_FIELDS}
            )
        else:
            resolved.append(entry)
    return resolved


#: Schwelle für ``verified``. Gespiegelt in ``confidence_calculator``
#: (``_compute_confidence_with_penalties``).
_VERIFIED_STRONG_MATCH = 0.85


def _verified_reachable(evidence: List[Dict[str, Any]]) -> bool:
    """Trägt diese Evidence die Stufe ``verified`` auch ohne Handarbeit?

    ``verified`` verlangt beides: einen starken Match (>= 0.85) und mindestens
    zwei unabhängige Quellen.
    """
    has_strong_match = any(
        float(entry.get("match_score") or 0.0) >= _VERIFIED_STRONG_MATCH
        for entry in evidence
        if "match_score" in entry
    )
    return has_strong_match and _count_independent_sources(evidence) >= 2


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
