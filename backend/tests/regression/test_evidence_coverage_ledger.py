"""Kein quantitativer Fakt verschwindet still zwischen Tool und Index.

Im Referenzlauf ``report_cc2ef45da5e9`` lagen 31 %, 67 %, 83 %, 91 %, 6 % und
"sieben Fälle" in den Retrieval-Ergebnissen vor und fehlten anschließend als
kanonische Evidence. Das ist kein Matching- und kein Entailment-Problem — die
Fakten kamen nie so weit.

Verworfen werden darf ein Fakt. Nur nicht wortlos: jeder Eintrag im Ledger
trägt entweder eine kanonische ID oder einen Grund.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import EvidenceCoverageEntry, EvidenceMapModel
from app.services.report_agent.evidence import register_evidence_record
from app.services.report_agent.evidence_ledger import EvidenceCoverageLedger, ledger_for

#: Das Tool-Ergebnis aus der Spezifikation.
TOOL_RESULT_FACTS = [
    "In der Verwaltung sind 54 Prozent der Beschäftigten geschult.",
    "Im Ärztlichen Dienst sind 67 Prozent der Beschäftigten geschult.",
    "In der Pflege-Nachtschicht sind 31 Prozent der Beschäftigten geschult.",
    "In der Technik sind 83 Prozent der Beschäftigten geschult.",
    "In der Leitung sind 91 Prozent der Beschäftigten geschult.",
]


def _item(snippet: str, producer_key: str) -> Dict[str, Any]:
    return {
        "type": "graph_fact",
        "source": "insight_forge",
        "source_kind": "seed_corpus",
        "snippet": snippet,
        "producer_key": producer_key,
    }


def _empty_map() -> Dict[str, Any]:
    return {
        "schema_version": 3,
        "report_id": "report_test",
        "simulation_id": "sim_test",
        "evidence_index": {},
        "global_evidence_refs": [],
        "sections": [],
    }


def test_five_facts_yield_five_traceable_outcomes():
    """Das Akzeptanzkriterium aus der Spezifikation, wörtlich."""
    ledger = EvidenceCoverageLedger()
    evidence_map = _empty_map()

    for index, fact in enumerate(TOOL_RESULT_FACTS):
        register_evidence_record(
            evidence_map, _item(fact, f"fact:{index}"), scope_id="sim_test", ledger=ledger
        )

    entries = ledger.entries
    assert len(entries) == 5
    assert all(entry.status == "canonicalized" for entry in entries)
    assert all(entry.canonical_evidence_id for entry in entries)
    assert sorted(entry.normalized_value for entry in entries) == [31, 54, 67, 83, 91]


def test_a_dedup_hit_is_booked_against_the_existing_record():
    """Zweimal derselbe Fakt ist kein Verlust — aber er ist nachvollziehbar."""
    ledger = EvidenceCoverageLedger()
    evidence_map = _empty_map()
    item = _item(TOOL_RESULT_FACTS[0], "fact:0")

    first = register_evidence_record(evidence_map, item, scope_id="sim_test", ledger=ledger)
    second = register_evidence_record(evidence_map, item, scope_id="sim_test", ledger=ledger)

    assert first is not None and second is not None
    assert first["evidence_id"] == second["evidence_id"]
    assert len(evidence_map["evidence_index"]) == 1
    assert [entry.canonical_evidence_id for entry in ledger.entries] == [
        first["evidence_id"],
        first["evidence_id"],
    ]


def test_a_fact_without_a_producer_key_is_booked_as_dropped_with_a_reason():
    ledger = EvidenceCoverageLedger()

    result = register_evidence_record(
        _empty_map(),
        {"type": "graph_fact", "snippet": TOOL_RESULT_FACTS[0]},
        scope_id="sim_test",
        ledger=ledger,
    )

    assert result is None
    assert [entry.status for entry in ledger.entries] == ["dropped"]
    assert ledger.entries[0].reason == "missing_producer_key"


def test_a_qualitative_snippet_does_not_enter_the_ledger():
    """Das Ledger führt Zahlen, nicht den gesamten Textverkehr des Laufs."""
    ledger = EvidenceCoverageLedger()

    register_evidence_record(
        _empty_map(),
        _item("Die Einführung erfolgt in mehreren Wellen.", "fact:q"),
        scope_id="sim_test",
        ledger=ledger,
    )

    assert ledger.entries == []


def test_without_a_ledger_nothing_changes():
    """Der Parameter ist optional; Alt-Aufrufer bleiben unberührt."""
    evidence_map = _empty_map()

    record = register_evidence_record(
        evidence_map, _item(TOOL_RESULT_FACTS[0], "fact:0"), scope_id="sim_test"
    )

    assert record is not None
    assert len(evidence_map["evidence_index"]) == 1


# --- Contract ---------------------------------------------------------------


def test_a_dropped_entry_without_a_reason_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceCoverageEntry(
            source_result_id="fact:0", fact="54 Prozent", status="dropped"
        )


def test_a_canonicalized_entry_without_an_id_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceCoverageEntry(
            source_result_id="fact:0", fact="54 Prozent", status="canonicalized"
        )


def test_the_ledger_field_is_additive_on_the_evidence_map():
    """Bestehende persistierte Maps ohne das Feld validieren unverändert."""
    assert EvidenceMapModel.model_validate(_empty_map()).evidence_coverage_ledger == []


def test_the_ledger_payload_validates_against_the_evidence_map():
    ledger = EvidenceCoverageLedger()
    evidence_map = _empty_map()
    register_evidence_record(
        evidence_map, _item(TOOL_RESULT_FACTS[0], "fact:0"), scope_id="sim_test", ledger=ledger
    )
    evidence_map["evidence_coverage_ledger"] = ledger.as_payload()

    validated = EvidenceMapModel.model_validate(evidence_map)

    assert len(validated.evidence_coverage_ledger) == 1


# --- Anbindung an den Agent -------------------------------------------------


def test_the_ledger_survives_repeated_lookups_on_the_same_object():
    class _Carrier:
        pass

    carrier = _Carrier()

    assert ledger_for(carrier) is ledger_for(carrier)
