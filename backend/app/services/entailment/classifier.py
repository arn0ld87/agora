"""Klassifikationslogik und Hauptprüfungsstufen für das Evidence-Entailment."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from ...contracts.document_manifest_contract import NON_SUPPORTING_DOCUMENT_ROLES
from ..claim_atomizer import split_compound_claim
from ..evidence_text import evidence_text
from ..quantifier_claims import (
    CHECK_CORE_SUPPORTED,
    CHECK_NEEDS_AGGREGATION,
    QuantifierStrength,
    detect_quantifier,
    evidence_backs_quantifier,
    quantifier_label,
)
from .linguistics import _content_tokens, _is_negated, _scopes_diverge
from .numeric_facts import extract_numeric_facts
from .patterns import (
    PREDICATE_COVERAGE_THRESHOLD,
    PREDICATE_MATCH_THRESHOLD,
    QUALITATIVE_RELATED_THRESHOLD,
    QUALITATIVE_SUPPORT_THRESHOLD,
    RETRIEVAL_RELEVANCE_THRESHOLD,
    TOPIC_MATCH_THRESHOLD,
    _DIVERGENCE_REASONS,
)
from .scoring import (
    _overlap_ratio,
    _quantifier_direction,
    coverage_ratio,
    subjects_match,
)
from .types import (
    BoundKind,
    EntailmentJudge,
    EntailmentResult,
    EntailmentVerdict,
    FactModality,
    NumericFact,
    SCENARIO_ROLE_REASON_PREFIX,
)


def _evidence_text(item: Dict[str, Any]) -> str:
    return evidence_text(item)


def facts_are_comparable(left: NumericFact, right: NumericFact) -> Optional[str]:
    """Reden beide Zahlen über denselben Sachverhalt?

    Gibt ``None`` zurück, wenn sie vergleichbar sind — sonst den Namen der
    Dimension, in der sie auseinanderlaufen.
    """
    if left.unit != right.unit:
        return "unit_mismatch"
    if left.modality is not right.modality:
        return "fact_type_mismatch"
    if _scopes_diverge(left.scope, right.scope):
        return "scope_mismatch"
    if left.bound is not right.bound and not _bound_is_violated(left, right):
        return "bound_satisfied"
    return None


def _bound_is_violated(left: NumericFact, right: NumericFact) -> bool:
    """Verletzt der gemessene Wert die behauptete Schranke?"""
    lower = next(
        (fact for fact in (left, right) if fact.bound is BoundKind.AT_LEAST), None
    )
    upper = next(
        (fact for fact in (left, right) if fact.bound is BoundKind.AT_MOST), None
    )
    if lower is not None and upper is not None:
        return lower.value > upper.value

    for bound_fact, point in ((left, right), (right, left)):
        if point.bound is not BoundKind.EXACT:
            continue
        if bound_fact.bound is BoundKind.AT_MOST and point.value > bound_fact.value:
            return True
        if bound_fact.bound is BoundKind.AT_LEAST and point.value < bound_fact.value:
            return True
    return False


def _classify_matching_number(
    claim_fact: NumericFact,
    ev_fact: NumericFact,
    predicate_overlap: float,
    checks: List[str],
) -> EntailmentResult:
    """Urteil für den Fall, dass Zahl *und* Bezugsgruppe übereinstimmen."""
    if ev_fact.modality is FactModality.NORMATIVE and (
        claim_fact.modality is FactModality.FACTUAL
    ):
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "Zahl und Bezugsgruppe passen; unklar, ob die Quelle "
            "einen Ist-Wert oder eine Zielvorgabe nennt",
            matched_fact=ev_fact,
            claim_fact=claim_fact,
            checks=checks + ["modality_mismatch"],
        )
    coverage = coverage_ratio(claim_fact.predicate, ev_fact.predicate)
    if (
        predicate_overlap >= PREDICATE_MATCH_THRESHOLD
        and coverage >= PREDICATE_COVERAGE_THRESHOLD
    ):
        return EntailmentResult(
            EntailmentVerdict.SUPPORTED,
            "Zahl, Bezugsgruppe und Aussage stimmen überein",
            matched_fact=ev_fact,
            claim_fact=claim_fact,
            checks=checks + ["value_subject_predicate_match"],
        )
    if coverage == 0.0 and (
        not _content_tokens(claim_fact.predicate)
        or not _content_tokens(ev_fact.predicate)
    ):
        if _is_negated(claim_fact.predicate) != _is_negated(ev_fact.predicate):
            return EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                "Zahl und Bezugsgruppe passen, die Aussagen "
                "sind aber gegensätzlich verneint",
                matched_fact=ev_fact,
                claim_fact=claim_fact,
                checks=checks + ["polarity_mismatch"],
            )
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "Zahl und Bezugsgruppe passen, die Aussage ist zu "
            "kurz, um gegen die Quelle geprüft zu werden",
            matched_fact=ev_fact,
            claim_fact=claim_fact,
            checks=checks + ["predicate_not_measurable"],
        )
    if coverage < PREDICATE_COVERAGE_THRESHOLD:
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "Zahl und Bezugsgruppe passen, der Claim behauptet "
            f"aber mehr als die Quelle deckt (Deckung {coverage:.2f})",
            matched_fact=ev_fact,
            claim_fact=claim_fact,
            checks=checks + ["predicate_overreach"],
        )
    return EntailmentResult(
        EntailmentVerdict.CONTRADICTED,
        "Zahl und Bezugsgruppe passen, die Aussage dazu nicht",
        matched_fact=ev_fact,
        claim_fact=claim_fact,
        checks=checks + ["predicate_mismatch"],
    )


def _classify_numeric_claim(
    claim_facts: List[NumericFact],
    evidence_facts: List[NumericFact],
    checks: List[str],
) -> EntailmentResult:
    """Regel 1 — der Claim trägt eine Zahl, und die entscheidet."""
    checks = checks + ["numeric_claim"]
    for claim_fact in claim_facts:
        for ev_fact in evidence_facts:
            same_value = (
                claim_fact.unit == ev_fact.unit
                and abs(claim_fact.value - ev_fact.value) < 0.001
            )
            same_subject = subjects_match(claim_fact.subject, ev_fact.subject)
            predicate_overlap = _overlap_ratio(claim_fact.predicate, ev_fact.predicate)

            if same_value and same_subject:
                return _classify_matching_number(
                    claim_fact, ev_fact, predicate_overlap, checks
                )

            if same_value and not same_subject:
                return EntailmentResult(
                    EntailmentVerdict.INSUFFICIENT,
                    "Zahl belegt, aber für eine andere Bezugsgruppe",
                    matched_fact=ev_fact,
                    claim_fact=claim_fact,
                    checks=checks + ["subject_mismatch"],
                )

            if (
                same_subject
                and not same_value
                and predicate_overlap >= PREDICATE_MATCH_THRESHOLD
            ):
                if any(
                    abs(other.value - ev_fact.value) < 0.001 for other in claim_facts
                ):
                    return EntailmentResult(
                        EntailmentVerdict.INSUFFICIENT,
                        "der Claim nennt den belegten Wert an anderer Stelle; "
                        "welche Zahl zu welcher Bezugsgruppe gehört, ist nicht "
                        "eindeutig zuzuordnen",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + ["value_mismatch_ambiguous_subject"],
                    )
                divergence = facts_are_comparable(claim_fact, ev_fact)
                if divergence is not None:
                    return EntailmentResult(
                        EntailmentVerdict.INSUFFICIENT,
                        "abweichender Zahlenwert, aber die beiden Angaben "
                        "sind nicht vergleichbar "
                        f"({_DIVERGENCE_REASONS[divergence]})",
                        matched_fact=ev_fact,
                        claim_fact=claim_fact,
                        checks=checks + [divergence],
                    )
                return EntailmentResult(
                    EntailmentVerdict.CONTRADICTED,
                    "gleiche Aussage über dieselbe Gruppe, abweichender Zahlenwert",
                    matched_fact=ev_fact,
                    claim_fact=claim_fact,
                    checks=checks + ["value_mismatch"],
                )

    return EntailmentResult(
        EntailmentVerdict.INSUFFICIENT,
        "numerischer Claim ohne passenden Zahlenbeleg",
        claim_fact=claim_facts[0],
        checks=checks + ["no_matching_number"],
    )


def _classify_quantifier_claim(
    claim: str,
    direction: str,
    evidence_facts: List[NumericFact],
    checks: List[str],
) -> EntailmentResult:
    """Regel 2 — der Claim behauptet eine Mehrheit oder Minderheit."""
    checks = checks + ["quantifier_claim"]
    for ev_fact in evidence_facts:
        if ev_fact.unit != "percent" or not subjects_match(claim, ev_fact.subject):
            continue
        is_majority = ev_fact.value > 50.0
        if direction == "majority" and not is_majority:
            return EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                f"Mehrheitsaussage steht gegen einen Anteil von {ev_fact.value:g} %",
                matched_fact=ev_fact,
                checks=checks + ["majority_vs_minority"],
            )
        if direction == "minority" and is_majority:
            return EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                f"Minderheitsaussage steht gegen einen Anteil von {ev_fact.value:g} %",
                matched_fact=ev_fact,
                checks=checks + ["minority_vs_majority"],
            )
    return EntailmentResult(
        EntailmentVerdict.RELATED_ONLY,
        "Mengenaussage ohne quantitativen Beleg",
        checks=checks + ["quantifier_unbacked"],
    )


_QUANTIFIER_SHARE_FLOOR: Dict[QuantifierStrength, Callable[[float], bool]] = {
    QuantifierStrength.UNIVERSAL: lambda pct: pct >= 99.5,
    QuantifierStrength.NEAR_UNIVERSAL: lambda pct: pct >= 80.0,
    QuantifierStrength.MAJORITY: lambda pct: pct > 50.0,
    QuantifierStrength.NONE: lambda pct: pct <= 0.5,
    QuantifierStrength.NEAR_NONE: lambda pct: pct <= 20.0,
}


def _classify_quantified_share(
    claim: str,
    strength: QuantifierStrength,
    evidence_facts: List[NumericFact],
    checks: List[str],
) -> tuple[Optional[EntailmentResult], bool]:
    """Regel 2 — prüft einen Quantor gegen Prozentangaben der Quelle (#1345)."""
    checks.append("quantifier_claim")
    meets = _QUANTIFIER_SHARE_FLOOR[strength]
    for ev_fact in evidence_facts:
        if ev_fact.unit != "percent" or not subjects_match(claim, ev_fact.subject):
            continue
        if meets(ev_fact.value):
            checks.append("quantifier_share_backed")
            return None, True
        return (
            EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                f"Mengenaussage „{quantifier_label(strength)}“ steht gegen einen "
                f"Anteil von {ev_fact.value:g} %",
                matched_fact=ev_fact,
                checks=checks + ["quantifier_vs_share"],
            ),
            False,
        )
    return None, False


def _cap_quantified_result(
    strength: QuantifierStrength,
    evidence_text: str,
    result: EntailmentResult,
) -> EntailmentResult:
    """Eine Quelle ohne eigene Mengenaussage trägt höchstens den Kern (#1345)."""
    if result.verdict is not EntailmentVerdict.SUPPORTED:
        return result
    if evidence_backs_quantifier(strength, evidence_text):
        result.checks.append("quantifier_backed_by_source")
        return result
    return EntailmentResult(
        EntailmentVerdict.RELATED_ONLY,
        f"Mengenaussage „{quantifier_label(strength)}“ — eine einzelne Quelle "
        "belegt nur die eigene Position, nicht ihre Verbreitung",
        checks=result.checks + [CHECK_CORE_SUPPORTED, CHECK_NEEDS_AGGREGATION],
    )


def _classify_qualitative_claim(
    claim: str,
    evidence_text: str,
    checks: List[str],
    *,
    topic_overlap: float,
    retrieval_score: Optional[float],
    judge: Optional[EntailmentJudge],
) -> EntailmentResult:
    """Regel 3 — der Claim trägt weder Zahl noch Mengenaussage."""
    retrieved = (
        retrieval_score is not None
        and retrieval_score >= RETRIEVAL_RELEVANCE_THRESHOLD
    )
    if retrieved:
        checks.append("retrieval_relevant")
    elif topic_overlap < TOPIC_MATCH_THRESHOLD:
        return EntailmentResult(
            EntailmentVerdict.INSUFFICIENT,
            "zu geringe inhaltliche Überschneidung",
            checks=checks + ["low_overlap"],
        )

    claim_coverage = coverage_ratio(claim, evidence_text)

    if claim_coverage >= QUALITATIVE_SUPPORT_THRESHOLD:
        atoms = split_compound_claim(claim)
        if len(atoms) > 1:
            uncovered = [
                atom
                for atom in atoms
                if coverage_ratio(atom, evidence_text) < QUALITATIVE_RELATED_THRESHOLD
            ]
            if uncovered:
                return EntailmentResult(
                    EntailmentVerdict.INSUFFICIENT,
                    "der Claim behauptet mehreres; zu "
                    f"{len(uncovered)} von {len(atoms)} Teilaussagen sagt die "
                    "Quelle nichts",
                    checks=checks + ["compound_claim_partially_uncovered"],
                )
        if _is_negated(claim) != _is_negated(evidence_text):
            return EntailmentResult(
                EntailmentVerdict.CONTRADICTED,
                "die Quelle deckt den Claim wörtlich ab, verneint ihn aber "
                f"gegenläufig (Deckung {claim_coverage:.2f})",
                checks=checks + ["qualitative_polarity_mismatch"],
            )
        return EntailmentResult(
            EntailmentVerdict.SUPPORTED,
            "die Quelle deckt den Claim weitgehend ab "
            f"(Deckung {claim_coverage:.2f})",
            checks=checks + ["high_claim_coverage"],
        )

    if claim_coverage < QUALITATIVE_RELATED_THRESHOLD and not retrieved:
        return EntailmentResult(
            EntailmentVerdict.RELATED_ONLY,
            "thematisch verwandt, aber kein Beleg "
            f"(Deckung {claim_coverage:.2f})",
            checks=checks + ["low_claim_coverage"],
        )

    if judge is not None:
        try:
            raw_verdict = str(judge(claim, evidence_text)).strip().upper()
            if raw_verdict in EntailmentVerdict.__members__:
                judge_verdict = EntailmentVerdict[raw_verdict]
                return EntailmentResult(
                    judge_verdict, "strukturierter Judge", checks=checks + ["judge"]
                )
        except Exception as exc:  # noqa: BLE001 — Judge ist optional; Regelpfad bleibt gültig
            from ..run_budget import reraise_if_budget_exceeded  # noqa: PLC0415

            reraise_if_budget_exceeded(exc)
            checks.append("judge_failed")

    return EntailmentResult(
        EntailmentVerdict.RELATED_ONLY,
        "thematisch verwandt, Beleggrad ohne inhaltliche Prüfung nicht "
        f"entscheidbar (Deckung {claim_coverage:.2f})",
        checks=checks + ["grey_zone_unjudged"],
    )


def classify_evidence(
    claim_text: str,
    evidence_item: Dict[str, Any],
    *,
    judge: Optional[EntailmentJudge] = None,
    retrieval_score: Optional[float] = None,
) -> EntailmentResult:
    """Entscheidet, ob ``evidence_item`` den Claim tatsächlich stützt."""
    claim = (claim_text or "").strip()
    ev_text = _evidence_text(evidence_item)
    if not claim or not ev_text:
        return EntailmentResult(EntailmentVerdict.INSUFFICIENT, "leerer Claim oder Evidence-Text")

    role = str(evidence_item.get("document_role") or "")
    if role in NON_SUPPORTING_DOCUMENT_ROLES:
        return EntailmentResult(
            EntailmentVerdict.RELATED_ONLY,
            f"{SCENARIO_ROLE_REASON_PREFIX} (document_role={role}) — Kontext, kein Beleg",
            checks=["non_supporting_document_role"],
        )

    checks: List[str] = []
    claim_facts = extract_numeric_facts(claim)
    evidence_facts = extract_numeric_facts(ev_text)
    topic_overlap = _overlap_ratio(claim, ev_text)

    # --- Regel 1: Claim trägt eine Zahl ------------------------------------
    if claim_facts:
        return _classify_numeric_claim(claim_facts, evidence_facts, checks)

    # --- Regel 2: Claim trägt eine Mengenaussage -----------------------------
    strength = detect_quantifier(claim)
    numerically_backed = False
    if strength is not None and evidence_facts:
        decided, numerically_backed = _classify_quantified_share(
            claim, strength, evidence_facts, checks
        )
        if decided is not None:
            return decided
    elif _quantifier_direction(claim) == "minority" and evidence_facts:
        return _classify_quantifier_claim(claim, "minority", evidence_facts, checks)

    result = _classify_qualitative_claim(
        claim,
        ev_text,
        checks,
        topic_overlap=topic_overlap,
        retrieval_score=retrieval_score,
        judge=judge,
    )
    if strength is None or numerically_backed:
        return result
    return _cap_quantified_result(strength, ev_text, result)


def classify_many(
    claim_text: str,
    evidence_items: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> List[EntailmentResult]:
    # Rufe classify_evidence über das Fassadenmodul oder direkt auf, damit
    # monkeypatching auf app.services.evidence_entailment wirksam bleibt.
    import sys

    facade = sys.modules.get("app.services.evidence_entailment")
    classifier_func = getattr(facade, "classify_evidence", classify_evidence) if facade else classify_evidence
    return [classifier_func(claim_text, item, judge=judge) for item in evidence_items]


__all__ = [
    "classify_evidence",
    "classify_many",
    "facts_are_comparable",
    "_bound_is_violated",
    "_cap_quantified_result",
    "_classify_matching_number",
    "_classify_numeric_claim",
    "_classify_qualitative_claim",
    "_classify_quantified_share",
    "_classify_quantifier_claim",
    "_evidence_text",
]
