"""S6 — Tests für die Confidence-Formel.

Reviewer hatte gefordert: Score muss kalibriert sein, `verified` darf
nur bei direkter Evidence vergeben werden. Diese Tests fixieren die
wichtigsten Eckpunkte der Formel.

MAI-14: Zusätzliche Tests für Sentiment-Contradiction-Penalty.
"""

from __future__ import annotations

from app.services.confidence_calculator import (
    _has_contradiction,
    compute_claim_confidence,
    compute_confidence,
)


def test_no_evidence_yields_speculative():
    # Slice 2: leere Evidence-Liste → (0.15, "speculative")
    # 0.15 < 0.45 → neues unterste Tier "speculative".
    score, label = compute_confidence([])
    assert score == 0.15
    assert label == "speculative"


def test_single_unmatched_graph_fact_yields_low():
    """Ein einzelnes Graph-Fact ohne match_score → low-Confidence (0.64 < 0.65)."""
    score, label = compute_confidence([
        {"type": "graph_fact", "source": "report_tool", "snippet": "x"},
    ])
    # source_quality 1.0, relevance 0.5, specificity 0.5, consistency 0.6
    # = 0.4*0.5 + 0.25*1.0 + 0.20*0.5 + 0.15*0.6 = 0.64 → low (0.45 ≤ 0.64 < 0.65)
    assert label == "low"
    assert 0.5 < score < 0.7


def test_strong_match_score_unlocks_verified():
    """Ein Item mit match_score >= 0.85 erlaubt Verified-Label."""
    score, label = compute_confidence([
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "x", "match_score": 0.92},
        {"type": "graph_fact", "source": "search_service",
         "snippet": "y", "match_score": 0.88},
        {"type": "entity_summary", "source": "graph_tools",
         "snippet": "z", "match_score": 0.86},
    ])
    assert score >= 0.90
    assert label == "verified"


def test_repeated_high_scores_from_one_source_cap_at_low():
    """Mehrere Treffer derselben Quelle bleiben ein Single-Source-Claim."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": f"x{i}", "match_score": 0.78}
        for i in range(5)
    ]
    score, label = compute_confidence(items)
    # Alle Items gleiche source → 1 unique source → consistency=0.6
    # relevance=0.78, source_quality=1.0, specificity=0.8 (0.78≥0.70), consistency=0.6
    # raw = 0.40*0.78 + 0.25*1.0 + 0.20*0.8 + 0.15*0.6 = 0.312+0.25+0.16+0.09 = 0.812
    assert score <= 0.59
    assert label == "low"


def test_off_topic_low_match_score_yields_speculative_or_low():
    """Niedrige match_scores drücken den Score in speculative/low."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "x", "match_score": 0.20},
        {"type": "agent_action", "source": "simulation_actions",
         "snippet": "y", "match_score": 0.15},
    ]
    score, label = compute_confidence(items)
    assert label in ("speculative", "low")
    assert score < 0.65


def test_audit_trail_types_get_zero_source_weight():
    """model_generated_inference und section_synthesis schlagen 0 Gewicht
    in source_quality — Defense-in-depth, falls jemand S5-Trennung umgeht."""
    items = [
        {"type": "model_generated_inference", "snippet": "..."},
        {"type": "section_synthesis", "snippet": "..."},
    ]
    score, _label = compute_confidence(items)
    # source_quality fällt komplett auf 0, Score sollte unter graph_fact-only
    # Baseline (0.64) liegen.
    assert score < 0.64


def test_contradiction_penalty_lowers_score():
    """Mit zwei Evidence-Items senkt die Penalty den Score messbar."""
    items = [
        {"type": "graph_fact", "source": "x", "match_score": 0.9},
        {"type": "graph_fact", "source": "y", "match_score": 0.85},
    ]
    base, _ = compute_confidence(items)
    penal, _ = compute_confidence(items, contradiction_penalty=0.3)
    assert penal == round(max(0.0, base - 0.3), 3) or penal < base


# ---------------------------------------------------------------------------
# MAI-14: Sentiment-Contradiction-Penalty
# ---------------------------------------------------------------------------


def test_has_contradiction_stddev():
    """_has_contradiction erkennt hohe Streuung (std > 0.6)."""
    assert _has_contradiction([0.9, -0.8, 0.7]) is True


def test_has_contradiction_range():
    """_has_contradiction erkennt gemischten Tenor (min<-0.3, max>+0.3)."""
    assert _has_contradiction([0.5, -0.5]) is True


def test_has_contradiction_aligned():
    """Konsistente Sentiments → kein Widerspruch."""
    assert _has_contradiction([0.4, 0.5, 0.6]) is False


def test_has_contradiction_single():
    """1 Score kann nicht widersprüchlich sein."""
    assert _has_contradiction([0.9]) is False


def test_contradiction_penalty_via_stddev():
    """MAI-14: Std-Dev>0.6 löst Penalty in compute_claim_confidence aus."""
    evidence = [
        {"source_id": "s1", "sentiment_score": 0.9},
        {"source_id": "s2", "sentiment_score": -0.8},
        {"source_id": "s3", "sentiment_score": 0.7},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    assert "contradiction_penalty" in penalties
    assert score <= 0.5


def test_contradiction_penalty_via_range():
    """MAI-14: min<-0.3 + max>+0.3 löst Penalty aus."""
    evidence = [
        {"source_id": "s1", "sentiment_score": 0.5},
        {"source_id": "s2", "sentiment_score": -0.5},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.6)
    assert "contradiction_penalty" in penalties


def test_no_penalty_when_aligned():
    """Konsistente Sentiments → keine Penalty."""
    evidence = [
        {"source_id": "s1", "sentiment_score": 0.4},
        {"source_id": "s2", "sentiment_score": 0.5},
        {"source_id": "s3", "sentiment_score": 0.6},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    assert "contradiction_penalty" not in penalties


def test_single_evidence_no_contradiction():
    """1 Item kann nicht widersprüchlich sein."""
    evidence = [{"source_id": "s1", "sentiment_score": 0.9}]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    assert "contradiction_penalty" not in penalties


def test_missing_sentiment_ignored():
    """Items ohne sentiment_score werden übersprungen, kein Crash."""
    evidence = [
        {"source_id": "s1"},  # kein sentiment_score
        {"source_id": "s2", "sentiment_score": 0.4},
    ]
    score, label, penalties = compute_claim_confidence(evidence, base_score=0.7)
    # Nur 1 valider Sentiment → kein Contradiction-Penalty
    assert "contradiction_penalty" not in penalties


def test_compute_confidence_auto_sentiment_penalty():
    """compute_confidence zieht Sentiment-Penalty automatisch ab."""
    evidence_clean = [
        {"type": "graph_fact", "source": "s1", "snippet": "x", "match_score": 0.7},
        {"type": "graph_fact", "source": "s2", "snippet": "y", "match_score": 0.7},
    ]
    evidence_contradicted = [
        {"type": "graph_fact", "source": "s1", "snippet": "x",
         "match_score": 0.7, "sentiment_score": 0.9},
        {"type": "graph_fact", "source": "s2", "snippet": "y",
         "match_score": 0.7, "sentiment_score": -0.8},
    ]
    score_clean, _ = compute_confidence(evidence_clean)
    score_penalized, _ = compute_confidence(evidence_contradicted)
    assert score_penalized < score_clean
