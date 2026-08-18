"""Der Referenzlauf ``report_cc2ef45da5e9``, einmal durch die ganze Kette.

Die Einzelmodule dieses Slices sind je für sich getestet. Was das nicht
abdeckt, ist ihr Zusammenspiel — und genau dort saß der schwerste Fehler:
ein Sortier-Hilfsfeld auf der Evidence-Bindung war für sich harmlos, brach
aber eine Stufe später die Section-Validierung und ließ den Reparaturlauf
jeden belegten Claim löschen. Ein Test je Modul hätte das nie gefunden.

Dieser Test spielt deshalb das Szenario des Referenzlaufs durch: dieselben
Zahlen, derselbe aufgerissene Absatz, dieselbe gescheiterte Simulation, dieselben
acht ergebnislosen Interview-Aufrufe. Geprüft wird, dass die Schutzmechanismen
zusammen greifen und einander nicht aufheben — und dass am Ende ein Artefakt
steht, das seinen eigenen Vertrag erfüllt.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.contracts.report_contract import EvidenceMapModel, ReportSectionModel
from app.contracts.report_v3 import Threshold
from app.models.report import Report, ReportStatus
from app.services.evidence_binder import bind_evidence_to_claim
from app.services.evidence_entailment import classify_evidence
from app.services.graph.graph_dtos import InterviewResult
from app.services.report_agent.agent import ReportAgent
from app.services.report_agent.attribution_guard import (
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
)
from app.services.report_agent.evidence import register_evidence_record
from app.services.report_agent.evidence_ledger import EvidenceCoverageLedger
from app.services.report_agent.run_degradation import (
    apply_run_degradation_downgrade,
    assert_run_invariants,
    collect_run_degradations,
)
from app.services.report_agent.text_verification import verify_prose
from app.services.report_agent.threshold_provenance import (
    bind_threshold_provenance,
    dedup_thresholds,
)
from app.services.report_agent.tools import define_tools, execute_tool_call

SCOPE_ID = "sim_aeba43fc4665"

#: Die Quellenlage des Referenzlaufs — ein Klinik-Rollout.
SEED_FACTS: List[str] = [
    "Der Projektplan fordert vor Produktivstart mindestens 80 Prozent "
    "Schulungsquote der unmittelbar betroffenen Beschäftigten.",
    "In der Pflege sind 54 Prozent der Beschäftigten geschult.",
    "In der Pflege-Nachtschicht sind 31 Prozent der Beschäftigten geschult.",
    "Für den manuellen Fallback sind höchstens 15 Minuten vorgesehen.",
    "In der Testphase wichen 38 Empfehlungen in der Dringlichkeitsstufe ab.",
]

#: Der Absatz, den der Trust-Layer im Referenzlauf aufgerissen hat.
PROSE = (
    "Erstens bleibt die Personaldecke der Nachtschicht dünn. "
    "Zweitens fehlt eine dokumentierte Rückfallebene. "
    "Drittens liegt die Schulungsquote der Pflege-Nachtschicht bei 31 Prozent, "
    "während der Projektplan mindestens 80 Prozent der unmittelbar betroffenen "
    "Beschäftigten vor Produktivstart fordert. "
    "Viertens fehlt ein belastbarer Zeitplan."
)

#: Der Laufzustand: Simulation gescheitert, drei Runden fehlen.
SNAPSHOT: Dict[str, Any] = {
    "rounds_completed": 45,
    "total_rounds": 48,
    "simulation_running": False,
    "simulation_status": "failed",
}


@pytest.fixture
def evidence_map() -> Dict[str, Any]:
    """Ein kanonisierter Evidence-Index aus den Seed-Fakten."""
    payload: Dict[str, Any] = {
        "schema_version": 3,
        "report_id": "report_cc2ef45da5e9",
        "simulation_id": SCOPE_ID,
        "evidence_index": {},
        "global_evidence_refs": [],
        "sections": [],
    }
    ledger = EvidenceCoverageLedger()
    for index, fact in enumerate(SEED_FACTS):
        register_evidence_record(
            payload,
            {
                "type": "graph_fact",
                "source": "insight_forge",
                "source_kind": "seed_corpus",
                "snippet": fact,
                "producer_key": f"seed:{index}",
            },
            scope_id=SCOPE_ID,
            ledger=ledger,
        )
    payload["evidence_coverage_ledger"] = ledger.as_payload()
    return payload


@pytest.fixture
def pool(evidence_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(evidence_map["evidence_index"].values())


# --- Der Fließtext übersteht die Prüfung ------------------------------------


def test_the_reference_sentence_survives_the_trust_layer(pool):
    """P0: 31 % Ist gegen 80 % Mindestanforderung ist kein Widerspruch."""
    result = verify_prose(PROSE, pool)

    assert result.rejected == []
    assert "31 Prozent" in result.content
    assert "80 Prozent" in result.content


def test_the_enumeration_stays_intact(pool):
    """P0: der Absatz zählt lückenlos — nichts wurde entfernt."""
    content = verify_prose(PROSE, pool).content

    for word in ("Erstens", "Zweitens", "Drittens", "Viertens"):
        assert word in content


def test_a_genuinely_contradicted_sentence_still_goes(pool):
    """Die Gegenprobe: der Schutz ist kein Freibrief.

    Ohne sie wäre nicht unterscheidbar, ob der Satz oben überlebt, weil er
    korrekt ist — oder weil der Löschpfad tot ist.
    """
    wrong = "In der Pflege sind 91 Prozent der Beschäftigten geschult."

    result = verify_prose(wrong, pool)

    assert result.rejected, "Ein echter Widerspruch muss weiterhin entfernt werden"


# --- Die Belege werden gefunden und bleiben vertragstreu --------------------


@pytest.mark.parametrize(
    "claim",
    [
        "Vor Produktivstart müssen mindestens 80 Prozent geschult sein.",
        "In der Pflege liegt die Schulungsquote bei 54 Prozent.",
        "Der manuelle Fallback ist auf höchstens 15 Minuten begrenzt.",
    ],
)
def test_every_seed_number_finds_its_source(claim: str, pool):
    """P1: acht belegte Zahlen galten im Referenzlauf als unbelegt."""
    verdicts = [classify_evidence(claim, item) for item in pool]

    assert not all("no_matching_number" in v.checks for v in verdicts)


def test_a_binding_survives_the_section_contract(pool):
    """Der Blocker: ein Zusatzfeld auf der Bindung riss die ganze Section mit.

    Geprüft wird nicht die Bindung allein, sondern der Weg, den sie nimmt —
    genau die Stufe, an der das Modultestnetz eine Lücke hatte.
    """
    def embed(_text: str) -> List[float]:
        return [1.0, 0.0]

    claim_text = "In der Pflege liegt die Schulungsquote bei 54 Prozent."
    bound = bind_evidence_to_claim(claim_text, pool, embed)

    assert bound, "Der Claim muss überhaupt binden"
    section = ReportSectionModel.model_validate({
        "section_index": 1,
        "section_title": "Ausgangslage",
        "section_summary": "Schulungsstand der betroffenen Bereiche.",
        "claims": [{
            "claim_id": "claim_01",
            "claim_text": claim_text,
            "confidence_score": 0.8,
            "confidence_label": "low",
            "evidence": bound,
        }],
    })

    assert section.claims[0].evidence


def test_the_coverage_ledger_accounts_for_every_seed_number(evidence_map):
    """P1: kein quantitativer Fakt verschwindet wortlos."""
    ledger = evidence_map["evidence_coverage_ledger"]

    assert len(ledger) == len(SEED_FACTS)
    assert all(entry["canonical_evidence_id"] for entry in ledger)


def test_the_evidence_map_validates_against_its_contract(evidence_map):
    validated = EvidenceMapModel.model_validate(evidence_map)

    assert len(validated.evidence_index) == len(SEED_FACTS)
    assert len(validated.evidence_coverage_ledger) == len(SEED_FACTS)


# --- Datenlücken bleiben Aussagen über die Quellenlage ----------------------


def test_a_fact_from_the_seed_never_becomes_a_data_gap(evidence_map):
    """P1: 159 Data Gaps, darunter Aussagen, die wörtlich im Seed standen."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.evidence_map = evidence_map

    _claims, hypotheses, gaps, decisions = agent._finalize_section_claims([{
        "claim_id": "claim_01",
        "claim_text": "Vor Produktivstart müssen mindestens 80 Prozent geschult sein.",
        "evidence": [],
        "confidence_score": 0.2,
        "confidence_label": "low",
    }])

    assert gaps == []
    assert len(hypotheses) == 1, "Unbelegt bleibt die Aussage trotzdem"
    assert "binding_failure" in decisions[0]["detail"]


def test_a_fact_absent_from_every_source_still_becomes_a_data_gap(evidence_map):
    agent = ReportAgent.__new__(ReportAgent)
    agent.evidence_map = evidence_map

    _claims, _hypotheses, gaps, _decisions = agent._finalize_section_claims([{
        "claim_id": "claim_01",
        "claim_text": "Die Kantinenpreise steigen im kommenden Quartal deutlich an.",
        "evidence": [],
        "confidence_score": 0.2,
        "confidence_label": "low",
    }])

    assert [gap["gap_reason"] for gap in gaps] == ["source_information_absent"]


# --- Schwellenwerte ---------------------------------------------------------


def test_the_seed_threshold_is_bound_and_deduplicated(pool):
    """P1: 27 Thresholds, alle heuristisch, mehrere doppelt."""
    from_two_sections = [
        Threshold.model_validate({
            "id": "th_01",
            "label": "Schulungsquote vor Produktivstart",
            "value": 80.0,
            "unit": "percent",
            "purpose": "target",
            "origin": "simulation_proposal",
        }),
        Threshold.model_validate({
            "id": "th_09",
            "label": "Vor Produktivstart: Schulungsquote",
            "value": 80.0,
            "unit": "%",
            "purpose": "target",
            "origin": "empirical_data",
        }),
    ]

    result = dedup_thresholds(bind_threshold_provenance(from_two_sections, pool))

    assert len(result) == 1
    assert result[0].evidence_refs, "Der Wert steht wörtlich im Seed"
    assert result[0].evidence_status == "verified"


# --- Orchestrierung ---------------------------------------------------------


def _agent_with_failing_interviews() -> Any:
    """Ein Agent, dessen Interview-Umgebung nicht erreichbar ist."""
    result = InterviewResult(interview_topic="Sorgen", interview_questions=[])
    result.summary = "Interview tool TERMINALLY UNAVAILABLE for this report run."
    result.terminal_failure = True
    result.terminal_reason = "keine persistierten Agent-Personas"

    agent = MagicMock()
    agent.graph_tools.interview_agents.return_value = result
    agent.web_tools.is_available.return_value = False
    agent.graph_id = "graph_test"
    agent.simulation_id = SCOPE_ID
    agent.simulation_requirement = "Rollout im Klinikverbund"
    agent._current_section_index = 0
    agent._tool_circuit_breaker = None
    return agent


def test_eight_attempts_reach_the_interview_tool_once():
    """P1: acht Aufrufe, null Interviews — jedes Mal derselbe Ausfall."""
    agent = _agent_with_failing_interviews()

    for _ in range(8):
        execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})

    assert agent.graph_tools.interview_agents.call_count == 1
    assert "interview_agents" not in define_tools(agent)


def test_the_run_reports_its_own_degradation():
    """P1: der Bericht ging als ``completed`` hinaus."""
    degradations = collect_run_degradations(
        simulation_snapshot=SNAPSHOT,
        interviews_requested=8,
        interviews_succeeded=0,
        interview_disabled_reason="keine persistierten Agent-Personas",
    )
    status = apply_run_degradation_downgrade(ReportStatus.COMPLETED, degradations)

    reasons = {entry["reason"] for entry in degradations}
    assert {"simulation_failed", "45_of_48_rounds", "0_successful_interviews"} <= reasons
    assert status is ReportStatus.INCOMPLETE

    report = Report(
        report_id="report_cc2ef45da5e9",
        simulation_id=SCOPE_ID,
        graph_id="graph_test",
        simulation_requirement="Rollout im Klinikverbund",
        status=status,
        simulation_snapshot=SNAPSHOT,
        run_degradations=degradations,
    )
    assert report.degraded is True


def test_the_deterministic_invariants_are_silent_once_it_is_handled():
    """Die drei Befunde, die das LLM-Red-Team übersah — nach der Behandlung."""
    degradations = collect_run_degradations(
        simulation_snapshot=SNAPSHOT,
        interviews_requested=8,
        interviews_succeeded=0,
    )

    assert (
        assert_run_invariants(
            status="incomplete",
            run_degradations=degradations,
            simulation_status="failed",
            interviews_requested=8,
            interviews_succeeded=0,
        )
        == []
    )


# --- Zuschreibung -----------------------------------------------------------


def test_the_report_does_not_call_a_simulation_that_contributed_nothing(evidence_map):
    """P2: ein Claim mit Simulations-Evidence, durchgehend "Die Simulation zeigt"."""
    profile = profile_from_evidence_index(evidence_map["evidence_index"])
    text = (
        "Die Simulation zeigt eine deutliche Skepsis der Pflege. "
        "Die interviewten Personas nennen die Schulungslücke zuerst."
    )

    findings = attribution_findings(text, profile)
    corrected = correct_attribution(text, profile)

    assert {finding["kind"] for finding in findings} == {
        "simulation_attribution_without_simulation_evidence",
        "interview_attribution_without_interviews",
    }
    assert "Die Simulation zeigt" not in corrected
    assert "interviewten" not in corrected
    # Die Aussagen selbst bleiben stehen — richtiggestellt wird die Herkunft.
    assert "deutliche Skepsis der Pflege" in corrected
    assert "Schulungslücke zuerst" in corrected


def test_a_seed_only_run_has_no_interview_evidence(evidence_map):
    """§18: null Interviews heißt niemals Interview-Konsens."""
    profile = profile_from_evidence_index(evidence_map["evidence_index"])

    assert profile.has_interviews is False
    assert profile.supports_consensus is False
