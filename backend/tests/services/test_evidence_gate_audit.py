"""Regressionstests für den auditierbaren Evidence-Gate-Trail (Slice 7).

Der Referenzlauf report_06f654800817 entfernte 17 Fließtext-Aussagen und
routete sämtliche Claims in Hypothesen — auditierbar war davon nichts.
Diese Tests fixieren, dass jede Gate-Entscheidung (fehlende
Supporting-Evidence, Fließtext-Entfernung) als
``EvidenceDegradationModel``-Eintrag im ``gate_decision_log`` landet —
getrennt vom ``degradation_log``, der über ``apply_degradation_downgrade``
den Report-Status abstuft und deshalb regulärem Gate-Routing vorbehalten
bleiben darf (Codex-Review PR #1151, P1).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services.evidence_entailment import EntailmentVerdict
from app.services.report_agent import ReportAgent
from app.services.report_agent.markdown_renderer import render_evidence_status
from app.services.report_agent.schemas import SectionKeyTakeaway
from app.services.report_agent.text_verification import RejectedStatement

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


def test_single_supported_evidence_keeps_low_claim():
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_07",
        "claim_text": "Die Migration braucht eine kontrollierte Übergangsphase.",
        "evidence": [{"evidence_id": _EV_ID, "supports_claim": True}],
        "confidence_score": 0.6,
        "confidence_label": "low",
    }]

    finalized, hypotheses, _gaps, decisions = agent._finalize_section_claims(claims)

    assert len(finalized) == 1
    assert finalized[0]["claim_id"] == "claim_07"
    assert finalized[0]["confidence_label"] == "low"
    assert finalized[0]["evidence"] == [
        {"evidence_id": _EV_ID, "supports_claim": True}
    ]
    assert hypotheses == []
    assert decisions == []


# ---------------------------------------------------------------------------
# Issue #1319: data_gaps.suggested_fix war identisch mit dem Claim-Text
# (suggestions[0] = Audit-Snippet des Claims selbst) — kein echter
# Lösungsvorschlag. Jetzt wird der Text aus gap_reason abgeleitet, und der
# data_gap verweist per hypothesis_id auf die begleitende Hypothese, statt
# claim_text erneut zu tragen.
# ---------------------------------------------------------------------------


def test_no_evidence_bound_gap_hat_konkreten_hinweis_statt_claim_text():
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Die Personas reagieren durchweg positiv auf das neue Feature.",
        "evidence": [],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]

    _finalized, hypotheses, gaps, _decisions = agent._finalize_section_claims(claims)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["gap_reason"] == "no_evidence_bound"
    assert gap["suggested_fix"] != gap["claim_text"]
    assert "recherchieren" in gap["suggested_fix"]


def test_related_evidence_only_gap_hat_anderen_hinweis_als_no_evidence_bound():
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Die Personas reagieren durchweg positiv auf das neue Feature.",
        "evidence": [{"evidence_id": _EV_ID, "supports_claim": False}],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]

    _finalized, _hypotheses, gaps, _decisions = agent._finalize_section_claims(claims)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["gap_reason"] == "related_evidence_only"
    assert gap["suggested_fix"] != gap["claim_text"]
    assert "direktem Aussagebezug" in gap["suggested_fix"]

    # Beide Gap-Gründe erhalten unterschiedliche Lösungsvorschläge.
    no_evidence_claims = [{
        "claim_id": "claim_02",
        "claim_text": "Ein völlig anderer, unbelegter Claim ohne jede Quelle.",
        "evidence": [],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]
    _finalized2, _hyp2, gaps2, _dec2 = agent._finalize_section_claims(no_evidence_claims)
    assert gaps2[0]["suggested_fix"] != gap["suggested_fix"]


def test_data_gap_traegt_hypothesis_id_der_zugehoerigen_hypothese():
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Die Personas reagieren durchweg positiv auf das neue Feature.",
        "evidence": [],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]

    _finalized, hypotheses, gaps, _decisions = agent._finalize_section_claims(claims)

    assert len(hypotheses) == 1
    assert len(gaps) == 1
    assert gaps[0]["hypothesis_id"] == hypotheses[0]["hypothesis_id"]
    # claim_text bleibt erhalten — wird in manager.py für die Beschreibung gebraucht.
    assert gaps[0]["claim_text"]


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
    # Issue #1356: der Puffer traegt Paare aus Hypothese und Statement — das
    # Gate-Log unterscheidet daran den entfernten vom markierten Fall.
    stub._pending_prose_hypotheses = {2: [(
        {
            "hypothesis_id": "hypothesis_99",
            "hypothesis_text": "Der Traffic wächst derzeit um rund 20 Prozent pro Monat.",
            "rationale": "Aus dem Fließtext entfernt: keine deckende Quelle gefunden.",
            "suggested_evidence": [],
        },
        RejectedStatement(
            text="Der Traffic wächst derzeit um rund 20 Prozent pro Monat.",
            verdict=EntailmentVerdict.CONTRADICTED,
            reason="keine deckende Quelle gefunden",
        ),
    )]}
    stub._pending_section_metadata = {}
    # Issue #1187: die echte Signatur nimmt einen optionalen
    # ``heartbeat``-Callback entgegen; der Stub spiegelt sie.
    stub._build_claims_for_section = lambda content, heartbeat=None: []
    stub._finalize_section_claims = lambda raw: ([], [], [], [])
    stub._section_dedup_check = lambda **kwargs: None

    with patch("app.services.report_agent.ReportManager.save_evidence_map"):
        stub._save_evidence_section(
            "r1", 2, "Unsicherheiten",
            "Ein ausreichend langer Abschnittstext ohne Fallback-Marker.",
        )

    log = stub.evidence_map.get("gate_decision_log") or []
    prose_entries = [e for e in log if e["violation"] == "prose_fact_contradicted"]
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


# ---------------------------------------------------------------------------
# medium ohne agent-grounded Evidence (ADR-0002 Stufe agent_grounded)
#
# Produktionslauf report_dea78f514e73 (09.08.2026): Der Builder ließ
# medium-Claims ohne agent_quote+seed_corpus durch, der
# ReportClaimModel-Validator lehnte sie ab und die gesamte
# EvidenceMap-Validierung schlug fehl — Report abgebrochen, nicht abgestuft.
# Der Reparaturlauf half nicht: Pydantic meldet pro Durchgang nur den ersten
# Verstoß je Modell, nach der Reparatur von claim_01 blieb claim_02 stehen.
# ---------------------------------------------------------------------------

_EV_ID_A = "ev_" + "a" * 32
_EV_ID_B = "ev_" + "b" * 32


def _evidence(evidence_id: str, source_kind: str, **extra) -> dict:
    item = {
        "evidence_id": evidence_id,
        "type": "graph_fact" if source_kind != "agent_interview" else "agent_interview",
        "source": "report_tool",
        "snippet": "Belegtext aus der Quelle.",
        "source_kind": source_kind,
        "supports_claim": True,
    }
    item.update(extra)
    return item


def test_medium_without_agent_grounded_evidence_is_downgraded_to_low():
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_02",
        "claim_text": "Die Migration senkt die organische Sichtbarkeit kurzfristig.",
        "evidence": [
            _evidence(_EV_ID_A, "seed_corpus"),
            _evidence(_EV_ID_B, "graph_relation"),
        ],
        "confidence_score": 0.55,
        "confidence_label": "medium",
    }]

    finalized, hypotheses, _gaps, decisions = agent._finalize_section_claims(claims)

    # Der Claim verschwindet nicht — er verliert nur sein unverdientes Label.
    assert len(finalized) == 1
    assert finalized[0]["confidence_label"] == "low"
    assert hypotheses == []
    assert len(decisions) == 1
    assert decisions[0]["claim_id"] == "claim_02"
    assert decisions[0]["violation"] == "medium_without_agent_grounded_evidence"
    assert decisions[0]["action"] == "downgraded_to_low"


def _record(evidence_id: str, source_kind: str, **extra) -> dict:
    record = {
        "evidence_id": evidence_id,
        "producer_key": f"key:{evidence_id}",
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Belegtext aus der Quelle.",
        "source_kind": source_kind,
    }
    record.update(extra)
    return record


def test_downgraded_claim_passes_the_evidence_map_validator():
    """Der Kern des Defekts: die fertige EvidenceMap muss validieren.

    ``EvidenceMapModel.validate_evidence_cross_references`` urteilt über die
    Records im ``evidence_index``. Vor dem Fix erreichte ein medium-Claim ohne
    agent_quote+seed_corpus diesen Validator und ließ die Validierung der
    gesamten Map scheitern — der Report brach ab, statt den einzelnen Claim
    ehrlich abzustufen (Produktionslauf report_dea78f514e73).
    """
    from app.contracts.report_contract import EvidenceMapModel

    agent = ReportAgent.__new__(ReportAgent)
    agent.evidence_map = {
        "schema_version": 3,
        "report_id": "report_test01",
        "simulation_id": "sim_test",
        "evidence_index": {
            _EV_ID_A: _record(_EV_ID_A, "seed_corpus"),
            _EV_ID_B: _record(_EV_ID_B, "graph_relation"),
        },
        "global_evidence_refs": [],
        "sections": [],
    }
    claims = [{
        "claim_id": "claim_02",
        "claim_text": "Die Migration senkt die organische Sichtbarkeit kurzfristig.",
        "evidence": [
            _evidence(_EV_ID_A, "seed_corpus"),
            _evidence(_EV_ID_B, "graph_relation"),
        ],
        "confidence_score": 0.55,
        "confidence_label": "medium",
    }]

    finalized, _hypotheses, _gaps, _decisions = agent._finalize_section_claims(claims)

    agent.evidence_map["sections"] = [{
        "section_index": 1,
        "section_title": "Kurzfazit",
        "section_summary": "Kurzfazit zur Domainmigration.",
        "claims": [{
            "claim_id": finalized[0]["claim_id"],
            "claim_text": finalized[0]["claim_text"],
            "confidence_score": finalized[0]["confidence_score"],
            "confidence_label": finalized[0]["confidence_label"],
            "evidence": [
                {"evidence_id": _EV_ID_A, "supports_claim": True},
                {"evidence_id": _EV_ID_B, "supports_claim": True},
            ],
        }],
    }]

    EvidenceMapModel.model_validate(agent.evidence_map)


def test_inline_item_without_source_kind_is_resolved_via_evidence_index():
    """Die Bewertung folgt den Records, nicht den Inline-Einträgen.

    Ein Inline-Eintrag trägt nur die Referenz; ``source_kind`` und ``quote``
    stehen kanonisch am Record. Würde der Builder nur die Inline-Daten lesen,
    fiele dieser vollständig agent-grounded Claim grundlos auf ``low``.
    """
    agent = ReportAgent.__new__(ReportAgent)
    agent.evidence_map = {
        "evidence_index": {
            _EV_ID_A: _record(_EV_ID_A, "seed_corpus"),
            _EV_ID_B: _record(
                _EV_ID_B,
                "agent_quote",
                type="agent_interview",
                quote="Ich würde die alte Domain mindestens ein Jahr weiterleiten.",
                persona_stakeholder_group="Bestandsleser",
            ),
        },
    }
    claims = [{
        "claim_id": "claim_04",
        "claim_text": "Bestandsleser erwarten eine lange Weiterleitung.",
        "evidence": [
            {"evidence_id": _EV_ID_A, "supports_claim": True},
            {"evidence_id": _EV_ID_B, "supports_claim": True},
        ],
        "confidence_score": 0.6,
        "confidence_label": "medium",
    }]

    finalized, _hypotheses, _gaps, decisions = agent._finalize_section_claims(claims)

    assert finalized[0]["confidence_label"] == "medium"
    assert decisions == []


def test_agent_grounded_medium_claim_keeps_its_label():
    """Gegenprobe: die Abstufung ist keine pauschale medium-Deckelung."""
    agent = ReportAgent.__new__(ReportAgent)
    claims = [{
        "claim_id": "claim_03",
        "claim_text": "Mehrere Stakeholder erwarten Reibung beim Umzug.",
        "evidence": [
            _evidence(_EV_ID_A, "seed_corpus"),
            _evidence(
                _EV_ID_B,
                "agent_quote",
                type="agent_interview",
                quote="Ich würde die alte Domain mindestens ein Jahr weiterleiten.",
                persona_stakeholder_group="Bestandsleser",
            ),
        ],
        "confidence_score": 0.6,
        "confidence_label": "medium",
    }]

    finalized, _hypotheses, _gaps, decisions = agent._finalize_section_claims(claims)

    assert finalized[0]["confidence_label"] == "medium"
    assert decisions == []
