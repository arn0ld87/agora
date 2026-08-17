"""Regression #1217 — die Bindungsphase waehlt Kandidaten nach Relevanz.

Befundlage: In zwei vollstaendigen Laeufen wurde kein einziger von 163 bzw.
131 Claims an Evidence gebunden, obwohl der ``evidence_index`` 66 bzw. 79
Eintraege trug (davon 37 ``agent_quote`` und 20 ``seed_corpus``).

Ursache war die Kandidatenauswahl, nicht das Evidence-Gate:
``_build_claims_for_section`` reichte dem Binder ``_active_section_evidence[:10]``
— die zehn *zuerst erhobenen* Items der Section. Ein einziger
``insight_forge``-Call erzeugt bis zu 26 Items (10 Facts + 8 Entities +
8 Chains), das Fenster war also nach dem ersten Tool-Call gefuellt. Die
spaeter erhobenen Persona-Zitate (``interview_agents``, dritter Tool-Call)
und Seed-Treffer (``quick_search``, vierter) konnten nie gebunden werden.

Die Tests sitzen deshalb auf der Bindungsphase selbst und nicht auf einem
Symptom weiter oben: sie fahren ``_build_claims_for_section`` mit einem
deterministischen Embedder und pruefen, welche Evidence als Kandidat
ueberhaupt bewertet wird.

ADR-0002 bleibt unberuehrt: Threshold, Entailment-Urteil und
Confidence-Regeln entscheiden unveraendert. Getestet wird ausschliesslich,
dass das Gate den vorhandenen Beleg auch zu sehen bekommt.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.services.report_agent.evidence_candidates import EvidenceCandidatePool

# Der Beleg und der Claim teilen diese Kernaussage woertlich — genau der Fall
# aus #1217 (``ev_50bff96…`` lag woertlich im Testfall-Dokument).
CLAIM_TEXT = (
    "Dozenten berichten sechs bis neun Stunden unbezahlte Nacharbeit pro Woche "
    "und fordern eine verbindliche Entlastungsregelung."
)


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"\W+", text.lower()) if t]


def _bag_of_words_embedder(vocabulary: List[str]):
    """Deterministischer Embedder: Termfrequenz ueber ein festes Vokabular.

    Kein Netz, kein Modell — die Cosine-Werte sind damit reproduzierbar und
    das Verhalten haengt nur an der Wortueberschneidung.
    """

    def embed(text: str) -> List[float]:
        counts = {token: 0 for token in vocabulary}
        for token in _tokens(text):
            if token in counts:
                counts[token] += 1
        vector = [float(counts[token]) for token in vocabulary]
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector

    return embed


def _filler_item(index: int) -> Dict[str, Any]:
    """Ein Item aus dem ersten Tool-Call: thematisch daneben, aber zuerst da."""
    return {
        "evidence_id": f"ev_{index:032x}",
        "type": "graph_fact",
        "source": "report_tool",
        "source_kind": "graph_relation",
        "snippet": (
            f"Knoten {index} verweist auf Reichweite, Netzwerkdichte und "
            "Clusterbildung im Diskussionsgraphen."
        ),
    }


def _supporting_item(index: int, snippet: str) -> Dict[str, Any]:
    """Ein spaet erhobenes Item, das den Claim woertlich stuetzt."""
    return {
        "evidence_id": f"ev_{index:032x}",
        "type": "seed_document",
        "source": "report_tool",
        "source_kind": "seed_corpus",
        "snippet": snippet,
    }


SUPPORTING_SNIPPETS = (
    "Dozenten berichten sechs bis neun Stunden unbezahlte Nacharbeit pro Woche.",
    "Dozenten fordern eine verbindliche Entlastungsregelung fuer die unbezahlte "
    "Nacharbeit pro Woche.",
)


def _section_evidence() -> List[Dict[str, Any]]:
    """Zwoelf Items in Erhebungsreihenfolge — die Belege stehen hinten.

    Genau die Verteilung des realen Laufs: der erste Tool-Call fuellt die
    Liste mit Graph-Fakten, die belegenden Seed-Treffer kommen aus einem
    spaeteren Call.
    """
    items = [_filler_item(i) for i in range(1, 11)]
    items.append(_supporting_item(11, SUPPORTING_SNIPPETS[0]))
    items.append(_supporting_item(12, SUPPORTING_SNIPPETS[1]))
    return items


def _make_agent(evidence: List[Dict[str, Any]]):
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
    agent._current_section_index = 1
    agent._active_section_unresolved_evidence = []
    agent._active_section_evidence = evidence
    agent.evidence_map = {
        "evidence_index": {item["evidence_id"]: dict(item) for item in evidence},
        "global_evidence_refs": [],
    }
    return agent


@pytest.fixture
def agent_with_late_evidence(monkeypatch):
    from app.services.report_agent import ReportAgent

    evidence = _section_evidence()
    vocabulary = sorted({
        token
        for text in [CLAIM_TEXT, *SUPPORTING_SNIPPETS, *(i["snippet"] for i in evidence)]
        for token in _tokens(text)
    })
    embed = _bag_of_words_embedder(vocabulary)
    monkeypatch.setattr(ReportAgent, "_try_get_embedder", lambda self: embed)
    return _make_agent(evidence)


def test_late_evidence_reaches_the_binder(agent_with_late_evidence) -> None:
    """Der Beleg auf Position 11/12 wird gebunden, nicht weggeschnitten.

    Vor dem Fix sah der Binder nur ``_active_section_evidence[:10]`` — die
    beiden stuetzenden Items lagen ausserhalb und der Claim landete mit
    ``no_supporting_evidence`` in den Hypothesen.
    """
    claims = agent_with_late_evidence._build_claims_for_section(CLAIM_TEXT)

    assert len(claims) == 1
    bound_ids = {
        item.get("evidence_id")
        for item in claims[0]["evidence"]
        if item.get("supports_claim") is True
    }
    assert bound_ids == {f"ev_{11:032x}", f"ev_{12:032x}"}, (
        "Die stuetzende Evidence steht an Position 11/12 der Section-Liste und "
        f"muss den Binder erreichen — gebunden wurde: {claims[0]['evidence']!r}"
    )


def test_claim_survives_the_evidence_gate(agent_with_late_evidence) -> None:
    """Mit zwei stuetzenden Items passiert der Claim das Evidence-Gate.

    Das ist das Akzeptanzkriterium aus #1217 auf Ebene der Bindungsphase:
    ein Claim mit eindeutig passender Evidence wird als Claim persistiert und
    nicht zur Hypothese degradiert.
    """
    extracted = agent_with_late_evidence._build_claims_for_section(CLAIM_TEXT)
    claims, hypotheses, data_gaps, gate_decisions = (
        agent_with_late_evidence._finalize_section_claims(extracted)
    )

    violations = [entry.get("violation") for entry in gate_decisions]
    assert "no_supporting_evidence" not in violations, (
        f"Das Gate verwarf den Claim trotz vorhandener Evidence: {gate_decisions!r}"
    )
    assert len(claims) == 1, f"Erwartet 1 validierter Claim, bekam {claims!r}"
    assert not hypotheses, f"Kein Claim durfte zur Hypothese werden: {hypotheses!r}"
    assert not data_gaps, f"Keine Datenluecke erwartet: {data_gaps!r}"


def test_pool_orders_by_relevance_not_by_position() -> None:
    """Der Pool sortiert nach Cosine und behaelt bei Gleichstand die Reihenfolge."""
    evidence = _section_evidence()
    vocabulary = sorted({
        token
        for text in [CLAIM_TEXT, *(i["snippet"] for i in evidence)]
        for token in _tokens(text)
    })
    pool = EvidenceCandidatePool(evidence, _bag_of_words_embedder(vocabulary), limit=3)

    selected = pool.select(CLAIM_TEXT)

    assert [item["evidence_id"] for item in selected[:2]] == [
        f"ev_{11:032x}",
        f"ev_{12:032x}",
    ]


def test_pool_embeds_each_text_once_across_claims() -> None:
    """Der Cache traegt die Section, nicht den einzelnen Claim (#1187).

    Ohne ihn kostet die relevanzbasierte Auswahl pro Claim einen Embed-Call
    je Kandidat — genau die Nachbearbeitungsschleife, wegen der die Kappung
    urspruenglich eingezogen wurde.
    """
    evidence = _section_evidence()
    vocabulary = sorted({
        token
        for text in [CLAIM_TEXT, *(i["snippet"] for i in evidence)]
        for token in _tokens(text)
    })
    pool = EvidenceCandidatePool(evidence, _bag_of_words_embedder(vocabulary))

    for _ in range(5):
        pool.select(CLAIM_TEXT)

    assert pool.embed_calls == len(evidence) + 1, (
        f"Erwartet {len(evidence)} Kandidaten- plus 1 Claim-Embedding, "
        f"gezaehlt wurden {pool.embed_calls}"
    )


def test_pool_dedupliziert_ueberlappende_direct_und_global_items() -> None:
    """#1318: dieselbe evidence_id aus direct_items UND global_items darf
    nur einmal im Pool landen, sonst zaehlt sie doppelt im Confidence-Mittel.

    Reihenfolge bleibt stabil: das erste Vorkommen (aus direct_items)
    gewinnt.
    """
    shared = _filler_item(1)
    direct_items = [shared, _filler_item(2)]
    global_items = [dict(shared), _filler_item(3)]

    pool = EvidenceCandidatePool(direct_items + global_items, lambda text: [1.0, 0.0])

    ids = [item["evidence_id"] for item, _text in pool._items]
    assert ids == [
        f"ev_{1:032x}",
        f"ev_{2:032x}",
        f"ev_{3:032x}",
    ], f"Erwartet je evidence_id genau einmal in Erhebungsreihenfolge, bekam: {ids!r}"


def test_pool_behaelt_items_ohne_evidence_id_alle() -> None:
    """Items ohne evidence_id haben keine Identitaet zum Abgleichen und
    duerfen deshalb nicht stillschweigend als Duplikate verworfen werden."""
    without_id_a = {"snippet": "Ein Item ohne evidence_id, Variante A."}
    without_id_b = {"snippet": "Ein Item ohne evidence_id, Variante B."}

    pool = EvidenceCandidatePool(
        [without_id_a, without_id_b], lambda text: [1.0, 0.0]
    )

    assert len(pool._items) == 2, (
        f"Beide Items ohne evidence_id muessen erhalten bleiben, "
        f"gezaehlt wurden {len(pool._items)}"
    )


def test_pool_behandelt_leere_evidence_id_nicht_als_identitaet() -> None:
    """Ein leerer evidence_id-String ist keine Identitaet.

    Wuerde der Dedup ihn wie eine ID behandeln, fielen alle Items mit
    leerem Feld auf ein einziges zusammen — ein stiller Datenverlust, der
    schwerer waere als das Duplikat, das #1318 beseitigt.
    """
    items = [
        {"evidence_id": "", "snippet": "Erstes Item mit leerer evidence_id."},
        {"evidence_id": "", "snippet": "Zweites Item mit leerer evidence_id."},
    ]

    pool = EvidenceCandidatePool(items, lambda text: [1.0, 0.0])

    assert len(pool._items) == 2


def test_failed_embedding_is_not_retried_per_claim() -> None:
    """Ein deterministisch scheiterndes Item kostet genau einen Versuch.

    Ohne den Cache-Eintrag fuer den Fehlschlag wiederholt jeder Claim der
    Section denselben Provider-Aufruf samt Retries und Timeouts — ein
    einzelnes defektes Evidence-Item wuerde die Nachbearbeitung ausbremsen.
    """
    broken = {
        "evidence_id": f"ev_{99:032x}",
        "type": "web_fetch",
        "source": "report_tool",
        "snippet": "Ein Snippet, dessen Einbettung beim Provider scheitert.",
    }
    attempts: List[str] = []

    def flaky_embed(text: str) -> List[float]:
        attempts.append(text)
        if text == broken["snippet"]:
            raise RuntimeError("context window exceeded")
        return [1.0, 0.0]

    pool = EvidenceCandidatePool([broken, _filler_item(1)], flaky_embed)

    for _ in range(4):
        assert pool.select(CLAIM_TEXT), "der intakte Kandidat muss weiterhin kommen"

    assert attempts.count(broken["snippet"]) == 1, (
        f"Der scheiternde Kandidat wurde {attempts.count(broken['snippet'])}x "
        "eingebettet statt genau einmal"
    )
