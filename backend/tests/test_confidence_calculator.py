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


def test_no_evidence_yields_low():
    # Sub-Slice 07: leere Evidence-Liste → ehrliches (0.15, "low")
    # statt 0.0 — der Guard in compute_confidence gibt einen Minimal-
    # Score zurück, damit Downstream-Code nicht auf 0.0 spezialisiert ist.
    score, label = compute_confidence([])
    assert score == 0.15
    assert label == "low"


def test_single_unmatched_graph_fact_yields_medium():
    """Ein einzelnes Graph-Fact ohne match_score → mittlere Confidence."""
    score, label = compute_confidence([
        {"type": "graph_fact", "source": "report_tool", "snippet": "x"},
    ])
    # source_quality 1.0, relevance 0.5, specificity 0.5, consistency 0.6
    # = 0.4*0.5 + 0.25*1.0 + 0.20*0.5 + 0.15*0.6 = 0.64 → medium
    assert label == "medium"
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


def test_high_score_without_strong_match_caps_at_high():
    """Ohne match_score-≥-0.85 wird verified geblockt; max 0.89 → high."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": f"x{i}", "match_score": 0.78}
        for i in range(5)
    ]
    score, label = compute_confidence(items)
    assert score <= 0.89
    assert label == "high"


def test_off_topic_low_match_score_yields_low_or_medium():
    """Niedrige match_scores drücken den Score in low/medium."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "x", "match_score": 0.20},
        {"type": "agent_action", "source": "simulation_actions",
         "snippet": "y", "match_score": 0.15},
    ]
    score, label = compute_confidence(items)
    assert label in ("low", "medium")
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
    items = [{"type": "graph_fact", "source": "x", "match_score": 0.9}]
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
