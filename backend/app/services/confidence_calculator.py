"""S6 — formelbasierte Confidence-Berechnung für Report-Claims.

Vorher: ``confidence_score = min(0.95, 0.25 + support_count * 0.12)`` —
quasi linear in der Anzahl der Evidence-Items, ohne Qualitätsbewertung.
Folge: jeder Claim mit 6+ Items wurde 0.95 (Label "high"), egal wie
relevant die Evidence inhaltlich war. Reviewer hatte das als
unkalibriert markiert.

Neue Formel (Reviewer-Empfehlung, leicht abgeschwächt):

    score = 0.40 * relevance
          + 0.25 * source_quality
          + 0.20 * specificity
          + 0.15 * consistency
          - contradiction_penalty

Komponenten kapitulieren bei 1.0; Penalty ist heute fix 0 (kein
Contradiction-Detector live), bleibt aber als Hook erhalten.

Labels:

* 0.00 – 0.39 → ``low``
* 0.40 – 0.69 → ``medium``
* 0.70 – 0.89 → ``high``
* 0.90 – 1.00 → ``verified`` (nur wenn mindestens ein Evidence-Item
  einen ``match_score >= 0.85`` trägt UND mindestens 2 unabhängige
  Quellen vorliegen — sonst gedeckelt auf 0.89)
* Zusätzlich: wenn alle match_scores < 0.55 → Deckel auf 0.69 (medium)

MAI-14: Contradiction-Penalty.

Wenn Evidence-Items derselben Claim auseinandergehende Sentiments tragen,
ist die Behauptung weniger belastbar. Konkret:
- Wenn std(sentiment_scores) > 0.6 → Penalty -0.2.
- Wenn min < -0.3 und max > +0.3 → Penalty -0.2 (gemischter Tenor).

Die Heuristik greift in compute_confidence automatisch, sobald mindestens
2 Evidence-Items ein sentiment_score-Feld tragen. Die Penalty wird
zusätzlich zum extern übergebenen contradiction_penalty aufaddiert.
compute_claim_confidence() ist die erweiterte Variante für Aufrufer,
die applied_penalties auswerten wollen.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Tuple

# MAI-14: Schwellwerte für Sentiment-Contradiction-Heuristik.
_CONTRADICTION_PENALTY_AMOUNT: float = 0.2
_CONTRADICTION_STD_THRESHOLD: float = 0.6
_CONTRADICTION_RANGE_LOW: float = -0.3
_CONTRADICTION_RANGE_HIGH: float = 0.3


def _has_contradiction(sentiment_scores: List[float]) -> bool:
    """Erkennt widersprüchliche Sentiment-Vektoren in einem Evidence-Set.

    Zwei Kriterien (OR-verknüpft):
    1. Populationsstandardabweichung > 0.6 — hohe Streuung.
    2. Minimum < -0.3 UND Maximum > +0.3 — gemischter Tenor.

    Mindestens 2 Scores nötig; 1 Score kann nicht widersprüchlich sein.
    """
    if len(sentiment_scores) < 2:
        return False
    stddev = statistics.pstdev(sentiment_scores)
    if stddev > _CONTRADICTION_STD_THRESHOLD:
        return True
    low = min(sentiment_scores)
    high = max(sentiment_scores)
    if low < _CONTRADICTION_RANGE_LOW and high > _CONTRADICTION_RANGE_HIGH:
        return True
    return False


def _extract_sentiment_scores(evidence: List[Dict]) -> List[float]:
    """Extrahiert valide sentiment_score-Werte aus einer Evidence-Liste."""
    result: List[float] = []
    for e in evidence:
        val = e.get("sentiment_score")
        if val is not None and isinstance(val, (int, float)):
            result.append(float(val))
    return result


# S6: Source-Quality-Gewichtung. Bewusst grob — der Audit-Trail wird
# in S5 ohnehin getrennt und fließt hier nicht ein.
_SOURCE_WEIGHTS: Dict[str, float] = {
    "graph_fact": 1.0,
    "graph_metric": 0.85,
    "graph_metric_status": 0.5,
    "relationship_chain": 0.95,
    "entity_summary": 0.85,
    "agent_action": 0.7,
    "agent_behavior": 0.75,
    "section_synthesis": 0.0,
    "model_generated_inference": 0.0,
}


def _component_relevance(evidence: List[Dict]) -> float:
    """Mittelwert der `match_score`-Felder; ohne Scores Konservativ-Default."""
    scores = [float(e.get("match_score") or 0.0) for e in evidence if "match_score" in e]
    if scores:
        return min(1.0, sum(scores) / len(scores))
    if not evidence:
        return 0.0
    return 0.5


def _component_source_quality(evidence: List[Dict]) -> float:
    if not evidence:
        return 0.0
    weights = [_SOURCE_WEIGHTS.get(str(e.get("type") or ""), 0.6) for e in evidence]
    return min(1.0, sum(weights) / len(weights))


def _component_specificity(evidence: List[Dict]) -> float:
    """Top-Match-Score → Spezifität. Ohne Scores: 0.5 (mid)."""
    scores = [float(e.get("match_score") or 0.0) for e in evidence if "match_score" in e]
    if not scores:
        return 0.5 if evidence else 0.0
    top = max(scores)
    if top >= 0.85:
        return 1.0
    if top >= 0.7:
        return 0.8
    if top >= 0.55:
        return 0.6
    return 0.4


def _component_consistency(evidence: List[Dict]) -> float:
    """Wieviele unabhängige Quellen? Mehr = robuster gegen Einzelfehler."""
    sources = {(e.get("type"), e.get("source")) for e in evidence}
    if len(sources) >= 3:
        return 1.0
    if len(sources) == 2:
        return 0.8
    if len(sources) == 1:
        return 0.6
    return 0.0


def compute_confidence(
    evidence: List[Dict],
    *,
    contradiction_penalty: float = 0.0,
) -> Tuple[float, str]:
    """Liefert (score, label) für eine Evidence-Liste.

    MAI-14: Wenn sentiment_score-Felder in den Evidence-Items vorhanden sind
    und _has_contradiction() anschlägt, wird automatisch ein Sentiment-
    Contradiction-Penalty von 0.2 aufaddiert (zusätzlich zum extern
    übergebenen contradiction_penalty).
    """
    if not evidence:
        return 0.15, "low"
    relevance = _component_relevance(evidence)
    source_quality = _component_source_quality(evidence)
    specificity = _component_specificity(evidence)
    consistency = _component_consistency(evidence)

    # MAI-14: Sentiment-Contradiction-Penalty auto-berechnen
    sentiments = _extract_sentiment_scores(evidence)
    sentiment_penalty = _CONTRADICTION_PENALTY_AMOUNT if _has_contradiction(sentiments) else 0.0

    total_penalty = max(0.0, contradiction_penalty) + sentiment_penalty

    raw = (
        0.40 * relevance
        + 0.25 * source_quality
        + 0.20 * specificity
        + 0.15 * consistency
        - total_penalty
    )
    score = max(0.0, min(1.0, raw))

    has_strong_match = any(
        float(e.get("match_score") or 0.0) >= 0.85
        for e in evidence
        if "match_score" in e
    )
    unique_sources = len({(e.get("type"), e.get("source")) for e in evidence})

    # Task 08: Medium-Cap — kein Claim darf "high" sein, wenn alle
    # match_scores unter 0.55 liegen.
    match_scores = [
        float(e.get("match_score") or 0.0)
        for e in evidence
        if "match_score" in e
    ]
    all_weak_matches = match_scores and max(match_scores) < 0.55
    if all_weak_matches:
        score = min(score, 0.69)

    # Task 08: verified nur bei starkem Match UND mind. 2 unabhängigen Quellen.
    if score >= 0.90 and (not has_strong_match or unique_sources < 2):
        score = 0.89

    if score < 0.40:
        label = "low"
    elif score < 0.70:
        label = "medium"
    elif score < 0.90:
        label = "high"
    else:
        label = "verified"

    return round(score, 3), label


def compute_claim_confidence(
    evidence: List[Dict],
    *,
    base_score: float = 0.5,
    contradiction_penalty: float = 0.0,
) -> Tuple[float, str, List[str]]:
    """Erweiterte Variante von compute_confidence mit Penalty-Audit-Trail.

    Returns:
        (score, label, applied_penalties)
        score: 0.0–1.0
        label: "low" | "medium" | "high" | "verified"
        applied_penalties: Namen aller angewandten Penalties für Audit.

    MAI-14: Erkennt Sentiment-Widersprüche (std > 0.6 ODER Range > 0.6)
    und trägt "contradiction_penalty" in applied_penalties ein.
    """
    applied_penalties: List[str] = []

    # MAI-14: Sentiment-Contradiction-Heuristik
    sentiments = _extract_sentiment_scores(evidence)
    sentiment_contradiction = _has_contradiction(sentiments)
    if sentiment_contradiction:
        applied_penalties.append("contradiction_penalty")

    # Delegiere an compute_confidence — dadurch bleiben alle bestehenden
    # Formeln (relevance, source_quality, specificity, consistency, caps)
    # konsistent.
    score, label = compute_confidence(
        evidence,
        contradiction_penalty=contradiction_penalty,
        # Hinweis: compute_confidence berechnet den Sentiment-Penalty intern
        # nochmal selbst — das ist korrekt, da es die einzige Authoritative
        # Stelle für die Formel ist.
    )
    return score, label, applied_penalties


__all__ = ["compute_confidence", "compute_claim_confidence", "_has_contradiction"]
