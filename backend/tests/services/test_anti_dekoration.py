"""Anti-Dekorations-Tests für Sub-Slice 07.

Prüft:
1. compute_confidence([]) → (0.15, "speculative") — kein dekorativer Score
2. Orphan-Claim (leere bound + leere direct_items) → speculative-Confidence + Audit-Entry
3. Nichtleere global_items schmieren NICHT in evidence_items durch

Refs #105, Layer 1.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

from app.services.confidence_calculator import compute_confidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(monkeypatch) -> object:
    """Minimaler ReportAgent ohne lebenden Storage — analog zu test_report_agent_contracts.py."""
    from app.services.report_agent import ReportAgent

    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_test"
    agent.simulation_id = "sim_test"
    agent.simulation_requirement = "Testreq"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = None
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None
    return agent


def _sample_global_item(idx: int = 0) -> Dict[str, Any]:
    return {
        "type": "graph_metric",
        "source": "simulation_metrics",
        "snippet": f"echo_chamber_index: 0.{40 + idx}",
        "match_score": 0.75,
        "supports_claim": True,
    }


# ---------------------------------------------------------------------------
# Test 1 — compute_confidence mit leerer Liste → (0.15, "speculative")
# ---------------------------------------------------------------------------

def test_compute_confidence_empty_returns_speculative() -> None:
    """Kein Evidence → ehrliches (0.15, 'speculative'), kein dekorativer Score."""
    score, label = compute_confidence([])
    assert label == "speculative", f"Erwartetes Label 'speculative', bekam '{label}'"
    assert score == 0.15, f"Erwarteter Score 0.15, bekam {score}"


# ---------------------------------------------------------------------------
# Test 2 — Orphan-Claim: bound==[], direct_items==[] → speculative + Audit-Entry
# ---------------------------------------------------------------------------

def test_orphan_claim_gets_speculative_confidence(monkeypatch) -> None:
    """Wenn Embedder läuft aber nichts bindet (bound==[]) und kein direktes
    Evidence vorhanden ist, muss der Claim confidence_label=='low' erhalten
    und der audit_trail einen 'no_direct_evidence_bound'-Eintrag enthalten.
    """
    from app.services.report_agent import ReportAgent

    agent = _make_agent(monkeypatch)
    # Globales Evidence vorhanden, aber leere section-Evidence
    agent.evidence_map = {
        "global_evidence": [_sample_global_item(0), _sample_global_item(1)],
    }
    agent._active_section_evidence = []  # kein direktes Evidence

    # Embedder liefert leeres bound-Ergebnis
    empty_bound: List[Dict] = []
    monkeypatch.setattr(
        "app.services.report_agent.agent.bind_evidence_to_claim",
        lambda *args, **kwargs: empty_bound,
    )
    # _try_get_embedder gibt einen Dummy zurück (nicht None → embedder_ok-Pfad)
    monkeypatch.setattr(
        ReportAgent,
        "_try_get_embedder",
        lambda self: lambda text: [0.1, 0.2, 0.3],
    )

    claims = agent._build_claims_for_section(
        "Die Netzwerk-Segmentierung zeigt eine Polarisierung von 72 %."
    )

    assert claims, "Es muss mindestens einen Claim geben"
    claim = claims[0]
    assert claim["confidence_label"] == "speculative", (
        f"Erwartet 'speculative', bekam '{claim['confidence_label']}'"
    )
    assert claim["confidence_score"] < 0.3, (
        f"Score sollte < 0.3 sein, bekam {claim['confidence_score']}"
    )
    audit_entries = claim.get("audit_trail", [])
    snippets = [e.get("snippet") for e in audit_entries]
    assert "no_direct_evidence_bound" in snippets, (
        f"Kein 'no_direct_evidence_bound'-Eintrag in audit_trail: {snippets}"
    )


# ---------------------------------------------------------------------------
# Test 3 — global_items schlagen NICHT mehr als evidence_items durch
# ---------------------------------------------------------------------------

def test_no_global_items_decoration(monkeypatch) -> None:
    """global_items dürfen nach dem [:2]-Entfernen nicht in evidence_items landen,
    wenn bound==[] und direct_items==[].
    """
    from app.services.report_agent import ReportAgent

    agent = _make_agent(monkeypatch)
    global_item_snippet = "GLOBAL_SENTINEL_SNIPPET"
    agent.evidence_map = {
        "global_evidence": [
            {
                "type": "graph_metric",
                "source": "simulation_metrics",
                "snippet": global_item_snippet,
                "match_score": 0.9,
                "supports_claim": True,
            }
        ],
    }
    agent._active_section_evidence = []

    empty_bound: List[Dict] = []
    monkeypatch.setattr(
        "app.services.report_agent.agent.bind_evidence_to_claim",
        lambda *args, **kwargs: empty_bound,
    )
    monkeypatch.setattr(
        ReportAgent,
        "_try_get_embedder",
        lambda self: lambda text: [0.1, 0.2, 0.3],
    )

    claims = agent._build_claims_for_section(
        "Die Netzwerk-Segmentierung zeigt eine Polarisierung von 72 %."
    )

    assert claims, "Es muss mindestens einen Claim geben"
    for claim in claims:
        evidence_snippets = [e.get("snippet", "") for e in claim.get("evidence", [])]
        assert global_item_snippet not in evidence_snippets, (
            f"Global-Item-Snippet '{global_item_snippet}' darf nicht in evidence_items sein; "
            f"evidence: {claim.get('evidence')}"
        )
