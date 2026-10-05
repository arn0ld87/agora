"""Issue #1778 — Simulationsbeiträge erreichen die Entailment-Stufe.

Im Abnahmelauf ``report_89d20c11edc1`` lagen 29 Simulationsaktionen im
Belegindex, aber nur 7 wurden je einem Claim vorgelegt. Zwei Gründe im
Retrieval:

* Der Vergleichstext eines Beitrags begann mit der Metabeschreibung
  („<Name> CREATE_COMMENT on reddit in round 9:") und endete mit dem
  Aktionstyp. Beides drückt den Cosine-Wert gegen einen Claim.
* Interviews und Beiträge teilten sich fünf Plätze. Ein Interview wird über
  das beste von bis zu zwölf Satzfenstern bewertet und verdrängte die Beiträge.

Die Tests prüfen, dass ein Beitrag über der Schwelle geprüft wird — und dass
die Prüfung selbst nicht gelockert ist.
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Dict, List

from app.services.evidence_binder import (
    _cosine,
    bind_evidence_to_claim,
    candidate_text,
    retrieval_texts,
)
from app.services.evidence_entailment import _evidence_text
from app.services.report_agent.action_search import build_action_evidence_item
from app.services.report_agent.evidence_candidates import (
    RESERVED_CANDIDATE_SLOTS,
    EvidenceCandidatePool,
)

_CLAIM = "Familien ohne eigenes Auto erreichen den Kreißsaal im Norden nur schwer"
_POST = (
    "Familien ohne eigenes Auto erreichen den Kreißsaal im Norden nur schwer, "
    "besonders nachts"
)


def _bow_embedder(dim: int = 4096):
    def embed(text: str) -> List[float]:
        vec = [0.0] * dim
        for token in re.findall(r"\w+", (text or "").lower()):
            vec[zlib.crc32(token.encode("utf-8")) % dim] += 1.0
        return vec

    return embed


def _action_item(evidence_id: str, content: str, *, agent_id: int = 7) -> Dict[str, Any]:
    item = build_action_evidence_item(
        {
            "round_num": 9,
            "timestamp": f"2026-10-05T03:50:{agent_id:02d}",
            "platform": "reddit",
            "agent_id": agent_id,
            "agent_name": "Landfrauenverband Hollerau",
            "action_type": "CREATE_COMMENT",
            "action_args": {"content": content},
        }
    )
    item["evidence_id"] = evidence_id
    return item


def _interview_item(index: int) -> Dict[str, Any]:
    """Ein Interview, das den Claim wörtlich enthält — schlägt jeden Beitrag."""
    return {
        "evidence_id": f"ev_interview_{index}",
        "type": "agent_interview",
        "source_kind": "agent_quote",
        "snippet": f"{_CLAIM} (Stimme {index})",
    }


def test_action_is_retrieved_by_its_wording_not_by_the_meta_description() -> None:
    item = _action_item("ev_action", _POST)
    embed = _bow_embedder()

    texts = retrieval_texts(item, candidate_text(item))

    assert texts == [_POST]
    with_meta = _cosine(embed(_CLAIM), embed(candidate_text(item)))
    wording_only = _cosine(embed(_CLAIM), embed(texts[0]))
    assert wording_only > with_meta


def test_entailment_still_reads_the_voice_and_round_of_an_action() -> None:
    """Nur das Retrieval liest den reinen Wortlaut; das Urteil sieht die Stimme."""
    text = _evidence_text(_action_item("ev_action", _POST))

    assert "Landfrauenverband Hollerau" in text
    assert "round 9" in text


def test_other_evidence_types_keep_their_retrieval_text() -> None:
    item = _interview_item(1)

    assert retrieval_texts(item, candidate_text(item)) == [candidate_text(item)]


def test_action_above_threshold_is_displaced_without_reserved_slots() -> None:
    """Der Zustand vor #1778: fünf Interviews füllen die fünf Plätze."""
    candidates = [_interview_item(i) for i in range(5)] + [_action_item("ev_action", _POST)]

    bound = bind_evidence_to_claim(_CLAIM, candidates, _bow_embedder(), threshold=0.55, top_k=5)

    assert "ev_action" not in {entry["evidence_id"] for entry in bound}


def test_action_above_threshold_reaches_entailment_with_reserved_slots() -> None:
    candidates = [_interview_item(i) for i in range(5)] + [_action_item("ev_action", _POST)]

    bound = bind_evidence_to_claim(
        _CLAIM,
        candidates,
        _bow_embedder(),
        threshold=0.55,
        top_k=5,
        reserved_slots=RESERVED_CANDIDATE_SLOTS,
    )

    by_id = {entry["evidence_id"]: entry for entry in bound}
    assert len(bound) == 6
    assert by_id["ev_action"]["retrieval_score"] >= 0.55
    assert "entailment" in by_id["ev_action"]


def test_reserved_slot_does_not_decide_the_verdict(monkeypatch) -> None:
    """Reserviert ist die Prüfung, nicht das Urteil: ohne SUPPORTED kein Beleg."""
    from app.services import evidence_entailment

    def related_only(claim_text, evidence_item, **_kwargs):
        return evidence_entailment.EntailmentResult(
            evidence_entailment.EntailmentVerdict.RELATED_ONLY, "thematisch verwandt"
        )

    monkeypatch.setattr(evidence_entailment, "classify_evidence", related_only)
    candidates = [_interview_item(i) for i in range(5)] + [_action_item("ev_action", _POST)]

    bound = bind_evidence_to_claim(
        _CLAIM,
        candidates,
        _bow_embedder(),
        threshold=0.55,
        top_k=5,
        reserved_slots=RESERVED_CANDIDATE_SLOTS,
    )

    action = next(entry for entry in bound if entry["evidence_id"] == "ev_action")
    assert action["entailment"] == "RELATED_ONLY"
    assert action["supports_claim"] is False


def test_action_below_threshold_gets_no_reserved_slot() -> None:
    off_topic = _action_item("ev_action", "Der Haushalt des Landkreises wird im Dezember beraten")
    candidates = [_interview_item(i) for i in range(5)] + [off_topic]

    bound = bind_evidence_to_claim(
        _CLAIM,
        candidates,
        _bow_embedder(),
        threshold=0.55,
        top_k=5,
        reserved_slots=RESERVED_CANDIDATE_SLOTS,
    )

    assert "ev_action" not in {entry["evidence_id"] for entry in bound}


def test_reserved_slots_are_bounded() -> None:
    """Höchstens zwei Beiträge rücken nach, auch wenn mehr über der Schwelle liegen."""
    actions = [_action_item(f"ev_action_{i}", _POST, agent_id=10 + i) for i in range(4)]
    candidates = [_interview_item(i) for i in range(5)] + actions

    bound = bind_evidence_to_claim(
        _CLAIM,
        candidates,
        _bow_embedder(),
        threshold=0.55,
        top_k=5,
        reserved_slots=RESERVED_CANDIDATE_SLOTS,
    )

    action_ids = [e["evidence_id"] for e in bound if e["evidence_id"].startswith("ev_action")]
    assert len(action_ids) == RESERVED_CANDIDATE_SLOTS["agent_action"]
    assert len(bound) == 5 + RESERVED_CANDIDATE_SLOTS["agent_action"]


def test_actions_already_among_the_best_use_up_the_reserved_slots() -> None:
    """Die Reservierung ist ein Minimum, kein Zuschlag auf vorhandene Plätze."""
    actions = [_action_item(f"ev_action_{i}", _CLAIM, agent_id=10 + i) for i in range(3)]
    weaker = [
        {
            "evidence_id": f"ev_interview_{i}",
            "type": "agent_interview",
            "snippet": f"{_CLAIM} und außerdem geht es um Nachsorge und Hebammen",
        }
        for i in range(5)
    ]

    bound = bind_evidence_to_claim(
        _CLAIM,
        weaker + actions,
        _bow_embedder(),
        threshold=0.55,
        top_k=5,
        reserved_slots=RESERVED_CANDIDATE_SLOTS,
    )

    assert len(bound) == 5


def test_pool_keeps_reserved_candidates_behind_the_common_limit() -> None:
    items = [_interview_item(i) for i in range(4)] + [_action_item("ev_action", _POST)]
    embed = _bow_embedder()

    without = EvidenceCandidatePool(items, embed, limit=3).select(_CLAIM)
    with_slots = EvidenceCandidatePool(
        items, embed, limit=3, reserved_slots=RESERVED_CANDIDATE_SLOTS
    ).select(_CLAIM)

    assert "ev_action" not in {item["evidence_id"] for item in without}
    assert [item["evidence_id"] for item in with_slots][-1] == "ev_action"
    assert len(with_slots) == 4
