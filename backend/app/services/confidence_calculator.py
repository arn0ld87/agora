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
  einen ``match_score >= 0.85`` trägt — sonst gedeckelt auf 0.89)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

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
    """Liefert (score, label) für eine Evidence-Liste."""
    if not evidence:
        return 0.15, "low"
    relevance = _component_relevance(evidence)
    source_quality = _component_source_quality(evidence)
    specificity = _component_specificity(evidence)
    consistency = _component_consistency(evidence)

    raw = (
        0.40 * relevance
        + 0.25 * source_quality
        + 0.20 * specificity
        + 0.15 * consistency
        - max(0.0, contradiction_penalty)
    )
    score = max(0.0, min(1.0, raw))

    has_strong_match = any(
        float(e.get("match_score") or 0.0) >= 0.85
        for e in evidence
        if "match_score" in e
    )
    # Verified nur bei direkter, claim-spezifischer Evidence (S6 Reviewer-Spec).
    if score >= 0.90 and not has_strong_match:
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


__all__ = ["compute_confidence"]
