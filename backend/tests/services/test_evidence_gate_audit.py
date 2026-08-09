"""Regressionstests für den auditierbaren Evidence-Gate-Trail (Slice 7).

Der Referenzlauf report_06f654800817 entfernte 17 Fließtext-Aussagen und
routete sämtliche Claims in Hypothesen — auditierbar war davon nichts.
Diese Tests fixieren, dass jede Gate-Entscheidung (Reviewer-Floor,
fehlende Supporting-Evidence, Fließtext-Entfernung) als
``EvidenceDegradationModel``-Eintrag im ``gate_decision_log`` landet —
getrennt vom ``degradation_log``, der über ``apply_degradation_downgrade``
den Report-Status abstuft und deshalb regulärem Gate-Routing vorbehalten
bleiben darf (Codex-Review PR #1151, P1).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.contracts.report_v3 import CLAIM_MIN_EVIDENCE_FOR_CLAIM
from app.services.report_agent import ReportAgent
from app.services.report_agent.markdown_renderer import render_evidence_status
from app.services.report_agent.schemas import SectionKeyTakeaway

_EV_ID = "ev_" + "1" * 32


def test_unsupported_claim_routing_writes_gate_decision():
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Alle acht Agenten lehnen den Hard Cutover ab.",
        "evidence": [],
        "confidence_score": 0.2,
        "confidence_label": "low",
    }]

    finalized, hypotheses, _gaps, decisions = agent._finalize_section_claims(claims)

    assert finalized == []
    assert len(hypotheses) == 1
    assert len(decisions) == 1
    assert decisions[0]["claim_id"] == "claim_01"
    assert decisions[0]["violation"] == "no_supporting_evidence"
    assert decisions[0]["action"] == "moved_to_hypotheses"


def test_reviewer_floor_routing_writes_gate_decision():
    assert CLAIM_MIN_EVIDENCE_FOR_CLAIM >= 2, "Test setzt Reviewer-Floor >= 2 voraus."
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_07",
        "claim_text": "Die Migration braucht eine kontrollierte Übergangsphase.",
        "evidence": [{"evidence_id": _EV_ID, "supports_claim": True}],
        "confidence_score": 0.6,
        "confidence_label": "low",
    }]

    finalized, hypotheses, _gaps, decisions = agent._finalize_section_claims(claims)

    assert finalized == []
    assert len(hypotheses) == 1
    assert decisions[0]["claim_id"] == "claim_07"
    assert decisions[0]["violation"] == "reviewer_floor_insufficient_evidence"
    assert decisions[0]["action"] == "moved_to_hypotheses"


def test_prose_removal_logged_in_degradation_log():
    stub = ReportAgent.__new__(ReportAgent)
    stub.evidence_map = {
        "schema_version": 3,
        "report_id": "r1",
        "simulation_id": "sim1",
        "evidence_index": {},
        "global_evidence_refs": [],
        "sections": [],
    }
    stub._pending_prose_hypotheses = {2: [{
        "hypothesis_id": "hypothesis_99",
        "hypothesis_text": "Der Traffic wächst derzeit um rund 20 Prozent pro Monat.",
        "rationale": "Aus dem Fließtext entfernt: keine deckende Quelle gefunden.",
        "suggested_evidence": [],
    }]}
    stub._pending_section_metadata = {}
    stub._build_claims_for_section = lambda content: []
    stub._finalize_section_claims = lambda raw: ([], [], [], [])
    stub._section_dedup_check = lambda **kwargs: None

    with patch("app.services.report_agent.ReportManager.save_evidence_map"):
        stub._save_evidence_section(
            "r1", 2, "Unsicherheiten",
            "Ein ausreichend langer Abschnittstext ohne Fallback-Marker.",
        )

    log = stub.evidence_map.get("gate_decision_log") or []
    prose_entries = [e for e in log if e["violation"] == "prose_fact_unsupported"]
    assert len(prose_entries) == 1
    assert prose_entries[0]["section_index"] == 2
    assert prose_entries[0]["action"] == "moved_to_hypotheses"
    # IDs werden vor dem Protokollieren zentral neu vergeben — der Eintrag
    # referenziert die finale Hypothesen-ID, nicht die vorläufige.
    assert prose_entries[0]["claim_id"] == "hypothesis_01"
    section = stub.evidence_map["sections"][0]
    assert section["hypotheses"][0]["hypothesis_id"] == "hypothesis_01"
    # Reguläres Gate-Routing darf den Report-Status NICHT abstufen — der
    # degradation_log (Trigger für apply_degradation_downgrade) bleibt leer.
    assert not stub.evidence_map.get("degradation_log")


def test_key_takeaway_confidence_scope_defaults_to_simulation():
    takeaway = SectionKeyTakeaway(statement="Acht Agenten benennen dieselben Risiken.")
    assert takeaway.confidence_scope == "simulation_consensus"


def test_render_evidence_status_shows_counts_and_simulation_notice():
    report = SimpleNamespace(claims=[], hypotheses=[object(), object()], data_gaps=[object()])
    rendered = render_evidence_status(report)
    assert "Validierte Claims" in rendered
    assert "Hypothesen" in rendered
    assert "simulierten Agenten" in rendered
    assert "keine" in rendered and "empirische Nutzerforschung" in rendered


def test_render_report_v3_includes_evidence_status():
    from datetime import datetime, timezone

    from app.contracts.report_v3 import ReportV3
    from app.services.report_agent.markdown_renderer import render_report_v3

    report = ReportV3(
        report_id="report_test01",
        generated_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    rendered = render_report_v3(report)
    assert "## Evidenzstatus" in rendered
    assert "empirische Nutzerforschung" in rendered
    # Der Status-Block steht vor den Detail-Tabellen.
    assert rendered.index("## Evidenzstatus") < rendered.index("## Claims")
