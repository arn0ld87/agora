"""Die Persona nennt ihre Haltung, und sie kommt am Evidence-Item an (#1363).

``sentiment_score`` stand im Vertrag, wurde von ``confidence_calculator``
gelesen — und war im 7-Sektionen-Referenzlauf bei **0 von 99 Items** gesetzt.
Jede Mengenaussage ueber Stakeholder war damit strukturell unbelegbar, und die
Widerspruchs-Penalty (``std > 0.6 → -0.2``) lief seit ihrer Einfuehrung leer.

Der zweite Teil dieser Datei prueft deshalb den **echten Erzeugerpfad**, nicht
nur die Parsing-Funktion: ein Feld, das nur in Fixtures gesetzt ist, ist genau
der Fehler, an dem PR #1362 gescheitert ist.
"""

from __future__ import annotations

import re

import pytest

from app.services.graph.graph_dtos import AgentInterview, InterviewResult
from app.services.interview_stance import (
    STANCE_PROMPT_REQUIREMENT,
    extract_stance,
)
from tests.services.test_report_tool_evidence import _make_agent


# --- Die Haltungszeile lesen -----------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("STANCE: -0.6", -0.6),
    ("stance: 0.8", 0.8),
    ("STANCE:-1", -1.0),
    ("STANCE = 0,4", 0.4),
    ("  STANCE: +0.5  ", 0.5),
    ("> STANCE: -0.3", -0.3),
])
def test_the_line_is_read_in_its_usual_variations(line: str, expected: float):
    value, _rest = extract_stance(f"Meine Antwort.\n\n{line}")
    assert value == pytest.approx(expected)


def test_the_line_is_removed_from_the_answer():
    """Sonst stuende "STANCE: -0.6" im persistierten Zitat und im Bericht."""
    _value, rest = extract_stance("Ich lehne das ab.\n\nSTANCE: -0.6")
    assert rest == "Ich lehne das ab."
    assert "STANCE" not in rest


def test_a_missing_line_is_not_an_abstention():
    """``None`` heisst "nicht erhoben", nicht "neutral".

    Eine Antwort ohne Richtung als 0.0 zu zaehlen fuellte die Grundgesamtheit
    mit Stimmen, die niemand abgegeben hat.
    """
    value, rest = extract_stance("Ich habe dazu eine lange Meinung.")
    assert value is None
    assert rest == "Ich habe dazu eine lange Meinung."


def test_values_beyond_the_scale_are_clamped_not_rejected():
    """Der Vertrag erlaubt nur [-1, 1]; ein Ausreisser darf das Item nicht kippen."""
    assert extract_stance("x\nSTANCE: -4.5")[0] == -1.0
    assert extract_stance("x\nSTANCE: 7")[0] == 1.0


def test_the_last_line_wins_when_the_model_repeats_itself():
    """Modelle echoen die Anweisung gern; gezaehlt wird, wo sie verlangt war."""
    response = "STANCE: 0.0 (so soll ich antworten)\n\nMeine Antwort.\n\nSTANCE: -0.9"
    assert extract_stance(response)[0] == pytest.approx(-0.9)


def test_a_number_inside_prose_is_not_a_stance():
    """Die Form muss eine eigene Zeile sein, sonst faengt sie Fliesstext ein."""
    assert extract_stance("Meine STANCE: -0.6 ist klar, aber ich bleibe dabei.")[0] is None


def test_an_empty_answer_does_not_raise():
    assert extract_stance("") == (None, "")


def test_the_prompt_actually_asks_for_the_line():
    """Ohne die Bitte im Prompt kommt keine Zeile — und das Feld bliebe leer."""
    assert "STANCE:" in STANCE_PROMPT_REQUIREMENT
    assert "-1.0" in STANCE_PROMPT_REQUIREMENT and "1.0" in STANCE_PROMPT_REQUIREMENT
    # Nur einmal, am Ende: mehrfach genannte Zeilen machen das Parsen zur Wette.
    assert "only once" in STANCE_PROMPT_REQUIREMENT


def test_the_prompt_requirement_is_wired_into_the_interview_prompt():
    from app.services import graph_tools

    source = graph_tools.__file__
    with open(source, encoding="utf-8") as handle:
        assert "STANCE_PROMPT_REQUIREMENT" in handle.read()


# --- Der Erzeugerpfad ------------------------------------------------------

def _interview(response: str, stance: float | None) -> AgentInterview:
    return AgentInterview(
        agent_name="Pflegedienstleitung",
        agent_role="Pflege",
        agent_bio="Bio",
        question="Was halten Sie vom Vollstart?",
        response=response,
        key_quotes=[],
        topic_stance=stance,
    )


def _record(interview: AgentInterview) -> dict:
    agent = _make_agent()
    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=InterviewResult(
            interview_topic="Vollstart",
            interview_questions=["Was halten Sie vom Vollstart?"],
            interviews=[interview],
        ),
        rendered_result="",
        section_index=1,
    )
    records = [
        r for r in (agent.evidence_map or {})["evidence_index"].values()
        if r["type"] == "agent_interview"
    ]
    assert len(records) == 1
    return records[0]


def test_the_stance_arrives_on_the_persisted_evidence_item():
    """Der Test, den #1362 gebraucht haette.

    Dort war ``sentiment_score`` nur in den Fixtures gesetzt; im echten Lauf
    trug es kein einziges von 99 Items.
    """
    record = _record(_interview("Ich sehe erhebliche Risiken.", -0.7))
    assert record["topic_stance"] == pytest.approx(-0.7)


def test_an_interview_without_a_stance_keeps_the_field_empty():
    record = _record(_interview("Ich sehe erhebliche Risiken.", None))
    assert record.get("topic_stance") is None


def test_the_stance_never_leaks_into_the_persisted_text():
    """Weder ins Zitat noch in den Snippet — der Leser sieht Prosa, keine Marke."""
    record = _record(_interview("Ich sehe erhebliche Risiken.", -0.7))
    assert not re.search(r"STANCE", record.get("quote") or "", re.IGNORECASE)
    assert not re.search(r"STANCE", record.get("snippet") or "", re.IGNORECASE)


def test_the_stance_never_lands_in_the_snippet_sentiment_field():
    """Die Themenhaltung darf die Widerspruchs-Penalty eines Claims nicht ausloesen.

    ``sentiment_score`` beschreibt den Tenor des Snippets und geht in
    ``_has_contradiction`` ein. Zwei Personas koennen denselben Claim stuetzen
    — beide Snippets zustimmend — und dabei gegensaetzlich zum Thema stehen.
    Fiele die Themenhaltung in dasselbe Feld, wuerde genau der Claim
    abgewertet, ueber den sie einig sind.
    """
    record = _record(_interview("Schulung ist noetig.", -0.8))
    assert record["topic_stance"] == pytest.approx(-0.8)
    assert record.get("sentiment_score") is None


def test_opposing_topic_stances_do_not_trigger_the_contradiction_penalty():
    """Der Fall aus dem Review, durchgerechnet.

    Zwei Belege, die denselben Claim stuetzen, mit entgegengesetzter Haltung
    zum Rollout. ``_has_contradiction`` feuert bei ``min < -0.3 UND
    max > +0.3`` — ueber ``sentiment_score``, das hier leer bleibt.
    """
    from app.services.confidence_calculator import (
        _extract_sentiment_scores,
        _has_contradiction,
    )

    evidence = [
        {"topic_stance": -0.8, "supports_claim": True},
        {"topic_stance": 0.7, "supports_claim": True},
    ]
    assert _extract_sentiment_scores(evidence) == []
    assert _has_contradiction(_extract_sentiment_scores(evidence)) is False
    # Gegenprobe: im alten Feld haette dieselbe Spanne die Penalty ausgeloest.
    assert _has_contradiction([-0.8, 0.7]) is True
