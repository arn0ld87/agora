"""Die Auszählung über geführte Interviews (Issue #1357).

Eine Mengenaussage über Stakeholder ist von keinem einzelnen Zitat belegbar.
Diese Tests halten fest, was die Auszählung leisten muss — und was sie
ausdrücklich *nicht* darf.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.contracts.report_contract import EvidenceSourceKind
from app.services.evidence_entailment import (
    EntailmentVerdict,
    classify_evidence,
    extract_numeric_facts,
)
from app.services.report_agent.evidence import _TYPE_TO_SOURCE_KIND
from app.services.report_agent.interview_consensus import (
    MIN_INTERVIEWS_FOR_CONSENSUS,
    build_consensus_item,
)


def _interview(family: str, sentiment: float, group: str | None = None) -> Dict[str, Any]:
    return {
        "type": "agent_interview",
        "persona_role_family": family,
        "persona_stakeholder_group": group or family,
        "sentiment_score": sentiment,
        "quote": "Ein Zitat.",
    }


FOUR_MOSTLY_CRITICAL: List[Dict[str, Any]] = [
    _interview("Ärztlicher Dienst", -0.6),
    _interview("Pflege", -0.4),
    _interview("Arbeitnehmervertretung", -0.7),
    _interview("Projektleitung", 0.5),
]


def _built() -> Dict[str, Any]:
    item = build_consensus_item(
        FOUR_MOSTLY_CRITICAL,
        section_index=1,
        topic="ungestaffelter Vollstart",
        evidence_ids=["ev_1", "ev_2", "ev_3", "ev_4"],
    )
    assert item is not None
    return item


# --- Was sie leisten muss --------------------------------------------------

def test_the_count_carries_a_percentage_rule_two_can_check():
    """Regel 2 prüft Mengenaussagen gegen einen Prozentwert.

    Ohne eine explizite Prozentangabe im Text fände sie keinen Beleg — und
    genau daran scheiterten Konsens-Claims bisher.
    """
    facts = extract_numeric_facts(_built()["snippet"])
    assert any(fact.unit == "percent" for fact in facts)


def test_a_majority_claim_is_no_longer_unbacked():
    claim = (
        "Die Mehrheit der befragten Stakeholder-Rollen steht dem "
        "ungestaffelten Vollstart kritisch gegenüber."
    )
    result = classify_evidence(claim, _built())

    assert "quantifier_claim" in result.checks
    assert "quantifier_unbacked" not in result.checks


def test_a_majority_claim_against_a_minority_finding_is_contradicted():
    """Die Gegenprobe: dreht die Auszählung, kippt die Mehrheitsaussage."""
    mostly_supportive = [
        _interview("Ärztlicher Dienst", 0.6),
        _interview("Pflege", 0.4),
        _interview("Arbeitnehmervertretung", 0.7),
        _interview("Projektleitung", -0.5),
    ]
    item = build_consensus_item(
        mostly_supportive,
        section_index=1,
        topic="ungestaffelter Vollstart",
        evidence_ids=["ev_1", "ev_2", "ev_3", "ev_4"],
    )
    assert item is not None
    claim = (
        "Die Mehrheit der befragten Stakeholder-Rollen steht dem "
        "ungestaffelten Vollstart kritisch gegenüber."
    )
    result = classify_evidence(claim, item)
    assert result.verdict is EntailmentVerdict.CONTRADICTED


def test_the_contributing_interviews_stay_referenced():
    item = _built()
    assert item["contributing_evidence_ids"] == ["ev_1", "ev_2", "ev_3", "ev_4"]
    assert item["raw"]["role_families"] == sorted(item["raw"]["role_families"])


def test_the_cluster_count_is_reported_not_priced_in():
    """Vier Stimmen aus einer Familie sind schwächer als zwei aus zweien.

    Die Zahl steht im Item, damit der Leser sie sieht — sie fließt bewusst in
    keine Gewichtung ein (Echo Chamber Index im Referenzlauf: 0.8046).
    """
    item = _built()
    assert item["cluster_count"] == 4

    one_family = build_consensus_item(
        [_interview("Pflege", -0.6) for _ in range(4)],
        section_index=1,
        topic="Rollout",
        evidence_ids=["ev_1", "ev_2", "ev_3", "ev_4"],
    )
    assert one_family is not None
    assert one_family["cluster_count"] == 1
    # Der Anteil bleibt derselbe — nur die Streuung unterscheidet sich.
    assert one_family["raw"]["critical_share_percent"] == 100.0


# --- Was sie nicht darf ----------------------------------------------------

def test_the_count_is_never_a_stakeholder_voice():
    """Der Kern der Anker-4-Frage.

    Ein Aggregat, das mehrere Gruppen zusammenfasst und als `agent_quote`
    aufträte, würde `cross_stakeholder_for_high` mit einem einzigen Item
    erfüllen. Die Anker-Erfüllung muss über die einzeln gebundenen Interviews
    laufen.
    """
    item = _built()

    assert item["source_kind"] != EvidenceSourceKind.agent_quote.value
    assert _TYPE_TO_SOURCE_KIND["agent_interview_consensus"] != "agent_quote"
    assert item.get("persona_stakeholder_group") is None


def test_the_count_does_not_block_high_confidence():
    """`inferred` läge semantisch näher, wäre aber schädlich.

    Anker 5 verwirft *jedes* `inferred`-Item in einem high-Claim — ein
    Aggregat dieser Gattung würde einen sonst belegbaren Claim herunterstufen.
    """
    assert _built()["source_kind"] != EvidenceSourceKind.inferred.value


def test_the_count_still_shows_up_as_a_simulation_contribution():
    from app.contracts.report_contract import SIMULATION_SOURCE_KINDS

    kind = EvidenceSourceKind(_built()["source_kind"])
    assert kind in SIMULATION_SOURCE_KINDS


# --- Wann sie ausbleibt ----------------------------------------------------

@pytest.mark.parametrize("count", [0, 1, MIN_INTERVIEWS_FOR_CONSENSUS - 1])
def test_too_few_voices_produce_no_count(count: int):
    """Unter drei Stimmen ist "die Mehrheit" eine Aussage über zwei Personen."""
    assert build_consensus_item(
        FOUR_MOSTLY_CRITICAL[:count],
        section_index=1,
        topic="Rollout",
        evidence_ids=["ev"] * count,
    ) is None


def test_interviews_without_sentiment_produce_no_count():
    """Eine Auszählung ohne Richtung wäre eine Zahl ohne Aussage."""
    blank = [{"type": "agent_interview", "persona_role_family": "Pflege"} for _ in range(4)]
    assert build_consensus_item(
        blank, section_index=1, topic="Rollout", evidence_ids=["ev"] * 4
    ) is None


def test_ambivalent_voices_lower_the_share_instead_of_flipping_it():
    """Der Korridor zwischen den Schwellen ist Absicht.

    Eine Antwort ohne klare Richtung erhöht die Grundgesamtheit, zählt aber in
    keine der beiden Zahlen — sie schwächt die Mehrheitsaussage, statt sie
    umzudrehen.
    """
    item = build_consensus_item(
        [
            _interview("Ärztlicher Dienst", -0.6),
            _interview("Pflege", -0.4),
            _interview("Projektleitung", 0.0),
            _interview("Verwaltung", 0.05),
        ],
        section_index=1,
        topic="Rollout",
        evidence_ids=["ev_1", "ev_2", "ev_3", "ev_4"],
    )
    assert item is not None
    assert item["raw"]["critical"] == 2
    assert item["raw"]["supportive"] == 0
    assert item["raw"]["critical_share_percent"] == 50.0
