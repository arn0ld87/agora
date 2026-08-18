"""Der Bericht schreibt nur zu, was seine Belege hergeben.

Von 13 validierten Claims des Referenzlaufs ``report_cc2ef45da5e9`` trug genau
einer Simulations-Evidence. Der Bericht schrieb trotzdem durchgehend "Die
Simulation zeigt …". Dazu: acht Interview-Aufrufe, null Interviews — und
Formulierungen, die sich auf Interviews beriefen.

Eine Aussage, die "die Simulation" als Zeugen anruft, behauptet eine
empirische Grundlage. Steht dahinter ein Satz aus dem Projektplan, liest der
Leser etwas anderes, als er zu lesen meint.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.report_agent.attribution_guard import (
    CONSENSUS_MIN_EVIDENCE,
    EvidenceProfile,
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
)

#: Die Evidenzlage des Referenzlaufs: viel Seed, keine Simulation, keine
#: Interviews.
SEED_ONLY = EvidenceProfile(simulation_evidence=0, interview_evidence=0, seed_evidence=12)

#: Ein Lauf mit tragfähigem Simulationsmaterial.
RICH_SIMULATION = EvidenceProfile(
    simulation_evidence=CONSENSUS_MIN_EVIDENCE + 3, interview_evidence=4, seed_evidence=9
)


def _record(
    source_kind: str, evidence_id: str, *, record_type: str = "agent_post"
) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_kind": source_kind,
        "type": record_type,
        "snippet": "x",
    }


# --- Das Evidenzprofil ------------------------------------------------------


def test_the_profile_counts_source_kinds():
    profile = profile_from_evidence_index({
        "ev_1": _record("seed_corpus", "ev_1", record_type="seed_document"),
        "ev_2": _record("agent_quote", "ev_2", record_type="agent_interview"),
        "ev_3": _record("agent_action", "ev_3", record_type="agent_action"),
    })

    assert profile.seed_evidence == 1
    assert profile.simulation_evidence == 2
    assert profile.interview_evidence == 1


def test_a_simulation_post_is_not_counted_as_an_interview():
    """``source_kind`` trennt die beiden nicht — der Evidence-Typ tut es.

    ``agent_post`` und ``agent_interview`` fallen beide auf ``agent_quote``
    (ADR-0002 Anker 3, bewusst). Wer danach zählt, findet ausgerechnet dann
    Interviews, wenn eine Simulation lief und keines zustande kam: der Fall
    des Referenzlaufs.
    """
    profile = profile_from_evidence_index([
        _record("agent_quote", "ev_1", record_type="agent_post")
    ])

    assert profile.has_simulation is True
    assert profile.has_interviews is False


def test_an_interview_record_is_counted_as_one():
    profile = profile_from_evidence_index([
        _record("agent_quote", "ev_1", record_type="agent_interview")
    ])

    assert profile.has_interviews is True


def test_agent_actions_are_simulation_but_not_interviews():
    """Eine Agentenaktion ist keine Wortmeldung.

    Ohne die Trennung würde jede Aktion die Formel "die interviewten Personas"
    decken — und genau die stand im Referenzlauf über null Interviews.
    """
    profile = profile_from_evidence_index([
        _record("agent_action", "ev_1", record_type="agent_action")
    ])

    assert profile.has_simulation is True
    assert profile.has_interviews is False


def test_a_seed_only_run_supports_neither():
    profile = profile_from_evidence_index([_record("seed_corpus", "ev_1")])

    assert profile.has_simulation is False
    assert profile.has_interviews is False


def test_a_list_and_an_index_are_read_the_same_way():
    records = [_record("agent_quote", "ev_1", record_type="agent_interview")]

    assert profile_from_evidence_index(records) == profile_from_evidence_index(
        {"ev_1": records[0]}
    )


# --- Befunde ----------------------------------------------------------------


def test_simulation_attribution_without_simulation_evidence_is_reported():
    findings = attribution_findings(
        "Die Simulation zeigt eine deutliche Skepsis der Pflege.", SEED_ONLY
    )

    assert [f["kind"] for f in findings] == [
        "simulation_attribution_without_simulation_evidence"
    ]


def test_interview_attribution_without_interviews_is_reported():
    findings = attribution_findings(
        "Die interviewten Personas nennen die Schulungslücke zuerst.", SEED_ONLY
    )

    assert any(
        f["kind"] == "interview_attribution_without_interviews" for f in findings
    )


def test_consensus_language_without_broad_evidence_is_reported():
    """Zwei Aktionen sind kein Konsens."""
    findings = attribution_findings(
        "Die Belegschaft lehnt den Vollstart durchweg ab.",
        EvidenceProfile(simulation_evidence=2),
    )

    assert any(
        f["kind"] == "consensus_language_without_broad_evidence" for f in findings
    )


def test_a_backed_report_produces_no_findings():
    assert (
        attribution_findings(
            "Die Simulation zeigt eine durchweg skeptische Haltung, und die "
            "interviewten Personas bestätigen sie.",
            RICH_SIMULATION,
        )
        == []
    )


def test_a_correctly_attributed_seed_statement_is_not_flagged():
    assert (
        attribution_findings(
            "Aus dem Seed-Dokument ergibt sich eine Schulungsquote von 31 Prozent.",
            SEED_ONLY,
        )
        == []
    )


def test_an_empty_text_produces_no_findings():
    assert attribution_findings("", SEED_ONLY) == []


# --- Richtigstellung --------------------------------------------------------


def test_the_simulation_formula_is_replaced_but_the_statement_survives():
    corrected = correct_attribution(
        "Die Simulation zeigt eine deutliche Skepsis der Pflege.", SEED_ONLY
    )

    assert corrected == "Die Quellenlage zeigt eine deutliche Skepsis der Pflege."


def test_the_replacement_keeps_the_case_of_the_original():
    """Mitten im Satz darf kein Großwort entstehen."""
    corrected = correct_attribution(
        "Der Vollstart ist riskant, wie die Simulation zeigt.", SEED_ONLY
    )

    assert corrected == "Der Vollstart ist riskant, wie die Quellenlage zeigt."


def test_an_interview_formula_is_replaced_when_no_interview_happened():
    corrected = correct_attribution(
        "Die interviewten Personas nennen die Schulungslücke zuerst.", SEED_ONLY
    )

    assert corrected.startswith("Die verfügbaren Quellen")
    assert "interviewten" not in corrected


def test_a_backed_attribution_is_left_alone():
    text = "Die Simulation zeigt eine deutliche Skepsis der Pflege."

    assert correct_attribution(text, RICH_SIMULATION) == text


def test_consensus_language_is_reported_but_not_rewritten():
    """Sie steckt mitten im Satzbau — ein Eingriff dort zerreißt Sätze."""
    text = "Die Belegschaft lehnt den Vollstart durchweg ab."

    assert correct_attribution(text, EvidenceProfile(simulation_evidence=2)) == text


def test_the_rest_of_the_text_is_untouched():
    text = (
        "Die Schulungsquote liegt bei 31 Prozent. Die Simulation zeigt Skepsis. "
        "Der Projektplan fordert 80 Prozent."
    )

    corrected = correct_attribution(text, SEED_ONLY)

    assert "Die Schulungsquote liegt bei 31 Prozent." in corrected
    assert "Der Projektplan fordert 80 Prozent." in corrected
