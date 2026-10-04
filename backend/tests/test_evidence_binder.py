"""S4a — Tests für claim-spezifisches Evidence-Binding.

Verwenden einen deterministischen Fake-Embedder, der jedem Wort eine
feste Achse im Vektor zuordnet. Damit hat „NRW Pflichtfach“ hohe
Cosine-Ähnlichkeit zu Items, die dieselben Wörter enthalten, und 0
zu komplett anderen Texten. Reicht aus, um die Filter-/Sortier-
Semantik zu testen, ohne Ollama oder ein echtes Embedding-Modell.
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Dict, List

from app.services.evidence_binder import (
    MAX_RETRIEVAL_WINDOWS,
    _cosine,
    bind_evidence_to_claim,
    candidate_text,
)
from app.services.evidence_entailment import _evidence_text
from app.services.report_agent.data_gap import _pool_texts


def _vocab_embedder(dim: int = 16):
    vocab: Dict[str, int] = {}

    def embed(text: str) -> List[float]:
        vec = [0.0] * dim
        for token in (text or "").lower().split():
            if token not in vocab:
                vocab[token] = len(vocab) % dim
            vec[vocab[token]] += 1.0
        return vec

    return embed


def test_returns_empty_for_no_claim_or_candidates():
    embed = _vocab_embedder()
    assert bind_evidence_to_claim("", [{"snippet": "x"}], embed) == []
    assert bind_evidence_to_claim("text", [], embed) == []


def test_filters_below_threshold_and_sorts_descending():
    embed = _vocab_embedder()
    candidates = [
        {"snippet": "NRW beschloss das Pflichtfach KIDM"},  # match
        {"snippet": "Bayern plant nichts dergleichen"},  # off-topic
        {"snippet": "NRW KIDM Pflichtfach Curriculum"},  # very strong match
    ]
    result = bind_evidence_to_claim(
        "NRW Pflichtfach KIDM",
        candidates,
        embed,
        threshold=0.5,
    )
    assert len(result) == 2
    assert result[0]["match_score"] >= result[1]["match_score"]
    snippets = {r["snippet"] for r in result}
    assert "Bayern plant nichts dergleichen" not in snippets


def test_top_k_truncates():
    embed = _vocab_embedder()
    cands = [{"snippet": f"NRW Pflichtfach KIDM Curriculum item{i}"} for i in range(10)]
    result = bind_evidence_to_claim(
        "NRW Pflichtfach KIDM",
        cands,
        embed,
        threshold=0.0,
        top_k=3,
    )
    assert len(result) == 3
    for item in result:
        assert "match_score" in item
        assert item["supports_claim"] is True


def test_uses_raw_content_when_snippet_missing():
    embed = _vocab_embedder()
    cands = [
        {"raw": {"content": "NRW Pflichtfach KIDM"}, "type": "graph_fact"},
        {"raw": {"content": "irrelevant content goes here"}, "type": "graph_fact"},
    ]
    result = bind_evidence_to_claim("NRW Pflichtfach KIDM", cands, embed, threshold=0.5)
    assert len(result) == 1
    assert result[0]["raw"]["content"].startswith("NRW")


def test_does_not_mutate_input_candidates():
    embed = _vocab_embedder()
    cand = {"snippet": "NRW Pflichtfach KIDM", "type": "graph_fact"}
    cands = [cand]
    out = bind_evidence_to_claim("NRW Pflichtfach KIDM", cands, embed, threshold=0.0)
    assert "match_score" in out[0]
    assert "match_score" not in cand


# --- #1766: der volle Interviewtext ist bindbar --------------------------------

_TARGET = (
    "Der Landfrauenverband verweist auf die fehlende nächtliche Busverbindung "
    "von Moorhagen nach Hollerau."
)

_FILLER = [
    "Die Gemeindeverwaltung hat im Frühjahr mehrere Gesprächsrunden mit Vereinen veranstaltet.",
    "Besonders ausführlich wurde über die Öffnungszeiten der Bibliothek gesprochen.",
    "Teilnehmerinnen schilderten, wie sich der Alltag im Dorf über die Jahre verändert hat.",
    "Der Sportverein lobte die neue Turnhalle und erinnerte an die lange Planungsphase.",
    "Die Feuerwehr betonte die gute Zusammenarbeit mit den Nachbargemeinden bei Einsätzen.",
    "Ein Gastwirt wünschte sich mehr Unterstützung bei der Gestaltung des Marktplatzes.",
    "Die Schule berichtete von einem lebendigen Austausch mit den Eltern im Förderverein.",
    "Der Chor kündigte ein Herbstkonzert in der Kirche an und lud alle Interessierten ein.",
]


def _interview_response(*, with_target: bool) -> str:
    """Rund 2400 Zeichen; der Zielsatz beginnt bei etwa Zeichen 650."""
    sentences: List[str] = []
    length = 0
    index = 0
    while length < 650:
        sentence = _FILLER[index % len(_FILLER)]
        sentences.append(sentence)
        length += len(sentence) + 1
        index += 1
    sentences.append(_TARGET if with_target else _FILLER[index % len(_FILLER)])
    index += 1
    length += len(sentences[-1]) + 1
    while length < 2400:
        sentence = _FILLER[index % len(_FILLER)]
        sentences.append(sentence)
        length += len(sentence) + 1
        index += 1
    return " ".join(sentences)


def _interview_item(*, with_target: bool = True) -> Dict[str, Any]:
    """Ein Persona-Interview, wie ``ReportAgent`` es registriert: gekürzt + ``raw``."""
    response = _interview_response(with_target=with_target)
    return {
        "evidence_id": "ev_interview_1",
        "source_kind": "persona_interview",
        "snippet": response[:300] + "…",
        "quote": response[:500] + "…",
        "raw": {
            "agent_name": "Landfrauenverband",
            "question": "Wie bewerten Sie die Anbindung im Nahverkehr?",
            "response": response,
        },
    }


def _bow_embedder(dim: int = 4096):
    def embed(text: str) -> List[float]:
        vec = [0.0] * dim
        for token in re.findall(r"\w+", (text or "").lower()):
            vec[zlib.crc32(token.encode("utf-8")) % dim] += 1.0
        return vec

    return embed


def _supporting_judge(claim: str, evidence_text: str) -> str:
    return "SUPPORTED"


def test_interview_answer_beyond_snippet_is_bindable():
    """Eine Aussage bei Zeichen ~650 hatte im Referenzlauf keinen Bindungskandidaten.

    ``snippet`` und ``quote`` sind gekürzt, die volle Antwort steht in
    ``raw["response"]``. Der Vergleichstext war 303 Zeichen lang.
    """
    item = _interview_item()
    assert item["raw"]["response"].index(_TARGET) >= 600

    result = bind_evidence_to_claim(
        _TARGET, [item], _bow_embedder(), threshold=0.4, judge=_supporting_judge
    )

    assert any(entry.get("supports_claim") is True for entry in result)


def test_interview_without_the_statement_does_not_support_the_claim():
    """Gegenprobe: derselbe Aufbau ohne den Zielsatz bindet nichts."""
    item = _interview_item(with_target=False)

    result = bind_evidence_to_claim(
        _TARGET, [item], _bow_embedder(), threshold=0.4, judge=_supporting_judge
    )

    assert not any(entry.get("supports_claim") is True for entry in result)


def test_long_text_is_scored_by_sentence_windows_not_diluted_by_the_whole_text():
    """Der Retrieval-Score eines langen Texts ist der beste Satzfenster-Score."""
    item = _interview_item()
    embed = _bow_embedder()
    diluted = _cosine(embed(_TARGET), embed(candidate_text(item)))

    result = bind_evidence_to_claim(
        _TARGET, [item], embed, threshold=0.4, judge=_supporting_judge
    )

    assert diluted < 0.4
    assert result and result[0]["retrieval_score"] >= 0.4


def test_candidate_pool_preselection_uses_the_window_score_for_long_interviews():
    """Die Vorauswahl darf ein langes Interview nicht an der Cosine-Verdünnung verlieren.

    Ohne Fensterscore läge die Antwort mit ~0.2 hinter einem kurzen Item, das
    nur zwei Wörter teilt (~0.4), und fiele bei ``limit=1`` heraus, bevor der
    Binder sie sieht.
    """
    from app.services.report_agent.evidence_candidates import EvidenceCandidatePool

    distractor = {
        "evidence_id": "ev_short",
        "source_kind": "seed_corpus",
        "snippet": "Busverbindung Moorhagen",
    }
    interview = _interview_item()
    pool = EvidenceCandidatePool([distractor, interview], _bow_embedder(), limit=1)

    selected = pool.select(_TARGET)

    assert [entry["evidence_id"] for entry in selected] == ["ev_interview_1"]


def test_window_embedding_calls_stay_bounded():
    """Ein langes Item kostet höchstens Kurztext + 12 Fenster an Embeddings."""
    calls: List[str] = []
    inner = _bow_embedder()

    def counting_embed(text: str) -> List[float]:
        calls.append(text)
        return inner(text)

    bind_evidence_to_claim(
        _TARGET, [_interview_item()], counting_embed, threshold=0.4, judge=_supporting_judge
    )

    # Claim + Kurztext + höchstens 12 Fenster.
    assert len(calls) <= 1 + 1 + MAX_RETRIEVAL_WINDOWS


def test_item_text_projections_agree_and_contain_the_full_answer():
    """Bindung, Entailment und Data-Gap lesen dieselbe Textprojektion."""
    interview = _interview_item()
    seed = {
        "evidence_id": "ev_seed_1",
        "source_kind": "seed_corpus",
        "snippet": "Der Projektplan fordert eine Schulung vor dem Start des Betriebs …",
        "value": "Schulung vor Betriebsstart",
        "raw": {
            "content": (
                "Der Projektplan fordert eine Schulung vor dem Start des Betriebs "
                "und eine Einweisung der Verwaltung in die neuen Abläufe."
            ),
            "name": "Projektplan",
        },
    }

    for item in (interview, seed):
        text = candidate_text(item)
        assert text == _evidence_text(item)
        assert text == _pool_texts([item])[0]

    interview_text = candidate_text(interview)
    assert interview["raw"]["response"] in interview_text
    assert interview["raw"]["question"] not in interview_text
    # snippet und quote sind gekürzte Kopien der Antwort und entfallen.
    assert interview_text == interview["raw"]["response"]
    assert seed["raw"]["content"] in candidate_text(seed)
