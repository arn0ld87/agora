"""Claim-, Hypothesis- und Metadaten-Extraktionshelfer für ReportManager (Issue #1864)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional

from ...contracts.report_contract import counts_for_confidence
from ...contracts.report_v3 import (
    Claim as ReportV3Claim,
    DataGap as ReportV3DataGap,
    Hypothesis as ReportV3Hypothesis,
)
from ...utils.logger import get_logger
from .claim_dedup import dedup_claims, duplicate_report
from .claim_provenance import (
    derive_aggregation_basis,
    derive_confidence_scope as _derive_confidence_scope,
    resolve_canonical_voice_keys,
)
from .evidence import text_confidence_label_of
from .metadata_merge import merge_section_metadata
from .threshold_deviation import drop_unresolvable_deviations
from .threshold_provenance import bind_threshold_provenance, dedup_thresholds

logger = get_logger("agora.report_agent")

#: Werte von ``report_contract.ClaimType`` (Issue #1400); Unbekanntes faellt
#: auf ``None`` statt die v3-Validierung zu sprengen.
_CLAIM_TYPES = frozenset({"empirical", "analytical", "recommendation", "structural"})
_VALID_CONFIDENCE = frozenset({"speculative", "low", "medium", "high", "verified"})


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
        "; ".join(
            f"{entry['claim_id']}→{entry['duplicate_of']}"
            for entry in duplicates[:5]
        ),
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
            bind_threshold_provenance(
                metadata_kwargs["thresholds"], list(evidence_index.values())
            )
        )
    )


def _claim_type_of(
    claim: Dict[str, Any],
) -> Literal["empirical", "analytical", "recommendation", "structural"] | None:
    value = claim.get("claim_type")
    return value if value in _CLAIM_TYPES else None  # type: ignore[return-value]


def _wording_confidence(
    claim_type: Optional[str],
    confidence: Literal["speculative", "low", "medium", "high", "verified"],
) -> Literal["speculative", "low", "medium", "high", "verified"] | None:
    """Issue #1400: der Wortlaut-Hinweis gilt nur Tatsachenbehauptungen.

    Das Label wird unabhaengig vom Typ abgesenkt; nur eine Tatsache kann
    sicherer formuliert sein, als ihr Label traegt.
    """
    return confidence if claim_type in (None, "empirical") else None


def _count_independent_sources(
    evidence_refs: Iterable[str],
    raw_evidence: Any,
    evidence_index: Mapping[str, Any],
) -> int:
    """Zaehlt unabhaengige Stuetzquellen unter den gueltigen Evidence-Refs.

    Zwei Items mit demselben voice_key (z. B. zwei Zitate derselben Persona)
    zaehlen als nur eine Stimme (ADR-0002, Issue #1766).
    """
    items_by_eid: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if isinstance(item, dict) and item.get("evidence_id"):
                eid = str(item.get("evidence_id"))
                if eid not in items_by_eid and item.get("supports_claim") is True:
                    items_by_eid[eid] = item

    pairs: list[tuple[str, Dict[str, Any], Optional[Mapping[str, Any]]]] = []
    for eid in evidence_refs:
        item = items_by_eid.get(eid) or {"evidence_id": eid}
        record = evidence_index.get(eid) if isinstance(evidence_index, Mapping) else None
        record_map = record if isinstance(record, Mapping) else None
        pairs.append((eid, item, record_map))

    voice_keys = resolve_canonical_voice_keys(
        [(item, record_map) for _, item, record_map in pairs]
    )
    unique_keys: set[Any] = set()
    for (eid, _, _), vk in zip(pairs, voice_keys):
        if vk:
            unique_keys.add(("voice", vk))
        else:
            unique_keys.add(("ref", eid))
    return len(unique_keys)


def _valid_evidence_refs_for_claim(
    claim: Dict[str, Any],
    evidence_index: Dict[str, Any],
) -> List[str]:
    """Extrahiert deduplizierte, unterstützende Evidence-IDs eines Claims."""
    refs: List[str] = []
    for item in claim.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("evidence_id")
        if not raw_id or item.get("supports_claim") is not True:
            continue
        if not counts_for_confidence(item):
            continue
        eid = str(raw_id)
        idx_entry = evidence_index.get(eid)
        if isinstance(idx_entry, (dict, Mapping)) and not counts_for_confidence(idx_entry):
            continue
        if eid not in refs:
            refs.append(eid)
    return refs


def _should_downgrade_single_source(
    independent_sources: int,
    confidence: str,
    claim_type: Optional[str],
) -> bool:
    """Prüft, ob ein Claim wegen Einzelquelle auf ``low`` abgestuft werden muss."""
    if independent_sources > 1:
        return False
    if confidence in {"high", "verified"}:
        return True
    return confidence == "medium" and claim_type not in ("structural", "recommendation")


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
    Argumenten und den Modul-Helfern ``derive_aggregation_basis``,
    ``_derive_confidence_scope`` und ``_text_confidence_for``.
    """
    claims: List[ReportV3Claim] = []
    claim_slot = 0
    for claim in raw_claims or []:
        if not isinstance(claim, dict):
            continue
        evidence_refs = _valid_evidence_refs_for_claim(claim, evidence_index)
        # balanced/explorative: Claims ohne Evidence → überspringen (kein Evidence-Anker)
        # strict: Claims ohne Evidence → gedroppt (gleiche Logik, aber auch low-conf)
        if not evidence_refs:
            continue
        statement = str(claim.get("claim_text") or claim.get("claim") or "").strip()
        if len(statement) < 8:
            continue
        label = str(claim.get("confidence_label") or "speculative")
        confidence: Literal["speculative", "low", "medium", "high", "verified"] = (
            label if label in _VALID_CONFIDENCE else "speculative"  # type: ignore[assignment]
        )
        single_source_text_confidence: Literal[
            "speculative", "low", "medium", "high", "verified"
        ] | None = None
        claim_type = _claim_type_of(claim)
        independent_sources = _count_independent_sources(
            evidence_refs, claim.get("evidence"), evidence_index
        )
        if _should_downgrade_single_source(independent_sources, confidence, claim_type):
            single_source_text_confidence = _wording_confidence(claim_type, confidence)
            confidence = "low"
        # strict: speculative/low-confidence Claims werden gedroppt
        if report_mode == "strict" and confidence in {"speculative", "low"}:
            continue
        claim_slot += 1
        claims.append(ReportV3Claim(
            id=f"C{section_index}_{claim_slot:02d}",
            statement=statement,
            evidence_refs=evidence_refs,
            confidence=confidence,
            # Issue #1358: beide Angaben stammen aus derselben Menge
            # stuetzender Items. Vorher stand hier der Literalwert
            # "persona" — jeder Claim behauptete damit Persona-
            # Traegerschaft, auch wenn er ausschliesslich aus dem
            # Seed-Dokument stammte.
            aggregation_basis=derive_aggregation_basis(
                claim.get("evidence"), evidence_index
            ),
            confidence_scope=_derive_confidence_scope(
                claim.get("evidence"), evidence_index
            ),
            # Issue #1012: nur gesetzt, wenn der Claim nachtraeglich
            # abgestuft wurde. Der Wortlaut stammt dann aus einer
            # hoeheren Stufe und deckt mehr Sicherheit ab als das
            # Label — ohne dass irgendetwas am Text geaendert wird.
            text_confidence=(
                _text_confidence_for(claim, confidence)
                or single_source_text_confidence
            ),
            claim_type=claim_type,
        ))
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
                hypothesis_export_ids[raw_id] = (
                    f"{id_prefix}{section_index}_{h_slot_idx:02d}"
                )
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
        hypothesis_ref = hypothesis_export_ids.get(
            str(gap.get("hypothesis_id") or "").strip()
        )
        suggested_fix = gap.get("suggested_fix")
        severity: Literal["low", "medium", "high"] = (
            "high" if reason == "no_evidence_bound" else "medium"
        )
        data_gaps.append(ReportV3DataGap(
            id=f"G{section_index}_{gap_slot:02d}",
            beschreibung=description,
            severity=severity,
            suggested_fixes=[str(suggested_fix)] if suggested_fix else [],
            related_hypothesis_id=hypothesis_ref,
        ))
    return data_gaps


def _parse_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_clamped_confidence(value: Any) -> float:
    try:
        score = float(value or 0.0)
    except (TypeError, ValueError):
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
            hypotheses.append(ReportV3Hypothesis(
                id=hypothesis_id,
                hypothesis_text=text,
                rationale=str(hypothesis.get("rationale") or ""),
                suggested_evidence=[
                    str(item)
                    for item in (hypothesis.get("suggested_evidence") or [])
                    if str(item).strip()
                ],
                origin_section_index=_parse_optional_int(origin_raw),
                confidence_score=_parse_clamped_confidence(
                    hypothesis.get("confidence_score")
                ),
            ))
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
            item.model_copy(update={
                "evidence_refs": [
                    ref for ref in item.evidence_refs if ref in evidence_index
                ]
            })
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
