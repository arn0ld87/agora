"""S4a — Tests für claim-spezifisches Evidence-Binding.

Verwenden einen deterministischen Fake-Embedder, der jedem Wort eine
feste Achse im Vektor zuordnet. Damit hat „NRW Pflichtfach" hohe
Cosine-Ähnlichkeit zu Items, die dieselben Wörter enthalten, und 0
zu komplett anderen Texten. Reicht aus, um die Filter-/Sortier-
Semantik zu testen, ohne Ollama oder ein echtes Embedding-Modell.
"""

from __future__ import annotations

from typing import Dict, List

from app.services.evidence_binder import bind_evidence_to_claim


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
