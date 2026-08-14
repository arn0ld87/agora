"""Issue #1300 — Interview-Evidence: korrekte Verankerung, keine seed_doc-Referenzen.

Regressionstests fuer die Producer-Boundary ``register_evidence_record``:
Interview-Items (``type=agent_interview``) werden zu ``source_kind=agent_quote``
und duerfen niemals einen ``seed_doc:``-Anker tragen. Fabrizierte Anker — im
Referenzlauf ``seed_doc:seed_aurora#chunk:0`` — werden an der Boundary
entfernt, statt den ganzen Record zu verlieren.
"""

from __future__ import annotations

from app.services.report_agent.evidence import register_evidence_record


_FABRICATED_ANCHOR = "seed_doc:seed_aurora#chunk:0"


def _interview_item(**overrides: object) -> dict:
    """Interview-Item, wie ``agent.py::_record_tool_evidence`` es baut."""
    payload: dict = {
        "type": "agent_interview",
        "source": "interview_agents",
        "tool_name": "interview_agents",
        "query": "Meinung zur Initiative",
        "snippet": "Persona: Ich sehe keinen Mehrwert.",
        "raw": {"agent_name": "persona_03", "question": "Was halten Sie davon?"},
        "quote": "Ich sehe keinen Mehrwert.",
        "persona_stakeholder_group": "Lehrkraefte",
        "agent_log_ref": {
            "section_index": 0,
            "action": "tool_result",
            "tool_name": "interview_agents",
        },
        "producer_key": "interview:s0:abc123",
    }
    payload.update(overrides)
    return payload


def _empty_evidence_map() -> dict:
    return {"evidence_index": {}}


def test_interview_item_registers_as_agent_quote_without_seed_doc_anchor() -> None:
    """Positivpfad: Interview-Output -> agent_quote-Record mit Persona-Referenz."""
    evidence_map = _empty_evidence_map()
    record = register_evidence_record(evidence_map, _interview_item(), scope_id="sim-1")
    assert record is not None
    assert record["source_kind"] == "agent_quote"
    assert record["persona_stakeholder_group"] == "Lehrkraefte"
    assert record["source_id_anchor"] is None
    assert not str(record["evidence_id"]).startswith("seed_doc:")
    assert record["evidence_id"] in evidence_map["evidence_index"]


def test_fabricated_seed_doc_anchor_is_stripped_at_the_boundary() -> None:
    """Negativpfad: erfundener seed_doc-Anker wird entfernt, Record bleibt."""
    evidence_map = _empty_evidence_map()
    record = register_evidence_record(
        evidence_map,
        _interview_item(source_id_anchor=_FABRICATED_ANCHOR),
        scope_id="sim-1",
    )
    assert record is not None
    assert record["source_kind"] == "agent_quote"
    assert record["source_id_anchor"] is None
    assert record["evidence_id"] in evidence_map["evidence_index"]


def test_seed_document_item_keeps_its_verified_anchor() -> None:
    """Der seed_corpus-Schreibpfad (ADR-0013) bleibt unberuehrt."""
    evidence_map = _empty_evidence_map()
    record = register_evidence_record(
        evidence_map,
        {
            "type": "seed_document",
            "source": "insight_forge",
            "tool_name": "insight_forge",
            "query": "Kursdaten",
            "snippet": "Fakt aus einer Dokumentpassage.",
            "raw": "Fakt aus einer Dokumentpassage.",
            "producer_key": "seed-doc:kursdokument:7",
            "source_id_anchor": "seed_doc:kursdokument#chunk:7",
        },
        scope_id="sim-1",
    )
    assert record is not None
    assert record["source_kind"] == "seed_corpus"
    assert record["source_id_anchor"] == "seed_doc:kursdokument#chunk:7"
