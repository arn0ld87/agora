"""S6 — Tests für die Confidence-Formel.

Reviewer hatte gefordert: Score muss kalibriert sein, `verified` darf
nur bei direkter Evidence vergeben werden. Diese Tests fixieren die
wichtigsten Eckpunkte der Formel.
"""

from __future__ import annotations

from app.services.confidence_calculator import compute_confidence


def test_no_evidence_yields_low():
    score, label = compute_confidence([])
    assert score == 0.0
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
