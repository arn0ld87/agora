"""Issue #1300 (Review-Finding Codex, P1, PR #1313): Bestandsschutz fuer
``agent_quote`` + ``seed_doc:``-Anker.

``EvidenceRecordModel.agent_quote_rejects_seed_doc_anchor`` lehnt diese
Kombination seit PR #1313 hart ab. Die Producer-Boundary in
``register_evidence_record`` verhindert sie fuer NEUE Records — vor dem
Deploy bereits als ``schema_version=3`` persistierte Reports tragen sie aber
noch auf Platte. Ohne Migration wirft ``GET /api/report/<id>/evidence`` beim
naechsten Laden ``ValidationError`` (HTTP 422), und JSON/ZIP/CSV-Export
lassen die Evidence-Map stumm aus.
"""
from __future__ import annotations

from app.contracts.report_contract import EvidenceMapModel
from app.services.evidence_identity import build_evidence_id
from app.services.evidence_migrations import (
    normalize_persisted_evidence_map,
    strip_seed_doc_anchor_from_agent_quote_records,
)

_SIM_ID = "sim_1300"
_QUOTE_KEY = "interview:s1:frage:antwort"


def _v3_map_with_fabricated_seed_doc_quote() -> dict:
    quote_id = build_evidence_id(_SIM_ID, "agent_quote", _QUOTE_KEY)
    return {
        "schema_version": 3,
        "report_id": "report_1300aa",
        "simulation_id": _SIM_ID,
        "evidence_index": {
            quote_id: {
                "evidence_id": quote_id,
                "producer_key": _QUOTE_KEY,
                "type": "agent_interview",
                "source": "agent:persona_1",
                "snippet": "Wörtliches Zitat aus dem Interview.",
                "quote": "Wörtliches Zitat aus dem Interview.",
                "source_kind": "agent_quote",
                "persona_stakeholder_group": "kunden",
                # Genau die Kombination, die #1300 als erfundene
                # Dokumentherkunft identifiziert.
                "source_id_anchor": "seed_doc:seed_aurora#chunk:0",
            }
        },
        "global_evidence_refs": [quote_id],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Stakeholder-Reaktionen",
                "section_summary": "Abschnitt mit einem Bestands-Interviewzitat.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Eine befragte Person äußert sich kritisch.",
                        "confidence_label": "medium",
                        "confidence_score": 0.5,
                        "evidence": [{"evidence_id": quote_id, "supports_claim": True}],
                    }
                ],
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
    }


def test_strip_removes_the_fabricated_anchor_but_keeps_the_record() -> None:
    migrated = strip_seed_doc_anchor_from_agent_quote_records(
        _v3_map_with_fabricated_seed_doc_quote()
    )

    record = next(iter(migrated["evidence_index"].values()))
    assert "source_id_anchor" not in record
    assert record["source_kind"] == "agent_quote"
    assert record["quote"] == "Wörtliches Zitat aus dem Interview."


def test_strip_does_not_change_the_evidence_id() -> None:
    """Anders als beim seed_corpus-Downgrade (#1154) bleibt source_kind gleich —
    kein Re-Key noetig, kein Bruch der Cross-References."""
    raw = _v3_map_with_fabricated_seed_doc_quote()
    original_id = next(iter(raw["evidence_index"]))

    migrated = strip_seed_doc_anchor_from_agent_quote_records(raw)

    assert list(migrated["evidence_index"].keys()) == [original_id]
    assert migrated["global_evidence_refs"] == [original_id]
    assert migrated["sections"][0]["claims"][0]["evidence"][0]["evidence_id"] == original_id


def test_a_persisted_report_with_the_legacy_combination_loads_without_422() -> None:
    """Der Kern des Findings: normalize_persisted_evidence_map darf nicht mehr
    an EvidenceRecordModel.agent_quote_rejects_seed_doc_anchor scheitern."""
    migrated = normalize_persisted_evidence_map(_v3_map_with_fabricated_seed_doc_quote())

    EvidenceMapModel.model_validate(migrated)


def test_strip_is_idempotent() -> None:
    once = strip_seed_doc_anchor_from_agent_quote_records(
        _v3_map_with_fabricated_seed_doc_quote()
    )
    index_after_first = dict(once["evidence_index"])

    twice = strip_seed_doc_anchor_from_agent_quote_records(once)

    assert twice["evidence_index"] == index_after_first


def test_verified_seed_document_anchor_on_seed_corpus_is_untouched() -> None:
    """Gegenprobe: der Strip betrifft ausschließlich source_kind=agent_quote."""
    raw = _v3_map_with_fabricated_seed_doc_quote()
    doc_id = build_evidence_id(_SIM_ID, "seed_corpus", "seed-doc:doc_a1b2c3d4:3")
    raw["evidence_index"][doc_id] = {
        "evidence_id": doc_id,
        "producer_key": "seed-doc:doc_a1b2c3d4:3",
        "type": "seed_document",
        "source": "report_tool",
        "snippet": "Beleg aus dem Ausgangsdokument.",
        "source_kind": "seed_corpus",
        "source_id_anchor": "seed_doc:doc_a1b2c3d4#chunk:3",
    }

    migrated = strip_seed_doc_anchor_from_agent_quote_records(raw)

    assert migrated["evidence_index"][doc_id]["source_id_anchor"] == (
        "seed_doc:doc_a1b2c3d4#chunk:3"
    )
