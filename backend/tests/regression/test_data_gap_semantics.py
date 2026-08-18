"""Ein Data Gap ist eine Aussage über die Quellenlage, nicht über den Matcher.

Der Referenzlauf ``report_cc2ef45da5e9`` exportierte 159 Data Gaps — 107 mit
``no_evidence_bound``, 52 mit ``related_evidence_only``. Beide Gründe
beschreiben, was das Binding getan hat, nicht was in den Quellen steht.
Mindestens ein so gemeldeter Fall stand wörtlich im Seed-Dokument.

Für den Leser ist das kein kleiner Unterschied: "diese Information liegt uns
nicht vor" richtet seine Recherche aus. Steht sie in Wahrheit im Seed, schickt
der Bericht ihn los, um etwas zu beschaffen, das er bereits hat.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.report_agent.agent import ReportAgent
from app.services.report_agent.data_gap import ClaimGapKind, classify_claim_gap

_SEED = (
    "Der Projektplan fordert vor Produktivstart mindestens 80 Prozent der "
    "unmittelbar betroffenen Beschäftigten als geschult."
)


def _record(text: str) -> Dict[str, Any]:
    return {"evidence_id": "ev_seed", "source_kind": "seed_corpus", "snippet": text}


def _agent_with_index(records: List[Dict[str, Any]]) -> ReportAgent:
    agent = ReportAgent.__new__(ReportAgent)
    agent.evidence_map = {
        "evidence_index": {record["evidence_id"]: record for record in records}
    }
    return agent


# --- Die Klassifikation selbst ---------------------------------------------


def test_related_evidence_proves_the_topic_exists():
    """Gebundene, aber nicht stützende Evidence ist bereits der Gegenbeweis.

    Sie wurde gefunden — also kommt das Thema in den Quellen vor. Dass sie
    den Claim nicht trägt, ist eine Aussage über den Claim, nicht über die
    Datenlage.
    """
    assert (
        classify_claim_gap(
            "Vor Produktivstart müssen mindestens 80 Prozent geschult sein.",
            related_evidence_count=2,
            evidence_pool=[],
        )
        is ClaimGapKind.BINDING_FAILURE
    )


def test_a_number_present_in_the_sources_is_never_a_data_gap():
    assert (
        classify_claim_gap(
            "Vor Produktivstart müssen mindestens 80 Prozent geschult sein.",
            related_evidence_count=0,
            evidence_pool=[_record(_SEED)],
        )
        is ClaimGapKind.BINDING_FAILURE
    )


def test_a_topic_present_in_the_sources_is_never_a_data_gap():
    assert (
        classify_claim_gap(
            "Die Schulung der betroffenen Beschäftigten ist vor Produktivstart "
            "abzuschließen.",
            related_evidence_count=0,
            evidence_pool=[_record(_SEED)],
        )
        is ClaimGapKind.BINDING_FAILURE
    )


def test_a_number_alone_is_enough_to_rule_out_a_data_gap():
    """Der rein numerische Pfad, ohne lexikalische Rückendeckung.

    Ohne diesen Fall wäre nicht geprüft, ob ``source_mentions_claim_numbers``
    überhaupt etwas beiträgt — die Wortdeckung fängt die meisten Fälle mit ab
    und verdeckte, dass der Zahlenpfad ungetestet war.
    """
    assert (
        classify_claim_gap(
            "Die Zielmarke liegt bei 80 Prozent.",
            related_evidence_count=0,
            evidence_pool=[_record(_SEED)],
        )
        is ClaimGapKind.BINDING_FAILURE
    )


def test_a_topic_absent_from_every_source_is_a_real_data_gap():
    """Die Gegenprobe — ohne sie wäre der Data Gap als Konzept abgeschafft."""
    assert (
        classify_claim_gap(
            "Die Kantinenpreise steigen im kommenden Quartal.",
            related_evidence_count=0,
            evidence_pool=[_record(_SEED)],
        )
        is ClaimGapKind.SOURCE_INFORMATION_ABSENT
    )


def test_an_empty_source_pool_leaves_everything_absent():
    assert (
        classify_claim_gap(
            "Irgendeine Aussage.", related_evidence_count=0, evidence_pool=[]
        )
        is ClaimGapKind.SOURCE_INFORMATION_ABSENT
    )


# --- Verdrahtung im Agent ---------------------------------------------------


def test_binding_failure_is_not_exported_as_data_gap_when_source_contains_fact():
    """Der Fall aus dem Referenzlauf, vollständig durch den Agent gezogen."""
    agent = _agent_with_index([_record(_SEED)])
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Vor Produktivstart müssen mindestens 80 Prozent geschult sein.",
        "evidence": [],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]

    _finalized, hypotheses, gaps, decisions = agent._finalize_section_claims(claims)

    assert gaps == [], "Die Information steht im Seed — das ist keine Datenlücke"
    assert len(hypotheses) == 1, "Unbelegt bleibt die Aussage trotzdem"
    assert "binding_failure" in decisions[0]["detail"]


def test_a_claim_no_source_speaks_to_still_becomes_a_data_gap():
    agent = _agent_with_index([_record(_SEED)])
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Die Kantinenpreise steigen im kommenden Quartal deutlich an.",
        "evidence": [],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]

    _finalized, _hypotheses, gaps, decisions = agent._finalize_section_claims(claims)

    assert len(gaps) == 1
    assert gaps[0]["gap_reason"] == "source_information_absent"
    assert "source_information_absent" in decisions[0]["detail"]


def test_related_only_evidence_never_produces_a_data_gap():
    agent = _agent_with_index([_record(_SEED)])
    claims = [{
        "claim_id": "claim_01",
        "claim_text": "Die Kantinenpreise steigen im kommenden Quartal deutlich an.",
        "evidence": [{"evidence_id": "ev_seed", "supports_claim": False}],
        "confidence_score": 0.1,
        "confidence_label": "low",
    }]

    _finalized, hypotheses, gaps, _decisions = agent._finalize_section_claims(claims)

    assert gaps == []
    assert len(hypotheses) == 1
