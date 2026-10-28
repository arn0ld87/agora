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

import types
from typing import Any, Dict

from types import SimpleNamespace

from app.services.report_agent.attribution_guard import (
    CONSENSUS_MIN_EVIDENCE,
    EvidenceProfile,
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
    resolve_section_evidence_records,
)
from app.services.report_agent.section_pipeline import _correct_attribution

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
    # Ausschließend gezählt: das Interview zählt nicht zusätzlich als
    # Simulationsbeitrag, sonst deckte ein reiner Interview-Lauf die Formel
    # "Die Simulation zeigt" ab.
    assert profile.simulation_evidence == 1
    assert profile.interview_evidence == 1


def test_an_interview_alone_does_not_back_a_simulation_attribution():
    """Die Gegenrichtung: nur Interviews, keine Simulationsbeiträge.

    Beide tragen ``agent_quote``. Zählte ein Interview beidseitig, bliebe
    "Die Simulation zeigt" stehen, obwohl keine Simulation als Zeuge
    auftreten kann.
    """
    profile = profile_from_evidence_index([
        _record("agent_quote", "ev_1", record_type="agent_interview")
    ])

    assert profile.has_interviews is True
    assert profile.has_simulation is False


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


# --- Slice 4: Qualifikationsfilter & Section-Scoped Attribution Guard -------


def test_profile_from_evidence_index_ignores_non_qualifying_records():
    """Records mit supports_claim=False, unzulässiger Provenienz oder graph_origin zählen nicht."""
    index = {
        "E-REFUTED-SIM": {
            "evidence_id": "E-REFUTED-SIM",
            "source_kind": "agent_quote",
            "type": "agent_post",
            "supports_claim": False,
        },
        "E-DERIVED-SIM": {
            "evidence_id": "E-DERIVED-SIM",
            "source_kind": "agent_quote",
            "type": "agent_post",
            "provenance_class": "derived_Calculation",
        },
        "E-MANUAL-INTERVIEW": {
            "evidence_id": "E-MANUAL-INTERVIEW",
            "source_kind": "agent_quote",
            "type": "agent_interview",
            "graph_origin": "manual",
        },
        "E-VALID-SEED": {
            "evidence_id": "E-VALID-SEED",
            "source_kind": "seed_corpus",
            "type": "seed_document",
            "supports_claim": True,
        },
    }

    profile = profile_from_evidence_index(index)

    assert profile == EvidenceProfile(
        simulation_evidence=0,
        interview_evidence=0,
        seed_evidence=1,
    )
    assert not profile.has_simulation
    assert not profile.has_interviews


def test_correct_attribution_scopes_to_active_section_evidence_when_only_seed_present():
    """Simulations-Evidenz aus Section 1 im globalen Index schaltet Section 2 (nur Seed) nicht frei."""
    agent = SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "E-SIM-1": {
                    "evidence_id": "E-SIM-1",
                    "source_kind": "agent_quote",
                    "type": "agent_post",
                },
                "E-SEED-1": {
                    "evidence_id": "E-SEED-1",
                    "source_kind": "seed_corpus",
                    "type": "seed_document",
                },
            }
        },
        _active_section_evidence=[
            {
                "evidence_id": "E-SEED-1",
                "source_type": "seed_document",
                "provenance_class": "source_grounded",
            }
        ],
    )
    section = SimpleNamespace(title="Ausgangslage")

    corrected = _correct_attribution(
        agent,
        section,
        "Die Simulation zeigt, dass die Übergangsfrist knapp bemessen ist.",
        section_index=2,
    )

    assert "Die Simulation zeigt" not in corrected
    assert corrected == "Die Quellenlage zeigt, dass die Übergangsfrist knapp bemessen ist."


def test_correct_attribution_keeps_simulation_formula_when_active_section_has_simulation_evidence():
    """Hat die aktuelle Section eigene qualifizierte Simulations-Evidenz, bleibt die Formel erhalten."""
    agent = SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "E-SIM-1": {
                    "evidence_id": "E-SIM-1",
                    "source_kind": "agent_quote",
                    "type": "agent_post",
                },
            }
        },
        _active_section_evidence=[
            {
                "evidence_id": "E-SIM-1",
                "type": "agent_post",
                "source_kind": "agent_quote",
            }
        ],
    )
    section = SimpleNamespace(title="Simulationsreaktionen")
    text = "Die Simulation zeigt eine deutliche Skepsis der Pflege."

    corrected = _correct_attribution(
        agent,
        section,
        text,
        section_index=1,
    )

    assert corrected == text


def test_resolve_section_evidence_records_preserves_index_disqualification():
    """Hat der globale Index supports_claim=False oder graph_origin gesetzt, bleibt die Disqualifikation erhalten."""
    index = {
        "E-SIM-1": {
            "evidence_id": "E-SIM-1",
            "source_kind": "agent_quote",
            "type": "agent_post",
            "supports_claim": False,
        }
    }
    section_ev = [{"evidence_id": "E-SIM-1", "type": "agent_post"}]

    resolved = resolve_section_evidence_records(section_ev, index)
    profile = profile_from_evidence_index(resolved)

    assert not profile.has_simulation


# --- Section-Scoped Attribution & Graph-Origin Filter (Slice 4) -------------


def test_evidence_profile_ignores_manual_and_edited_graph_origin():
    """Graph-Kanten aus Handarbeit oder Editierung dürfen keine Zuschreibungen tragen."""
    records = {
        "ev_manual": {
            "evidence_id": "ev_manual",
            "source_kind": "agent_action",
            "type": "agent_action",
            "graph_origin": "manual",
        },
        "ev_edited": {
            "evidence_id": "ev_edited",
            "source_kind": "seed_corpus",
            "type": "seed_document",
            "graph_origin": "edited",
        },
        "ev_valid_sim": {
            "evidence_id": "ev_valid_sim",
            "source_kind": "agent_action",
            "type": "agent_action",
            "graph_origin": None,
        },
    }

    profile = EvidenceProfile.from_evidence_index(records)
    assert profile.simulation_evidence == 1
    assert profile.seed_evidence == 0


def test_evidence_profile_ignores_refuted_bindings_supports_claim_false():
    """Widerlegte Bindings (supports_claim=False) speisen keine Evidenz ein."""
    records = [
        {
            "evidence_id": "ev_refuted_sim",
            "source_kind": "agent_action",
            "type": "agent_action",
            "supports_claim": False,
        },
        {
            "evidence_id": "ev_refuted_interview",
            "source_kind": "agent_quote",
            "type": "agent_interview",
            "supports_claim": False,
        },
        {
            "evidence_id": "ev_valid_sim",
            "source_kind": "agent_action",
            "type": "agent_action",
            "supports_claim": True,
        },
    ]

    profile = EvidenceProfile.from_evidence_index(records)
    assert profile.simulation_evidence == 1
    assert profile.interview_evidence == 0


def test_correct_attribution_scoped_to_active_section_evidence():
    """_correct_attribution nutzt _active_section_evidence statt blind den globalen Index."""
    agent = types.SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "ev_sim": {
                    "evidence_id": "ev_sim",
                    "source_kind": "agent_action",
                    "type": "agent_action",
                }
            }
        },
        _active_section_evidence=[],
    )
    section = types.SimpleNamespace(title="Wirtschaftlichkeit")
    content = "Die Simulation zeigt eine deutliche Skepsis."

    # Abschnitt hat keine eigene Simulations-Evidenz -> muss korrigiert werden
    corrected = _correct_attribution(agent, section, content, section_index=1)
    assert corrected == "Die Quellenlage zeigt eine deutliche Skepsis."


def test_correct_attribution_resolves_bindings_in_active_section():
    """Bindings in _active_section_evidence werden gegen evidence_index aufgelöst."""
    agent = types.SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "ev_sim": {
                    "evidence_id": "ev_sim",
                    "source_kind": "agent_action",
                    "type": "agent_action",
                }
            }
        },
        _active_section_evidence=[{"evidence_id": "ev_sim"}],
    )
    section = types.SimpleNamespace(title="Simulationsbefunde")
    content = "Die Simulation zeigt eine deutliche Skepsis."

    # Beleg vorhanden und auflösbar -> bleibt erhalten
    corrected = _correct_attribution(agent, section, content, section_index=2)
    assert corrected == content


def test_correct_attribution_filters_refuted_binding_in_active_section():
    """Ein widerlegtes Binding im Abschnitt trägt die Simulation nicht."""
    agent = types.SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "ev_sim": {
                    "evidence_id": "ev_sim",
                    "source_kind": "agent_action",
                    "type": "agent_action",
                }
            }
        },
        _active_section_evidence=[{"evidence_id": "ev_sim", "supports_claim": False}],
    )
    section = types.SimpleNamespace(title="Simulationsbefunde")
    content = "Die Simulation zeigt eine deutliche Skepsis."

    corrected = _correct_attribution(agent, section, content, section_index=2)
    assert corrected == "Die Quellenlage zeigt eine deutliche Skepsis."


def test_correct_attribution_falls_back_when_active_evidence_is_none():
    """Wenn _active_section_evidence None ist (z. B. isolierter Test), greift der globale Index."""
    agent = types.SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "ev_sim": {
                    "evidence_id": "ev_sim",
                    "source_kind": "agent_action",
                    "type": "agent_action",
                }
            }
        },
        _active_section_evidence=None,
    )
    section = types.SimpleNamespace(title="Legacy Fallback")
    content = "Die Simulation zeigt eine deutliche Skepsis."

    corrected = _correct_attribution(agent, section, content, section_index=0)
    assert corrected == content


def test_correct_attribution_includes_preloaded_global_evidence_refs_when_active_section_empty():
    """Vorab geladene global_evidence_refs tragen Simulationszuschreibungen auch ohne neuen Abschnitts-Toolcall."""
    agent = types.SimpleNamespace(
        evidence_map={
            "evidence_index": {
                "ev_sim": {
                    "evidence_id": "ev_sim",
                    "source_kind": "agent_quote",
                    "type": "agent_post",
                }
            },
            "global_evidence_refs": ["ev_sim"],
        },
        _active_section_evidence=[],
    )
    section = types.SimpleNamespace(title="Synthese")
    content = "Die Simulation zeigt eine deutliche Skepsis."

    corrected = _correct_attribution(agent, section, content, section_index=1)
    assert corrected == content


def test_resolve_section_evidence_records_prevents_provenance_and_source_kind_spoofing():
    """Widersprüchliche Abschnitts-Einträge dürfen autoritative Index-Metadaten
    (source_kind, type, provenance_class) nicht überschreiben."""
    index = {
        "E-SEED-ONLY": {
            "evidence_id": "E-SEED-ONLY",
            "source_kind": "seed_corpus",
            "type": "seed_document",
            "source_type": "seed_document",
            "provenance_class": "source_grounded",
        },
        "E-DERIVED-SIM": {
            "evidence_id": "E-DERIVED-SIM",
            "source_kind": "agent_quote",
            "type": "agent_post",
            "provenance_class": "derived_calculation",
        },
        "E-INFERRED-INTERVIEW": {
            "evidence_id": "E-INFERRED-INTERVIEW",
            "source_kind": "inferred",
            "type": "agent_interview",
            "provenance_class": "source_grounded",
        },
    }
    # Abschnitts-Einträge versuchen, ein Seed-Dokument als Simulations-Post/Interview
    # auszugeben bzw. disqualifizierte Provenienz zu überschreiben.
    section_ev = [
        {
            "evidence_id": "E-SEED-ONLY",
            "source_kind": "agent_quote",
            "type": "agent_interview",
            "source_type": "agent_interview",
        },
        {
            "evidence_id": "E-DERIVED-SIM",
            "source_kind": "agent_quote",
            "type": "agent_post",
            "provenance_class": "source_grounded",
        },
        {
            "evidence_id": "E-INFERRED-INTERVIEW",
            "source_kind": "agent_quote",
            "type": "agent_interview",
            "provenance_class": "source_grounded",
        },
    ]

    resolved = resolve_section_evidence_records(section_ev, index)
    profile = profile_from_evidence_index(resolved)

    assert profile.seed_evidence == 1
    assert profile.simulation_evidence == 0
    assert profile.interview_evidence == 0
    assert not profile.has_simulation
    assert not profile.has_interviews



