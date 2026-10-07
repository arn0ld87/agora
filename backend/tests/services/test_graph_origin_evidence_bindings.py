"""#1808: Herkunft am Record, Match und Entailment am v3-Claim-Binding."""

from copy import deepcopy

import pytest

from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import (
    auto_downgrade_unsupported_high_claims,
    init_evidence_map,
    normalize_sections_for_contract,
    register_evidence_record,
)


def _agent_and_claim(label: str, strong_quote: bool):
    agent = ReportAgent.__new__(ReportAgent)
    agent.evidence_map = init_evidence_map(
        report_id="report-test", simulation_id="sim-test", global_evidence=[]
    )
    bindings = []
    for position, group in enumerate(("Buerger", "Verwaltung", None)):
        manual = group is None
        item = {
            "producer_key": f"graph:{position}" if manual else f"interview:{group}",
            "type": "graph_fact" if manual else "agent_interview",
            "source": "report_tool",
            "source_kind": "graph_relation" if manual else "agent_quote",
            "snippet": "Die Reform braucht eine verbindliche Entlastungsregelung.",
        }
        if manual:
            item["graph_origin"] = "edited"
        else:
            assert group is not None
            item.update(
                quote=item["snippet"],
                persona_stakeholder_group=group,
                voice_key=f"agent:{position}",
            )
        record = register_evidence_record(agent.evidence_map, item, scope_id="test")
        assert record is not None and "match_score" not in record
        bindings.append(
            {
                "evidence_id": record["evidence_id"],
                "supports_claim": True,
                "entailment": "SUPPORTED",
                "match_score": 0.95 if manual or (strong_quote and position == 0) else 0.7,
            }
        )
    claim = {
        "claim_id": "claim_01",
        "claim_text": "Die Reform braucht eine verbindliche Entlastungsregelung.",
        "confidence_label": label,
        "confidence_score": 0.93,
        "evidence": bindings,
    }
    return agent, claim


@pytest.mark.parametrize(
    ("label", "strong_quote", "expected"),
    [("high", False, "high"), ("verified", False, "high"), ("verified", True, "verified")],
)
def test_v3_normalization_uses_record_origin_and_binding_scores(label, strong_quote, expected):
    agent, claim = _agent_and_claim(label, strong_quote)
    original = deepcopy(claim)
    (result,) = auto_downgrade_unsupported_high_claims(
        [claim], evidence_index=agent.evidence_map["evidence_index"]
    )
    assert result["confidence_label"] == expected
    assert result["evidence"] == original["evidence"]
    assert claim == original
    assert ("audit_trail" in result) == (label != expected)


@pytest.mark.parametrize("strong_quote", [False, True])
def test_finalization_and_section_normalization_keep_independently_met_label(strong_quote):
    agent, claim = _agent_and_claim("verified", strong_quote)
    expected = "verified" if strong_quote else "high"
    claims, hypotheses, gaps, _decisions = agent._finalize_section_claims([claim])
    assert not hypotheses and not gaps
    assert claims[0]["confidence_label"] == expected
    sections = normalize_sections_for_contract(
        [{"section_index": 1, "section_title": "Reform", "claims": claims}],
        evidence_index=agent.evidence_map["evidence_index"],
    )
    assert sections[0]["claims"][0]["confidence_label"] == expected


def _agent_and_hand_work_only_claim(origin: str):
    """Ein Claim, dessen einziger stuetzender Beleg Handarbeit im Graphen ist."""
    agent, claim = _agent_and_claim("high", strong_quote=False)
    manual_id = claim["evidence"][-1]["evidence_id"]
    agent.evidence_map["evidence_index"][manual_id]["graph_origin"] = origin
    claim["evidence"] = [
        binding for binding in claim["evidence"] if binding["evidence_id"] == manual_id
    ]
    return agent, claim


@pytest.mark.parametrize("origin", ["manual", "edited"])
def test_claim_with_only_hand_work_support_is_a_hypothesis(origin):
    """Handarbeit zaehlt fuer keine Confidence-Stufe, also auch fuer keinen Claim.

    Haelt sie den Claim in ``claims[]``, stuenden im Bericht ein Label, ein
    ``confidence_scope`` und eine ``aggregation_basis``, die ausschliesslich auf
    einem Handeintrag ohne Dokumentstelle beruhen. Das ist die vorgetaeuschte
    Pruefbarkeit, die ADR-0013/ADR-0022 ausschliessen.
    """
    agent, claim = _agent_and_hand_work_only_claim(origin)

    claims, hypotheses, _gaps, _decisions = agent._finalize_section_claims([claim])

    assert claims == []
    assert len(hypotheses) == 1
    assert hypotheses[0]["hypothesis_text"] == claim["claim_text"]


@pytest.mark.parametrize("origin", ["manual", "edited"])
def test_one_simulated_support_beside_hand_work_keeps_the_claim(origin):
    """Gegenprobe: Handarbeit nimmt einem belegten Claim nichts weg."""
    agent, claim = _agent_and_claim("high", strong_quote=False)
    manual_id = claim["evidence"][-1]["evidence_id"]
    agent.evidence_map["evidence_index"][manual_id]["graph_origin"] = origin

    claims, hypotheses, _gaps, _decisions = agent._finalize_section_claims([claim])

    assert not hypotheses
    assert claims and claims[0]["confidence_label"] in ("high", "verified")


@pytest.mark.parametrize("origin", ["manual", "edited"])
def test_claim_builder_excludes_hand_work_from_external_penalty(monkeypatch, origin):
    import app.services.report_agent.agent as agent_module

    agent, claim = _agent_and_claim("high", False)
    index = agent.evidence_map["evidence_index"]
    manual_id = claim["evidence"][-1]["evidence_id"]
    index[manual_id]["graph_origin"] = origin
    agent._active_section_evidence = list(index.values())
    agent._active_section_unresolved_evidence = []
    agent._current_section_index = 1
    monkeypatch.setattr(ReportAgent, "_try_get_embedder", lambda self: lambda text: [1.0])
    monkeypatch.setattr(ReportAgent, "_try_get_entailment_judge", lambda self: None)
    monkeypatch.setattr(
        agent_module, "bind_evidence_to_claim", lambda *args, **kwargs: claim["evidence"]
    )
    seen = []

    def penalty(evidence):
        seen.extend(evidence)
        return 0.15 if any(item.get("graph_origin") for item in evidence) else 0.0

    monkeypatch.setattr(agent_module, "detect_contradiction_penalty", penalty)
    claims = agent._build_claims_for_section(claim["claim_text"])
    assert len(seen) == 2
    assert all(not item.get("graph_origin") for item in seen)
    assert claims[0]["evidence"] == claim["evidence"]
    assert not any(
        item.get("type") == "contradiction_penalty_applied" for item in claims[0]["audit_trail"]
    )
