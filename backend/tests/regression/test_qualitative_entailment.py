"""Golden Cases zum qualitativen Entailment-Pfad (Issue #1357).

Alle Fälle stammen aus einem vollständigen 7-Sektionen-Referenzlauf, in dem
kein einziges `SUPPORTED` aus dem numerischen Pfad kam: alle 24 entstanden im
rein lexikalischen Zweig von Regel 3, mit Containment-Median 1.00 gegen
Deckungs-Median 0.21. Persona-Interviews banden dabei nie — ihre lexikalische
Deckung liegt im Median bei 0.02.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.services.evidence_binder import bind_evidence_to_claim
from app.services.evidence_entailment import (
    QUALITATIVE_RELATED_THRESHOLD,
    QUALITATIVE_SUPPORT_THRESHOLD,
    RETRIEVAL_RELEVANCE_THRESHOLD,
    EntailmentVerdict,
    classify_evidence,
    coverage_ratio,
)

# --- Der AURORA-Fall -------------------------------------------------------

#: Wortlaut aus dem Referenzlauf. Gemessen gegen das Snippet unten:
#: Containment 0.50 — über der alten Schwelle PREDICATE_MATCH_THRESHOLD — bei
#: einer Deckung von 0.21. Genau so wurde die Projektankündigung zum Beleg
#: einer Risikobewertung.
AURORA_CLAIM = (
    "Die simulationsgestützte Evaluation der Entscheidungsoptionen für das "
    "Projekt AURORA (Nexora Triage Assist) im Städtischen Klinikverbund "
    "Falkenbrück ergibt gravierende Risiken für die Patientensicherheit."
)
AURORA_EVIDENCE: Dict[str, Any] = {
    "snippet": (
        "Der Städtische Klinikverbund Falkenbrück plant unter dem Projektnamen "
        "AURORA die Einführung des Systems Nexora Triage Assist."
    ),
    "source_kind": "seed_corpus",
}


def test_a_project_announcement_does_not_prove_a_risk_assessment():
    """Der Gründungsfall von #1357.

    Die Ankündigung eines Projekts belegt keine Aussage über dessen Risiken.
    Unter Containment galt sie als Beleg, weil ihre Wörter sämtlich im Claim
    vorkamen — die Deckungsrichtung war verkehrt herum.
    """
    result = classify_evidence(AURORA_CLAIM, AURORA_EVIDENCE)

    assert result.verdict is not EntailmentVerdict.SUPPORTED
    assert "high_lexical_overlap" not in result.checks


def test_the_old_containment_measure_would_still_call_it_a_match():
    """Warum der Fall ohne Richtungswechsel nicht zu beheben war.

    Containment erreicht die alte Bindungsschwelle, die Deckung bleibt weit
    darunter. Wer nur die Schwelle anhebt, verliert die belegten Bindungen
    mit — der Referenzlauf zeigte 4 von 16 Claims bei Schwelle 0.50.
    """
    from app.services.evidence_entailment import (
        PREDICATE_MATCH_THRESHOLD,
        _overlap_ratio,
    )

    containment = _overlap_ratio(AURORA_CLAIM, AURORA_EVIDENCE["snippet"])
    coverage = coverage_ratio(AURORA_CLAIM, AURORA_EVIDENCE["snippet"])

    assert containment >= PREDICATE_MATCH_THRESHOLD
    assert coverage < QUALITATIVE_SUPPORT_THRESHOLD
    assert containment > coverage


# --- Die drei Zonen --------------------------------------------------------

def test_high_coverage_supports_without_asking_anyone():
    claim = "Die Betriebsvereinbarung zur Systemeinführung ist abgeschlossen."
    evidence = {
        "snippet": "Die Betriebsvereinbarung zur Systemeinführung ist abgeschlossen.",
        "source_kind": "seed_corpus",
    }

    def judge(_claim: str, _evidence: str) -> str:  # pragma: no cover
        raise AssertionError("Der Judge darf oberhalb der Schwelle nicht laufen")

    result = classify_evidence(claim, evidence, judge=judge)
    assert result.verdict is EntailmentVerdict.SUPPORTED
    assert "high_claim_coverage" in result.checks


def test_the_grey_zone_asks_the_judge():
    claim = (
        "Die ärztliche Leitung hält die Erprobung für unzureichend, um die "
        "Betriebsreife des Systems zu belegen."
    )
    evidence = {
        "snippet": (
            "Das ist eine begrenzte Erprobung, kein Nachweis der Betriebsreife."
        ),
        "source_kind": "agent_quote",
        "persona_stakeholder_group": "Ärztliche Leitung",
    }
    asked: list[tuple[str, str]] = []

    def judge(claim_text: str, evidence_text: str) -> str:
        asked.append((claim_text, evidence_text))
        return "SUPPORTED"

    result = classify_evidence(claim, evidence, judge=judge)

    assert asked, "Die Grauzone muss den Judge befragen"
    assert result.verdict is EntailmentVerdict.SUPPORTED
    assert "judge" in result.checks


def test_without_a_judge_the_grey_zone_stays_unproven():
    """Ausfall macht den Report vorsichtiger, nicht falscher."""
    claim = (
        "Die ärztliche Leitung hält die Erprobung für unzureichend, um die "
        "Betriebsreife des Systems zu belegen."
    )
    evidence = {
        "snippet": "Das ist eine begrenzte Erprobung, kein Nachweis der Betriebsreife.",
        "source_kind": "agent_quote",
        "persona_stakeholder_group": "Ärztliche Leitung",
    }

    result = classify_evidence(claim, evidence)
    assert result.verdict is EntailmentVerdict.RELATED_ONLY
    assert "grey_zone_unjudged" in result.checks


def test_a_failing_judge_falls_back_to_the_rule_path():
    claim = (
        "Die ärztliche Leitung hält die Erprobung für unzureichend, um die "
        "Betriebsreife des Systems zu belegen."
    )
    evidence = {
        "snippet": "Das ist eine begrenzte Erprobung, kein Nachweis der Betriebsreife.",
        "source_kind": "agent_quote",
        "persona_stakeholder_group": "Ärztliche Leitung",
    }

    def judge(_claim: str, _evidence: str) -> str:
        raise RuntimeError("Provider nicht erreichbar")

    result = classify_evidence(claim, evidence, judge=judge)
    assert "judge_failed" in result.checks
    assert result.verdict is EntailmentVerdict.RELATED_ONLY


# --- Der Retrieval-Vorrang -------------------------------------------------

INTERVIEW_CLAIM = (
    "Die Beschäftigtenvertretung fordert verbindliche Regeln zur Auswertung "
    "der im System anfallenden Leistungsdaten."
)
INTERVIEW_EVIDENCE: Dict[str, Any] = {
    "snippet": (
        "Solange nicht schriftlich steht, wer welche Kennzahlen sehen darf, "
        "trägt der Betriebsrat das nicht mit."
    ),
    "quote": "Solange das nicht schriftlich steht, tragen wir das nicht mit.",
    "type": "agent_interview",
    "source_kind": "agent_quote",
    "persona_stakeholder_group": "Betriebsrat",
    "persona_role_family": "Arbeitnehmervertretung",
}


def test_an_interview_says_the_same_thing_in_other_words():
    """Die Messung, an der die Diagnose hängt.

    Ein Interviewzitat trifft den Claim inhaltlich und verfehlt ihn
    lexikalisch. Ohne Retrieval-Signal fällt es unter beide Schwellen.
    """
    coverage = coverage_ratio(INTERVIEW_CLAIM, INTERVIEW_EVIDENCE["snippet"])
    assert coverage < QUALITATIVE_RELATED_THRESHOLD


def test_a_retrieved_interview_reaches_the_judge_instead_of_being_dropped():
    """Ohne diesen Vorrang wäre `high` strukturell unerreichbar.

    `agent_interview` wird auf `agent_quote` abgebildet, und
    `cross_stakeholder_for_high` verlangt genau diese Gattung. Solange
    Interviews am lexikalischen Filter scheitern, kann kein Claim je `high`
    werden — im Referenzlauf waren alle 16 Claims `low`.
    """
    asked: list[str] = []

    def judge(_claim: str, evidence_text: str) -> str:
        asked.append(evidence_text)
        return "SUPPORTED"

    result = classify_evidence(
        INTERVIEW_CLAIM,
        INTERVIEW_EVIDENCE,
        judge=judge,
        retrieval_score=0.72,
    )

    assert asked, "Ein semantisch gefundenes Interview muss geprüft werden"
    assert result.verdict is EntailmentVerdict.SUPPORTED
    assert "retrieval_relevant" in result.checks


def test_a_weak_retrieval_score_does_not_open_the_gate():
    """Der Vorrang gilt nur für einen belastbaren Treffer."""
    result = classify_evidence(
        INTERVIEW_CLAIM,
        INTERVIEW_EVIDENCE,
        retrieval_score=RETRIEVAL_RELEVANCE_THRESHOLD - 0.05,
    )
    assert "retrieval_relevant" not in result.checks


# --- Das Judge-Budget ------------------------------------------------------

def test_the_binder_classifies_only_the_candidates_it_keeps():
    """Das Judge-Budget hängt an `top_k`, nicht an der Kandidatenzahl.

    Der Binder klassifiziert seit #1357 erst nach dem Kürzen. Vorher lief der
    Entailment-Check über jeden Kandidaten oberhalb der Retrieval-Schwelle —
    bei einem Claim mit zwanzig Treffern also zwanzig mögliche Judge-Calls
    für fünf behaltene Bindungen.
    """
    claim = "Die Systemeinführung erzeugt Vorbehalte in mehreren Bereichen."
    candidates = [
        {"evidence_id": f"ev_{n}", "snippet": f"Vorbehalt Nummer {n} zur Systemeinführung."}
        for n in range(12)
    ]
    calls: list[str] = []

    def judge(_claim: str, evidence_text: str) -> str:
        calls.append(evidence_text)
        return "RELATED_ONLY"

    def embed(text: str) -> list[float]:
        # Konstanter Vektor: alle Kandidaten liegen über der Schwelle, die
        # Auswahl entscheidet also allein die Kürzung.
        return [1.0, 0.0]

    bound = bind_evidence_to_claim(
        claim, candidates, embed, threshold=0.5, top_k=3, judge=judge
    )

    assert len(bound) == 3
    assert len(calls) <= 3


# --- Der Judge am Provider ------------------------------------------------

class _ProseOnlyClient:
    """Ein Provider, der sich nicht an das JSON-Schema hält.

    Vier der fünf im Entwicklungssetup verfügbaren Ollama-Cloud-Modelle
    verhalten sich so — mit ``LLM_DISABLE_JSON_MODE`` fällt der erzwungene
    Modus ohnehin weg. Ohne den Freitext-Versuch wäre der Judge dort
    dauerhaft im ``judge_failed``-Pfad.
    """

    def __init__(self, prose: str) -> None:
        self.prose = prose
        self.chat_calls = 0

    def chat_json(self, **_kwargs: Any) -> Dict[str, Any]:
        raise ValueError("Invalid JSON format from LLM")

    def chat(self, **_kwargs: Any) -> str:
        self.chat_calls += 1
        return self.prose


def test_a_prose_answer_still_yields_a_verdict():
    from app.services.llm_entailment_judge import build_llm_judge

    client = _ProseOnlyClient(
        "**Urteil:** RELATED_ONLY\n\n**Begründung:** Die Evidence thematisiert "
        "zwar die Voraussetzungen, nennt aber keine der im Claim genannten "
        "Befunde."
    )
    verdict = build_llm_judge(client)("Ein Claim.", "Eine Evidence.")  # type: ignore[arg-type]

    assert verdict == "RELATED_ONLY"
    assert client.chat_calls == 1


def test_an_ambiguous_prose_answer_is_not_guessed():
    """Zwei Urteilsnamen im Text heißen: kein Urteil.

    Der Aufrufer sieht dieselbe Exception wie zuvor und fällt auf den
    Regelpfad — raten wäre schlimmer als nicht wissen.
    """
    from app.services.llm_entailment_judge import build_llm_judge

    client = _ProseOnlyClient("Zwischen SUPPORTED und CONTRADICTED ist es schwer.")

    with pytest.raises(ValueError):
        build_llm_judge(client)("Ein Claim.", "Eine Evidence.")  # type: ignore[arg-type]


def test_an_empty_answer_is_not_a_verdict():
    """Reasoning-Modelle liefern gelegentlich nur den Denkteil, also nichts."""
    from app.services.llm_entailment_judge import build_llm_judge

    with pytest.raises(ValueError):
        build_llm_judge(_ProseOnlyClient(""))("Ein Claim.", "Eine Evidence.")  # type: ignore[arg-type]


@pytest.mark.parametrize("verdict", ["SUPPORTED", "CONTRADICTED", "RELATED_ONLY"])
def test_every_binding_carries_its_verdict_and_reason(verdict: str):
    claim = "Die Systemeinführung erzeugt Vorbehalte in mehreren Bereichen."
    candidates = [{"evidence_id": "ev_1", "snippet": "Ein Vorbehalt zur Systemeinführung."}]

    bound = bind_evidence_to_claim(
        claim,
        candidates,
        lambda _text: [1.0, 0.0],
        threshold=0.5,
        top_k=5,
        judge=lambda _c, _e: verdict,
    )

    assert bound[0]["entailment"]
    assert bound[0]["entailment_reason"]
    assert bound[0]["supports_claim"] is (bound[0]["entailment"] == "SUPPORTED")
