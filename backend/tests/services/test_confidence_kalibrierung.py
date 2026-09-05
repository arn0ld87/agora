"""Task 08 — Tests fuer Confidence-Kalibrierung + Contradiction-Penalty.

- match_score < 0.55 → Deckel auf medium (0.69)
- verified braucht >= 2 unabhaengige Quellen
- detect_contradiction_penalty: strukturierte Felder, keine Textanalyse
- #1301: Single-Source-Deckel differenziert ab match_score >= 0.85
"""

from __future__ import annotations

import pytest

from app.services.confidence_calculator import (
    compute_claim_confidence,
    compute_confidence,
)
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


def test_single_source_strong_match_reaches_at_least_medium():
    """#1301: ein SUPPORTED-Fakt mit match_score > 0.9 aus nur einer Quelle
    erreicht mindestens ``medium`` (Score >= 0.65).

    Vorher zog der bedingungslose 0.59-Deckel jeden Ein-Quellen-Claim auf
    "low", unabhaengig von der Belegqualitaet -- ein Attraktor statt eines
    Grenzfall-Schutzes. Im AURORA-Referenzlauf landeten so 27 von 28 Claims
    exakt bei 0.59.
    """
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "x", "match_score": 0.946},
    ]
    score, label = compute_confidence(items)
    assert score >= 0.65
    assert label not in ("speculative", "low")


def test_single_source_never_reaches_verified_even_with_perfect_match():
    """Leitplanke #1301: ein Ein-Quellen-Claim darf trotz Lockerung nie
    ``verified`` erreichen -- die Verified-Schranke (unique_sources >= 2)
    bleibt unangetastet, auch bei match_score == 1.0."""
    items = [
        {"type": "graph_fact", "source": "panorama_search",
         "snippet": "x", "match_score": 1.0},
    ]
    score, label = compute_confidence(items)
    assert label != "verified"
    assert score <= 0.89


@pytest.mark.parametrize(
    "match_score, n_sources, expected_labels, score_bound, bound_is_max",
    [
        # Unterhalb der Strong-Match-Schwelle (0.85): Deckel greift weiterhin.
        (0.78, 1, ("low",), 0.59, True),
        (0.84, 1, ("low",), 0.59, True),
        # Ab 0.85 (Verified-Schranken-Schwelle, wiederverwendet statt einer
        # neuen Skala) hebt sich der Deckel -- Rohscore zaehlt wieder.
        (0.85, 1, ("medium", "high"), 0.59, False),
        (0.946, 1, ("medium", "high"), 0.65, False),
        # Zwei unabhaengige Quellen: Deckel betrifft das gar nicht erst,
        # unveraendertes Bestandsverhalten.
        (0.946, 2, ("verified",), 0.90, False),
    ],
)
def test_match_score_and_source_count_bands(
    match_score, n_sources, expected_labels, score_bound, bound_is_max
):
    """#1301: Matrix aus Match-Score x Quellenzahl -> erwartete Confidence-Baender,
    insbesondere die neue 0.85-Grenze des Single-Source-Deckels."""
    items = [
        {"type": "graph_fact", "source": f"source_{i}",
         "snippet": f"x{i}", "match_score": match_score}
        for i in range(n_sources)
    ]
    score, label = compute_confidence(items)
    assert label in expected_labels
    if bound_is_max:
        assert score <= score_bound
    else:
        assert score >= score_bound


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


_GEBUNDENER_WIDERSPRUCH = [
    {"snippet": "NRW KIDM beschlossen", "match_score": 0.9,
     "supports_claim": True, "entailment": "SUPPORTED"},
    {"snippet": "NRW Curriculum verabschiedet", "match_score": 0.8,
     "supports_claim": True, "entailment": "SUPPORTED"},
    {"snippet": "NRW KIDM widerlegt", "match_score": 0.7,
     "supports_claim": False, "contradicts_claim": True,
     "entailment": "CONTRADICTED"},
]


def test_binder_belastet_gebundenen_widerspruch_nicht_ein_zweites_mal():
    """#1327: der Binder darf einen CONTRADICTED-Beleg nicht selbst bestrafen.

    ``bind_evidence_to_claim`` setzt ``contradicts_claim`` nur bei
    CONTRADICTED, was ``supports_claim=False`` erzwingt. Dasselbe Item wird
    von ``partition_by_entailment`` bereits als ``contradicting`` gezaehlt und
    im Rechner mit 0.2 belastet. Wuerde ``detect_contradiction_penalty`` es
    zusaetzlich mit 0.15 belasten, waere derselbe Widerspruch doppelt
    bestraft — ``report_agent/agent.py`` reicht dieses Ergebnis als
    ``contradiction_penalty`` in genau jenen Rechner.
    """
    assert detect_contradiction_penalty(_GEBUNDENER_WIDERSPRUCH) == 0.0


def test_entailment_pfad_bestraft_den_gebundenen_widerspruch_tatsaechlich():
    """Gegenstueck: die Strafe fehlt nicht, sie sitzt nur woanders.

    Ohne diesen Test liesse sich der Test darueber auch dadurch erfuellen,
    dass der Widerspruch gar keine Wirkung mehr haette.
    """
    ohne_widerspruch = _GEBUNDENER_WIDERSPRUCH[:2]

    _score_mit, _label_mit, penalties_mit = compute_claim_confidence(
        _GEBUNDENER_WIDERSPRUCH
    )
    score_ohne, _label_ohne, penalties_ohne = compute_claim_confidence(
        ohne_widerspruch
    )

    assert "entailment_contradiction_penalty" in penalties_mit
    assert "entailment_contradiction_penalty" not in penalties_ohne
    assert _score_mit < score_ohne, (
        "Der gebundene Widerspruch muss die Confidence senken — nur eben "
        "ueber den Entailment-Pfad, nicht ueber den Binder"
    )


def test_stuetzendes_item_mit_fremdem_widerspruchs_flag_wird_bestraft():
    """Was Regel 1 weiterhin abdeckt: ein Flag, das der Entailment-Pfad nicht kennt.

    ``partition_by_entailment`` prueft nur ``entailment == CONTRADICTED`` und
    ``contradicts_claim``. Ein stuetzendes Item, das aus einer anderen Quelle
    ``is_contradiction`` traegt, bleibt damit Sache des Binders.
    """
    items = [
        {"snippet": "NRW KIDM beschlossen", "match_score": 0.9,
         "supports_claim": True},
        {"snippet": "NRW Curriculum verabschiedet", "match_score": 0.8,
         "supports_claim": True, "is_contradiction": True},
    ]
    assert detect_contradiction_penalty(items) > 0.0


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
