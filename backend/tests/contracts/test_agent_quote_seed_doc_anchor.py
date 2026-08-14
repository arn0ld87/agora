"""Issue #1300 — Interviewzitate duerfen keine seed_doc-Anker tragen.

Ein agent_quote-Evidence-Record beschreibt eine simulierte Persona-Aussage
aus einem Interview. Ein ``seed_doc:``-Anker (ADR-0013) behauptet dagegen,
der Inhalt stamme wortgetreu aus einer Passage eines Seed-Dokuments. Beides
zusammen ist eine erfundene Quelle: der Referenzlauf zeigte Persona-O-Toene
mit Anker ``seed_doc:seed_aurora#chunk:0``, obwohl sie aus
``agent_interview``-Interaktionen stammen.

Der Validator setzt das acceptance criterion aus #1300 am Contract durch:
Ein EvidenceRecord/Item mit ``source_kind=agent_quote`` darf keinen
``seed_doc:``-Anker tragen — Interview-Evidence referenziert sich ueber ihre
``ev_``-Evidence-ID bzw. einen interview-spezifischen Anker, nie ueber eine
Dokumentherkunft.

Abgrenzung: ``validate_quote_anchors`` (Markdown-Tag) bleibt bewusst
unberuehrt — der Section-Prompt dokumentiert die ``seed_doc:``-Form als
gueltige seed_anchor-Form fuer Zitate, die tatsaechlich aus einem Seed-
Dokument stammen (PR #1312 Revert-Notiz, contracts-first).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts import (
    EvidenceItemModel,
    EvidenceRecordModel,
    EvidenceSourceKind,
    EvidenceType,
)


#: Fabrizierter Anker aus dem Referenzlauf (Issue #1300) — existiert in
#: keinem Korpus, behauptet aber eine ueberpruefbare Dokumentstelle.
_FABRICATED_ANCHOR = "seed_doc:seed_aurora#chunk:0"

_VALID_EVIDENCE_ID = "ev_" + "a" * 32


def _agent_quote_item(**overrides: object) -> dict:
    payload: dict = {
        "type": EvidenceType.agent_interview,
        "source": "interview_agents",
        "snippet": "Persona aeusserte sich im Interview.",
        "quote": "Original-Zitat aus dem Interview.",
        "source_kind": EvidenceSourceKind.agent_quote,
        "persona_stakeholder_group": "Lehrkraefte",
    }
    payload.update(overrides)
    return payload


def _agent_quote_record(**overrides: object) -> dict:
    payload: dict = {
        "evidence_id": _VALID_EVIDENCE_ID,
        "producer_key": "interview:s0:abc",
        "type": EvidenceType.agent_interview,
        "source": "interview_agents",
        "snippet": "Persona aeusserte sich im Interview.",
        "quote": "Original-Zitat aus dem Interview.",
        "source_kind": EvidenceSourceKind.agent_quote,
        "persona_stakeholder_group": "Lehrkraefte",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# EvidenceItemModel
# ---------------------------------------------------------------------------


def test_item_agent_quote_rejects_seed_doc_anchor() -> None:
    """Interview-Evidence mit erfundenem seed_doc-Anker -> ValidationError."""
    with pytest.raises(ValidationError, match="seed_doc"):
        EvidenceItemModel.model_validate(_agent_quote_item(source_id_anchor=_FABRICATED_ANCHOR))


def test_item_agent_quote_allows_non_seed_doc_anchors() -> None:
    """Interview-Evidence mit interview-gerechtem Anker bleibt gueltig."""
    item = EvidenceItemModel.model_validate(
        _agent_quote_item(source_id_anchor="agent-log-42#entry-7")
    )
    assert item.source_id_anchor == "agent-log-42#entry-7"


def test_item_seed_corpus_with_seed_doc_anchor_stays_valid() -> None:
    """Echte Dokumentfakten behalten ihren seed_doc-Anker (ADR-0013-Pfad)."""
    item = EvidenceItemModel.model_validate(
        {
            "type": EvidenceType.seed_document,
            "source": "insight_forge",
            "snippet": "Fakt aus einer Dokumentpassage.",
            "source_kind": EvidenceSourceKind.seed_corpus,
            "source_id_anchor": "seed_doc:kursdokument#chunk:7",
        }
    )
    assert item.source_id_anchor == "seed_doc:kursdokument#chunk:7"


# ---------------------------------------------------------------------------
# EvidenceRecordModel
# ---------------------------------------------------------------------------


def test_record_agent_quote_rejects_seed_doc_anchor() -> None:
    """EvidenceRecord: agent_quote + seed_doc-Anker -> ValidationError."""
    with pytest.raises(ValidationError, match="seed_doc"):
        EvidenceRecordModel.model_validate(_agent_quote_record(source_id_anchor=_FABRICATED_ANCHOR))


def test_record_agent_quote_without_anchor_stays_valid() -> None:
    """Interview-Evidence ohne Anker bleibt gueltig — die ev_-ID traegt die
    referenzierbare Identitaet (build_evidence_id)."""
    record = EvidenceRecordModel.model_validate(_agent_quote_record())
    assert record.source_id_anchor is None
    assert record.source_kind == EvidenceSourceKind.agent_quote


def test_record_seed_corpus_with_seed_doc_anchor_stays_valid() -> None:
    record = EvidenceRecordModel.model_validate(
        {
            "evidence_id": _VALID_EVIDENCE_ID,
            "producer_key": "seed-doc:kursdokument:7",
            "type": EvidenceType.seed_document,
            "source": "insight_forge",
            "snippet": "Fakt aus einer Dokumentpassage.",
            "source_kind": EvidenceSourceKind.seed_corpus,
            "source_id_anchor": "seed_doc:kursdokument#chunk:7",
        }
    )
    assert record.source_id_anchor == "seed_doc:kursdokument#chunk:7"
