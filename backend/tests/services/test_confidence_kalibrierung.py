"""Task 08 — Tests fuer Confidence-Kalibrierung + Contradiction-Penalty.

- match_score < 0.55 → Deckel auf medium (0.69)
- verified braucht >= 2 unabhaengige Quellen
- detect_contradiction_penalty: strukturierte Felder, keine Textanalyse
"""

from __future__ import annotations

from app.services.confidence_calculator import compute_confidence
from app.services.evidence_binder import detect_contradiction_penalty


# ── Confidence-Kalibrierung ──────────────────────────────────────────

def test_weak_matches_cap_at_low():
    """Alle match_scores < 0.55 → max 0.64 (Grenze low/medium), nie medium/high/verified."""
    items = [
        {"type": "graph_fact", "source": "a", "snippet": "x",
         "match_score": 0.52},
        {"type": "graph_metric", "source": "b", "snippet": "y",
         "match_score": 0.48},
        {"type": "relationship_chain", "source": "c", "snippet": "z",
         "match_score": 0.51},
    ]
    score, label = compute_confidence(items)
    assert score <= 0.64
    assert label in ("speculative", "low")


def test_single_strong_match_but_only_one_source_no_verified():
    """Ein starkes Match reicht nicht — es braucht >= 2 unabhaengige Quellen
    fuer verified."""
    items = [
        {"type": "graph_fact", "source": "only_source",
         "snippet": "x", "match_score": 0.92},
        {"type": "graph_fact", "source": "only_source",
         "snippet": "y", "match_score": 0.88},
    ]
    score, label = compute_confidence(items)
    assert score <= 0.89
    assert label != "verified"


def test_two_sources_plus_strong_match_unlocks_verified():
    """2+ unabhaengige Quellen + top match >= 0.85 → verified."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "x", "match_score": 0.92},
        {"type": "entity_summary", "source": "graph_tools",
         "snippet": "y", "match_score": 0.86},
    ]
    score, label = compute_confidence(items)
    assert score >= 0.90
    assert label == "verified"


def test_one_strong_one_weak_source_capped():
    """Zwei Quellen aber max match < 0.55 → Cap auf 0.64 greift vor verified."""
    items = [
        {"type": "graph_fact", "source": "a", "snippet": "x",
         "match_score": 0.30},
        {"type": "agent_action", "source": "b", "snippet": "y",
         "match_score": 0.35},
    ]
    score, label = compute_confidence(items)
    assert score <= 0.64
    assert label in ("speculative", "low")


# ── Contradiction-Penalty (strukturiert, keine Textanalyse) ──────────

def test_no_penalty_for_single_item():
    assert detect_contradiction_penalty([]) == 0.0
    assert detect_contradiction_penalty(
        [{"snippet": "ein Item", "match_score": 0.8,
          "supports_claim": True}]
    ) == 0.0


def test_no_penalty_for_unsupporting_items():
    """Items ohne supports_claim=True werden ignoriert."""
    items = [
        {"snippet": "x", "contradicts_claim": True},
        {"snippet": "y", "contradicts_claim": True},
    ]
    assert detect_contradiction_penalty(items) == 0.0


def test_boolean_contradiction_flag_adds_penalty():
    """contradicts_claim=True bei supports_claim=True → +0.15."""
    items = [
        {"snippet": "NRW beschloss KIDM", "match_score": 0.8,
         "supports_claim": True, "contradicts_claim": True},
        {"snippet": "NRW Curriculum verabschiedet", "match_score": 0.7,
         "supports_claim": True},
    ]
    penalty = detect_contradiction_penalty(items)
    assert penalty == 0.15


def test_is_contradiction_flag_adds_penalty():
    items = [
        {"snippet": "x", "match_score": 0.6,
         "supports_claim": True, "is_contradiction": True},
        {"snippet": "y", "match_score": 0.6,
         "supports_claim": True},
    ]
    assert detect_contradiction_penalty(items) == 0.15


def test_contradiction_flag_adds_penalty():
    items = [
        {"snippet": "x", "match_score": 0.6,
         "supports_claim": True, "contradiction": True},
        {"snippet": "y", "match_score": 0.6,
         "supports_claim": True},
    ]
    assert detect_contradiction_penalty(items) == 0.15


def test_multiple_boolean_flags_add_up():
    """Pro Item mit Flag +0.15, nicht pro Flag. Zwei Items mit Flag = 0.30."""
    items = [
        {"snippet": "x", "match_score": 0.8,
         "supports_claim": True,
         "contradicts_claim": True, "is_contradiction": True},
        {"snippet": "y", "match_score": 0.7,
         "supports_claim": True, "contradiction": True},
    ]
    penalty = detect_contradiction_penalty(items)
    assert penalty == 0.3  # 2 Items × 0.15


def test_stance_conflict_support_vs_oppose():
    items = [
        {"snippet": "NRW KIDM super", "match_score": 0.8,
         "supports_claim": True, "stance": "support"},
        {"snippet": "NRW KIDM schlecht", "match_score": 0.7,
         "supports_claim": True, "stance": "oppose"},
    ]
    penalty = detect_contradiction_penalty(items)
    assert penalty == 0.15


def test_stance_conflict_pro_vs_contra():
    items = [
        {"snippet": "pro KIDM", "match_score": 0.8,
         "supports_claim": True, "stance": "pro"},
        {"snippet": "contra KIDM", "match_score": 0.7,
         "supports_claim": True, "stance": "contra"},
    ]
    assert detect_contradiction_penalty(items) == 0.15


def test_stance_conflict_positive_vs_negative():
    items = [
        {"snippet": "positive", "match_score": 0.8,
         "supports_claim": True, "stance": "positive"},
        {"snippet": "negative", "match_score": 0.7,
         "supports_claim": True, "stance": "negative"},
    ]
    assert detect_contradiction_penalty(items) == 0.15


def test_same_stance_no_penalty():
    items = [
        {"snippet": "x", "match_score": 0.8,
         "supports_claim": True, "stance": "support"},
        {"snippet": "y", "match_score": 0.7,
         "supports_claim": True, "stance": "support"},
    ]
    assert detect_contradiction_penalty(items) == 0.0


def test_penalty_capped_at_max():
    """Auch extreme Kombination bleibt unter max_penalty (0.5)."""
    items = [
        {"snippet": f"item{i}", "match_score": 0.8,
         "supports_claim": True,
         "contradicts_claim": True, "is_contradiction": True,
         "contradiction": True, "stance": "support"}
        for i in range(5)
    ]
    # + Stance (oppose gegen support aus item 0) = viele Treffer
    items.append(
        {"snippet": "opp", "match_score": 0.8,
         "supports_claim": True, "stance": "oppose"}
    )
    penalty = detect_contradiction_penalty(items)
    assert penalty <= 0.5


def test_contradiction_penalty_integrated_with_confidence():
    """Penalty aus detect_contradiction fliesst in compute_confidence ein."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "NRW KIDM beschlossen", "match_score": 0.92,
         "supports_claim": True, "contradicts_claim": True},
        {"type": "entity_summary", "source": "graph_tools",
         "snippet": "NRW KIDM umstritten", "match_score": 0.76,
         "supports_claim": True},
    ]
    penalty = detect_contradiction_penalty(items)
    assert penalty > 0.0
    base_score, _ = compute_confidence(items)
    penalized_score, _ = compute_confidence(items, contradiction_penalty=penalty)
    assert penalized_score < base_score
