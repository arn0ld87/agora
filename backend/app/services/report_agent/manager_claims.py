"""Claim-, Hypothesis- und Metadaten-Extraktionshelfer für ReportManager (Issue #1864)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from ...contracts.report_v3 import (
    Claim as ReportV3Claim,
    DataGap as ReportV3DataGap,
    Hypothesis as ReportV3Hypothesis,
)
from ...utils.logger import get_logger
from .claim_dedup import dedup_claims, duplicate_report
from .claim_qualification import (  # noqa: F401
    _CLAIM_TYPES,
    _VALID_CONFIDENCE,
    claim_type_of as _claim_type_of,
    count_independent_sources_for_refs as _count_independent_sources,
    derive_aggregation_basis,
    derive_confidence_scope as _derive_confidence_scope,
    evaluate_claim_mode_gate,
    should_downgrade_single_source as _should_downgrade_single_source,
    valid_evidence_refs_for_claim as _valid_evidence_refs_for_claim,
    wording_confidence as _wording_confidence,
)
from .evidence import text_confidence_label_of
from .metadata_merge import merge_section_metadata
from .threshold_deviation import drop_unresolvable_deviations
from .threshold_provenance import bind_threshold_provenance, dedup_thresholds

logger = get_logger("agora.report_agent")


def _text_confidence_for(
    claim: dict[str, Any], current: str
) -> "Literal['speculative', 'low', 'medium', 'high', 'verified'] | None":
    """Die Stufe, unter der der Wortlaut entstand — oder ``None`` (#1012).

    ``None`` ist der Normalfall: der Wortlaut passt zum Label. Stimmt die
    protokollierte Ausgangsstufe mit dem aktuellen Label ueberein, wurde
    faktisch nichts abgestuft — dann ebenfalls ``None``, statt eine Abstufung
    auszuweisen, die keine ist.
    """
    recorded = text_confidence_label_of(claim)
    if not recorded or recorded == current:
        return None
    if recorded not in _VALID_CONFIDENCE:
        return None
    return recorded  # type: ignore[return-value]


def _dedup_claims_with_log(claims: list) -> list:
    """Derselbe Befund aus mehreren Abschnitten ist ein Befund.

    Über die sieben Abschnitte des Referenzlaufs ``report_cc2ef45da5e9``
    verteilten sich mehrfach praktisch identische Aussagen — für den Leser
    sieht das aus wie mehrfache Bestätigung, tatsächlich ist es dieselbe
    Quelle, mehrfach zitiert. Zusammengeführt wird nur bei gleichen Zahlen,
    gleicher Belegmenge und hoher Wortüberlappung; das Entfernte steht im Log.
    """
    duplicates = duplicate_report(claims)
    if not duplicates:
        return claims
    logger.info(
        "build_report_v3: %d Claim-Dublette(n) entfernt: %s",
        len(duplicates),
        "; ".join(f"{entry['claim_id']}→{entry['duplicate_of']}" for entry in duplicates[:5]),
    )
    return dedup_claims(claims)


def _bind_and_dedup_thresholds(metadata_kwargs: dict, evidence_index: dict) -> None:
    """Zwei Schritte, die kein anderer Metadaten-Slot braucht.

    Eine Zahl, die wörtlich in einer Quelle steht, darf nicht als unbelegte
    Heuristik enden, und dieselbe Zahl aus zwei Abschnitten ist ein
    Schwellenwert, nicht zwei. Im Referenzlauf trugen alle 27 Thresholds
    ``evidence_status="heuristic"`` bei leeren ``evidence_refs`` — auch die aus
    dem Seed-Dokument — und mehrere Werte erschienen doppelt mit
    widersprüchlicher Herkunftsangabe.
    """
    if not metadata_kwargs.get("thresholds"):
        return
    # Issue #1359: erst nach der Deduplizierung steht fest, welche Kennungen
    # es im Bericht gibt — ein Verweis auf eine verworfene zeigte ins Leere.
    metadata_kwargs["thresholds"] = drop_unresolvable_deviations(
        dedup_thresholds(
            bind_threshold_provenance(metadata_kwargs["thresholds"], list(evidence_index.values()))
        )
    )


def _extract_claims_for_section(
    raw_claims: Any,
    *,
    section_index: int,
    evidence_index: Dict[str, Any],
    report_mode: Optional[str],
) -> List[ReportV3Claim]:
    """Baut die exportierten Claims eines Abschnitts aus der Rohform.

    Issue #1341: Die abschnittsinterne ``claim_id`` (``claim_01``) ist nur
    innerhalb ihres Abschnitts eindeutig. Beim Merge zu einer flachen Liste
    kollidieren die Nummernraeume. Exportiert wird deshalb eine
    abschnittsqualifizierte ID nach demselben Muster, das die Hypothesen
    benutzen (``H<n>_<i>``). Der Zaehler laeuft ueber die *akzeptierten*
    Claims: er wird erst hochgezaehlt, wenn der Claim alle Filter passiert hat,
    damit die ID die finale Liste beschreibt und nicht die Rohextraktion.

    Die Funktion ist bewusst frei von Instanz-Zustand — sie haengt nur an ihren
    Argumenten und dem kanonischen Qualifikations-Gate ``evaluate_claim_mode_gate``.
    """
    claims: List[ReportV3Claim] = []
    claim_slot = 0
    for claim in raw_claims or []:
        if not isinstance(claim, dict):
            continue
        raw_label = str(claim.get("confidence_label") or "speculative")
        initial_conf: Literal["speculative", "low", "medium", "high", "verified"] = (
            raw_label if raw_label in _VALID_CONFIDENCE else "speculative"  # type: ignore[assignment]
        )
        decision = evaluate_claim_mode_gate(
            claim,
            evidence_index,
            report_mode=report_mode,
            recorded_text_confidence=_text_confidence_for(claim, initial_conf),
        )
        if not decision.accepted:
            continue
        statement = str(claim.get("claim_text") or claim.get("claim") or "").strip()
        claim_slot += 1
        claims.append(
            ReportV3Claim(
                id=f"C{section_index}_{claim_slot:02d}",
                statement=statement,
                evidence_refs=list(decision.qualified_evidence.valid_evidence_refs),
                confidence=decision.confidence,
                # Issue #1358: beide Angaben stammen aus derselben Menge
                # stuetzender Items im qualifizierten Beleg-Objekt.
                aggregation_basis=decision.qualified_evidence.aggregation_basis,
                confidence_scope=decision.qualified_evidence.confidence_scope,
                # Issue #1012: nur gesetzt, wenn der Claim nachtraeglich
                # abgestuft wurde. Der Wortlaut stammt dann aus einer
                # hoeheren Stufe und deckt mehr Sicherheit ab als das
                # Label — ohne dass irgendetwas am Text geaendert wird.
                text_confidence=(
                    _text_confidence_for(claim, decision.confidence) or decision.text_confidence
                ),
                claim_type=decision.claim_type,
            )
        )
    return claims


def _build_hypothesis_export_ids(
    hypothesis_slots: list[tuple[str, list[dict[str, Any]]]],
    *,
    section_index: int,
) -> dict[str, str]:
    """Bildet abschnittsinterne Roh-IDs (``hypothesis_01``) auf Export-IDs ab (#1319)."""
    hypothesis_export_ids: dict[str, str] = {}
    for id_prefix, slot in hypothesis_slots:
        for h_slot_idx, hypothesis in enumerate(slot, start=1):
            if not isinstance(hypothesis, dict):
                continue
            if not str(hypothesis.get("hypothesis_text") or "").strip():
                continue
            raw_id = str(hypothesis.get("hypothesis_id") or "").strip()
            if raw_id:
                hypothesis_export_ids[raw_id] = f"{id_prefix}{section_index}_{h_slot_idx:02d}"
    return hypothesis_export_ids


def _extract_data_gaps_for_section(
    raw_gaps: Any,
    *,
    section_index: int,
    hypothesis_export_ids: dict[str, str],
) -> List[ReportV3DataGap]:
    """Extrahiert Datenlücken eines Abschnitts mit stabilen Export-IDs (#1342, #1319)."""
    data_gaps: List[ReportV3DataGap] = []
    gap_slot = 0
    for gap in raw_gaps or []:
        if not isinstance(gap, dict):
            continue
        gap_slot += 1
        claim_text = str(gap.get("claim_text") or gap.get("gap_reason") or "")
        reason = str(gap.get("gap_reason") or "").strip()
        description = claim_text if not reason else f"{claim_text} ({reason})"
        description = description.strip() or "Datenluecke ohne Claim-Text."
        hypothesis_ref = hypothesis_export_ids.get(str(gap.get("hypothesis_id") or "").strip())
        suggested_fix = gap.get("suggested_fix")
        severity: Literal["low", "medium", "high"] = (
            "high" if reason == "no_evidence_bound" else "medium"
        )
        data_gaps.append(
            ReportV3DataGap(
                id=f"G{section_index}_{gap_slot:02d}",
                beschreibung=description,
                severity=severity,
                suggested_fixes=[str(suggested_fix)] if suggested_fix else [],
                related_hypothesis_id=hypothesis_ref,
            )
        )
    return data_gaps


def _parse_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _parse_clamped_confidence(value: Any) -> float:
    try:
        score = float(value or 0.0)
    except TypeError, ValueError:
        score = 0.0
    return max(0.0, min(1.0, score))


def _extract_hypotheses_for_section(
    hypothesis_slots: list[tuple[str, list[dict[str, Any]]]],
    *,
    section_index: int,
) -> List[ReportV3Hypothesis]:
    """Extrahiert sichtbare und Appendix-Hypothesen eines Abschnitts (Slice 3, #495)."""
    hypotheses: List[ReportV3Hypothesis] = []
    for id_prefix, slot in hypothesis_slots:
        for h_slot_idx, hypothesis in enumerate(slot, start=1):
            if not isinstance(hypothesis, dict):
                continue
            text = str(hypothesis.get("hypothesis_text") or "").strip()
            if not text:
                continue
            hypothesis_id = f"{id_prefix}{section_index}_{h_slot_idx:02d}"
            origin_raw = hypothesis.get("origin_section_index", section_index)
            hypotheses.append(
                ReportV3Hypothesis(
                    id=hypothesis_id,
                    hypothesis_text=text,
                    rationale=str(hypothesis.get("rationale") or ""),
                    suggested_evidence=[
                        str(item)
                        for item in (hypothesis.get("suggested_evidence") or [])
                        if str(item).strip()
                    ],
                    origin_section_index=_parse_optional_int(origin_raw),
                    confidence_score=_parse_clamped_confidence(hypothesis.get("confidence_score")),
                )
            )
    return hypotheses


def _build_metadata_kwargs(
    sections: Any,
    evidence_index: Dict[str, Any],
) -> Dict[str, Any]:
    """Führt strukturierte Abschnitts-Metadaten zusammen und filtert Evidence-Refs (P0-6)."""
    merged = merge_section_metadata(sections or [])
    if merged.rejected:
        logger.warning(
            "build_report_v3: %d Metadaten-Eintrag/Einträge verworfen: %s",
            len(merged.rejected),
            "; ".join(merged.rejected[:5]),
        )
    metadata_kwargs = merged.as_report_v3_kwargs()
    for slot, items in list(metadata_kwargs.items()):
        metadata_kwargs[slot] = [
            item.model_copy(
                update={
                    "evidence_refs": [ref for ref in item.evidence_refs if ref in evidence_index]
                }
            )
            if hasattr(item, "evidence_refs")
            else item
            for item in items
        ]
    _bind_and_dedup_thresholds(metadata_kwargs, evidence_index)
    return metadata_kwargs


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
]
