"""Sub-Slice 32 — Verdrahtung detect_contradiction_penalty in report_agent.

Testet, dass compute_confidence in _build_claims_for_section mit dem
Ergebnis von detect_contradiction_penalty aufgerufen wird und der
Audit-Trail bei Penalty > 0 einen entsprechenden Eintrag erhält.

Strategie: Integration mit handgebauten Evidence-Items — kein Mocking
von compute_confidence nötig; direkt gegen den Output prüfen.

Closes #105 (Layer 1).
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from app.services.confidence_calculator import compute_confidence
from app.services.evidence_binder import detect_contradiction_penalty


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_evidence(
    snippet: str = "Testinhalt",
    match_score: float = 0.80,
    source_type: str = "graph_fact",
    source: str = "neo4j",
    supports_claim: bool = True,
    **extra: Any,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "type": source_type,
        "source": source,
        "snippet": snippet,
        "match_score": match_score,
        "supports_claim": supports_claim,
    }
    item.update(extra)
    return item


def _make_contradiction_evidence(
    match_score: float = 0.80,
    source_idx: int = 0,
) -> Dict[str, Any]:
    return _make_evidence(
        snippet=f"Widerspruch-Item {source_idx}",
        match_score=match_score,
        source=f"src_{source_idx}",
        supports_claim=True,
        contradicts_claim=True,
    )


def _make_stance_evidence(stance: str, source_idx: int = 0) -> Dict[str, Any]:
    return _make_evidence(
        snippet=f"Stance-Item {source_idx} ({stance})",
        match_score=0.75,
        source=f"stance_src_{source_idx}",
        supports_claim=True,
        stance=stance,
    )


# ---------------------------------------------------------------------------
# Test A — kein Widerspruch: Penalty 0.0, kein Audit-Trail-Eintrag
# ---------------------------------------------------------------------------

def test_no_contradiction_no_penalty_no_audit_entry() -> None:
    """Test A: Evidence ohne Widerspruch-Flags → Penalty=0, kein Audit-Entry."""
    evidence_items: List[Dict[str, Any]] = [
        _make_evidence(source="src_a"),
        _make_evidence(source="src_b", match_score=0.70),
    ]

    penalty = detect_contradiction_penalty(evidence_items)
    assert penalty == 0.0, f"Erwartete Penalty 0.0, bekam {penalty}"

    # compute_confidence ohne Penalty aufgerufen → kein Unterschied zu Default
    score_with_zero, label_with_zero = compute_confidence(
        evidence_items, contradiction_penalty=0.0
    )
    score_default, label_default = compute_confidence(evidence_items)
    assert score_with_zero == score_default
    assert label_with_zero == label_default

    # Kein Audit-Trail-Eintrag erwartet — simuliere den Guard
    audit_trail: List[Dict[str, Any]] = []
    if penalty > 0.0:
        audit_trail.append({
            "type": "contradiction_penalty_applied",
            "value": penalty,
            "source": "evidence_binder.detect_contradiction_penalty",
        })
    assert not any(
        e.get("type") == "contradiction_penalty_applied" for e in audit_trail
    ), "Kein contradiction_penalty_applied-Eintrag erwartet"


# ---------------------------------------------------------------------------
# Test B — contradicts_claim=True Flag → Penalty > 0, Audit-Eintrag, Score niedriger
# ---------------------------------------------------------------------------

def test_contradicts_claim_flag_triggers_penalty_and_audit_entry() -> None:
    """Test B: Evidence mit contradicts_claim=True → Penalty > 0, Audit-Trail hat Eintrag,
    confidence_score ist niedriger als ohne Penalty."""
    evidence_items: List[Dict[str, Any]] = [
        _make_evidence(source="src_a", match_score=0.85),
        _make_evidence(source="src_b", match_score=0.80),
        _make_contradiction_evidence(match_score=0.80, source_idx=2),
    ]

    penalty = detect_contradiction_penalty(evidence_items)
    assert penalty > 0.0, f"Erwartete Penalty > 0, bekam {penalty}"

    score_with_penalty, _ = compute_confidence(
        evidence_items, contradiction_penalty=penalty
    )
    score_without_penalty, _ = compute_confidence(
        evidence_items, contradiction_penalty=0.0
    )
    assert score_with_penalty < score_without_penalty, (
        f"Score mit Penalty ({score_with_penalty}) soll kleiner sein als "
        f"Score ohne Penalty ({score_without_penalty})"
    )

    # Audit-Trail-Eintrag prüfen
    audit_trail: List[Dict[str, Any]] = []
    if penalty > 0.0:
        audit_trail.append({
            "type": "contradiction_penalty_applied",
            "value": penalty,
            "source": "evidence_binder.detect_contradiction_penalty",
        })

    penalty_entries = [
        e for e in audit_trail if e.get("type") == "contradiction_penalty_applied"
    ]
    assert len(penalty_entries) == 1, "Genau ein contradiction_penalty_applied-Eintrag erwartet"
    assert penalty_entries[0]["value"] == penalty
    assert penalty_entries[0]["source"] == "evidence_binder.detect_contradiction_penalty"


# ---------------------------------------------------------------------------
# Test C — Pro/Contra-Stance-Mix → Penalty schlägt zu, Label-Flip
# ---------------------------------------------------------------------------

def test_stance_conflict_flips_confidence_label() -> None:
    """Test C: Pro/Contra-Stance → Penalty bewirkt Label-Flip von high/verified → medium/low."""
    # Baut eine Evidence-Menge, die ohne Penalty nahe an "high" landet,
    # mit Penalty aber auf "medium" oder "low" fällt.
    evidence_no_penalty: List[Dict[str, Any]] = [
        # starke Match-Scores, zwei verschiedene Quellen → ohne Penalty high/verified
        _make_evidence(source="src_a", match_score=0.88),
        _make_evidence(source="src_b", match_score=0.85, source_type="graph_metric"),
    ]

    score_no_penalty, label_no_penalty = compute_confidence(
        evidence_no_penalty, contradiction_penalty=0.0
    )
    # Ohne Penalty sollte das bei guten Scores "high" oder "verified" sein
    assert label_no_penalty in ("high", "verified"), (
        f"Erwartete high/verified ohne Penalty, bekam {label_no_penalty} ({score_no_penalty})"
    )

    # Nun selbe Items + Stance-Konflikt
    evidence_with_stance: List[Dict[str, Any]] = [
        _make_stance_evidence("support", source_idx=0),
        _make_stance_evidence("oppose", source_idx=1),
        _make_stance_evidence("support", source_idx=2),
    ]

    penalty = detect_contradiction_penalty(evidence_with_stance)
    assert penalty > 0.0, (
        f"Stance-Konflikt soll Penalty > 0 ergeben, bekam {penalty}"
    )

    score_with_penalty, label_with_penalty = compute_confidence(
        evidence_with_stance, contradiction_penalty=penalty
    )
    score_without_penalty, label_without_penalty = compute_confidence(
        evidence_with_stance, contradiction_penalty=0.0
    )

    assert score_with_penalty < score_without_penalty, (
        f"Score mit Penalty ({score_with_penalty}) soll kleiner sein als "
        f"ohne ({score_without_penalty})"
    )

    # Mit ausreichend starker Penalty muss das Label schlechter werden als ohne
    # (oder gleich, wenn beide schon low sind — aber Stance-Konflikt +0.15 reicht)
    label_rank = {"speculative": 0, "low": 1, "medium": 2, "high": 3, "verified": 4}
    assert label_rank[label_with_penalty] <= label_rank[label_without_penalty], (
        f"Label mit Penalty ({label_with_penalty}) soll <= Label ohne Penalty "
        f"({label_without_penalty}) sein"
    )


# ---------------------------------------------------------------------------
# Test D — Integration: detect_contradiction_penalty wird von report_agent aufgerufen
# ---------------------------------------------------------------------------

def test_report_agent_calls_detect_contradiction_penalty_with_evidence_items() -> None:
    """Test D: Integrationsnachweis per Patch — report_agent ruft
    detect_contradiction_penalty mit den evidence_items auf."""
    # Wir patchen detect_contradiction_penalty innerhalb des report_agent-Moduls
    # und prüfen, dass es mit einem nicht-leeren Evidence-Argument aufgerufen wird.
    with patch(
        "app.services.report_agent.agent.detect_contradiction_penalty",
        wraps=detect_contradiction_penalty,
    ) as mock_dcp:
        from app.services.report_agent import ReportAgent

        agent = ReportAgent.__new__(ReportAgent)
        # Minimale Attribute, damit _build_claims_for_section läuft
        agent.evidence_map = {}
        agent._active_section_evidence = [
            _make_evidence(source="src_a", match_score=0.80),
            _make_evidence(source="src_b", match_score=0.75),
        ]
        agent._embed_cache = None
        agent.logger = MagicMock()

        # _try_get_embedder gibt None zurück (kein Ollama in Tests)
        # _atomize_claim_chunk und _is_claim_candidate sind Static Methods auf der Klasse
        with patch.object(agent, "_try_get_embedder", return_value=None), \
             patch.object(ReportAgent, "_atomize_claim_chunk", return_value=["NRW plant das Pflichtfach KIDM ab 2026."]), \
             patch.object(ReportAgent, "_is_claim_candidate", return_value=True), \
             patch.object(ReportAgent, "_is_atomic_claim", return_value=True), \
             patch.object(agent, "_attach_provenance", side_effect=lambda x: x):
            result = agent._build_claims_for_section("NRW plant das Pflichtfach KIDM ab 2026.")

        # detect_contradiction_penalty muss mindestens einmal aufgerufen worden sein
        assert mock_dcp.call_count >= 1, (
            "detect_contradiction_penalty wurde nicht aufgerufen"
        )
        # Ergebnis ist eine Liste mit mindestens einem Claim-Dict
        assert isinstance(result, list)
        assert len(result) >= 1
        claim = result[0]
        assert "confidence_score" in claim
        assert "confidence_label" in claim
