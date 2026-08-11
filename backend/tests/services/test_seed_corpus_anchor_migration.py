"""ADR-0013 / Issue #1154: seed_corpus ohne verifizierten Dokumentanker.

Vor #1154 war ``seed_corpus`` die Default-Quellengattung für alles, was aus
dem Graphen kam. Solche Records behaupten einen Dokumentbeleg, den niemand
nachschlagen kann. Beim Laden verlieren sie ihren Seed-Status.

Der Downgrade ist kein Label-Update: ``source_kind`` steckt im Hash von
``build_evidence_id``. Bliebe die alte ID stehen, bekäme derselbe Beleg beim
nächsten Schreiben eine zweite Identität. Umgeschlüsselt wird deshalb
zusammen mit allen Referenzen — sonst wirft
``EvidenceMapModel.validate_evidence_cross_references``.
"""
from __future__ import annotations

from app.contracts.report_contract import EvidenceMapModel
from app.services.evidence_identity import build_evidence_id
from app.services.evidence_migrations import (
    demote_unanchored_seed_corpus_records,
    normalize_persisted_evidence_map,
)

_SIM_ID = "sim_1154"
_UNANCHORED_KEY = "graph-fact:a1b2c3"
_ANCHORED_KEY = "seed-doc:doc_a1b2c3d4:7"


def _record(evidence_id: str, producer_key: str, **extra) -> dict:
    record = {
        "evidence_id": evidence_id,
        "producer_key": producer_key,
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Belegtext aus der Quelle.",
        "source_kind": "seed_corpus",
    }
    record.update(extra)
    return record


def _v3_map(*, claim_label: str = "medium", with_agent_quote: bool = True) -> dict:
    unanchored_id = build_evidence_id(_SIM_ID, "seed_corpus", _UNANCHORED_KEY)
    quote_id = build_evidence_id(_SIM_ID, "agent_quote", "agent:persona_1")
    evidence_index = {
        unanchored_id: _record(unanchored_id, _UNANCHORED_KEY),
    }
    bindings = [{"evidence_id": unanchored_id, "supports_claim": True}]
    if with_agent_quote:
        evidence_index[quote_id] = {
            "evidence_id": quote_id,
            "producer_key": "agent:persona_1",
            "type": "agent_interview",
            "source": "agent:persona_1",
            "snippet": "Wörtliches Zitat.",
            "quote": "Wörtliches Zitat.",
            "source_kind": "agent_quote",
            "persona_stakeholder_group": "kunden",
        }
        bindings.append({"evidence_id": quote_id, "supports_claim": True})
    return {
        "schema_version": 3,
        "report_id": "report_1154aa",
        "simulation_id": _SIM_ID,
        "evidence_index": evidence_index,
        "global_evidence_refs": [unanchored_id],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Abschnitt mit Bestandsevidenz.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Zielgruppe reagiert positiv auf den Ansatz.",
                        "confidence_label": claim_label,
                        "confidence_score": 0.55,
                        "evidence": bindings,
                    }
                ],
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
    }


def test_unanchored_seed_record_loses_its_seed_status() -> None:
    migrated = demote_unanchored_seed_corpus_records(_v3_map())

    records = list(migrated["evidence_index"].values())
    demoted = next(r for r in records if r["producer_key"] == _UNANCHORED_KEY)
    assert demoted["source_kind"] == "graph_relation"


def test_demotion_rekeys_the_record_and_every_reference() -> None:
    """Der Kern: Identitätswechsel und Referenzen wandern gemeinsam."""
    raw = _v3_map()
    old_id = build_evidence_id(_SIM_ID, "seed_corpus", _UNANCHORED_KEY)
    new_id = build_evidence_id(_SIM_ID, "graph_relation", _UNANCHORED_KEY)
    assert old_id != new_id, "Testvoraussetzung: source_kind geht in den Hash ein."

    migrated = demote_unanchored_seed_corpus_records(raw)

    assert old_id not in migrated["evidence_index"]
    assert migrated["evidence_index"][new_id]["evidence_id"] == new_id
    assert migrated["global_evidence_refs"] == [new_id]
    bindings = migrated["sections"][0]["claims"][0]["evidence"]
    assert new_id in {b["evidence_id"] for b in bindings}
    assert old_id not in {b["evidence_id"] for b in bindings}


def test_rekeyed_map_still_validates_against_the_contract() -> None:
    """Ein Re-Key ohne Referenz-Nachzug wäre genau der HTTP 422."""
    migrated = normalize_persisted_evidence_map(_v3_map())

    EvidenceMapModel.model_validate(migrated)


def test_claim_loses_medium_when_its_seed_evidence_is_demoted() -> None:
    migrated = normalize_persisted_evidence_map(_v3_map())

    claim = migrated["sections"][0]["claims"][0]
    assert claim["confidence_label"] == "low"


def test_anchored_seed_record_keeps_status_and_identity() -> None:
    """Gegenprobe: mit auflösbarem Anker bleibt alles, wie es ist."""
    raw = _v3_map()
    anchored_id = build_evidence_id(_SIM_ID, "seed_corpus", _ANCHORED_KEY)
    raw["evidence_index"][anchored_id] = _record(
        anchored_id,
        _ANCHORED_KEY,
        type="seed_document",
        source_id_anchor="seed_doc:doc_a1b2c3d4#chunk:7",
    )
    raw["sections"][0]["claims"][0]["evidence"].append(
        {"evidence_id": anchored_id, "supports_claim": True}
    )

    migrated = normalize_persisted_evidence_map(raw)

    kept = migrated["evidence_index"][anchored_id]
    assert kept["source_kind"] == "seed_corpus"
    assert kept["type"] == "seed_document"
    # Der Claim behält medium: agent_quote + verankerter seed_corpus.
    assert migrated["sections"][0]["claims"][0]["confidence_label"] == "medium"
    EvidenceMapModel.model_validate(migrated)


def test_demotion_is_idempotent() -> None:
    once = demote_unanchored_seed_corpus_records(_v3_map())
    index_after_first = dict(once["evidence_index"])

    twice = demote_unanchored_seed_corpus_records(once)

    assert twice["evidence_index"] == index_after_first
    EvidenceMapModel.model_validate(normalize_persisted_evidence_map(twice))


def test_collision_with_an_existing_record_merges_instead_of_duplicating() -> None:
    """Gleicher producer_key in derselben Gattung ist dieselbe Quelle."""
    raw = _v3_map(with_agent_quote=False)
    target_id = build_evidence_id(_SIM_ID, "graph_relation", _UNANCHORED_KEY)
    raw["evidence_index"][target_id] = {
        "evidence_id": target_id,
        "producer_key": _UNANCHORED_KEY,
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Derselbe Beleg, bereits als Graph-Relation geführt.",
        "source_kind": "graph_relation",
    }
    raw["sections"][0]["claims"][0]["evidence"].append(
        {"evidence_id": target_id, "supports_claim": True}
    )

    migrated = demote_unanchored_seed_corpus_records(raw)

    assert len(migrated["evidence_index"]) == 1
    bindings = migrated["sections"][0]["claims"][0]["evidence"]
    assert [b["evidence_id"] for b in bindings] == [target_id], (
        "Zwei Bindungen auf dieselbe Quelle würden Evidence-Anzahl und Confidence aufblähen."
    )


def test_record_without_producer_key_is_demoted_but_keeps_its_id() -> None:
    """Ohne producer_key ist keine kanonische ID berechenbar.

    Der Seed-Status fällt trotzdem — ein unbelegter Dokumentfakt ist der
    schlechtere Zustand als eine ID, die nicht zum Hash passt.
    """
    raw = _v3_map(with_agent_quote=False)
    old_id = build_evidence_id(_SIM_ID, "seed_corpus", _UNANCHORED_KEY)
    raw["evidence_index"][old_id]["producer_key"] = ""

    migrated = demote_unanchored_seed_corpus_records(raw)

    assert old_id in migrated["evidence_index"]
    assert migrated["evidence_index"][old_id]["source_kind"] == "graph_relation"


def test_remap_out_reports_the_identity_change() -> None:
    """Aufrufer mit eigenen Referenzen im Speicher brauchen die Zuordnung."""
    remap: dict[str, str] = {}
    demote_unanchored_seed_corpus_records(_v3_map(), remap_out=remap)

    assert remap == {
        build_evidence_id(_SIM_ID, "seed_corpus", _UNANCHORED_KEY):
            build_evidence_id(_SIM_ID, "graph_relation", _UNANCHORED_KEY),
    }


def test_high_claim_with_two_stakeholder_groups_keeps_high_without_seed() -> None:
    """Kein pauschaler Cap: ``high`` hängt an Stakeholder-Gruppen, nicht am Seed.

    Der Downgrade aus #1154 betrifft ausschließlich den Seed-Status und das
    davon abhängige ``medium``. Ein Claim, den zwei unterschiedliche
    Stakeholder-Gruppen stützen, erfüllt ADR-0002 Anker 4 aus eigener Kraft.
    """
    quote_ids = [
        build_evidence_id(_SIM_ID, "agent_quote", f"agent:persona_{n}") for n in (1, 2)
    ]
    raw = {
        "schema_version": 3,
        "report_id": "report_1154bb",
        "simulation_id": _SIM_ID,
        "evidence_index": {
            quote_id: {
                "evidence_id": quote_id,
                "producer_key": f"agent:persona_{n}",
                "type": "agent_interview",
                "source": f"agent:persona_{n}",
                "snippet": "Wörtliches Zitat.",
                "quote": "Wörtliches Zitat.",
                "source_kind": "agent_quote",
                "persona_stakeholder_group": group,
            }
            for n, (quote_id, group) in enumerate(
                zip(quote_ids, ["kunden", "betreiber"]), start=1
            )
        },
        "global_evidence_refs": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Abschnitt mit zwei Stakeholder-Gruppen.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Beide Seiten erwarten denselben Reibungspunkt.",
                        "confidence_label": "high",
                        "confidence_score": 0.82,
                        "evidence": [
                            {"evidence_id": quote_ids[0], "supports_claim": True},
                            {"evidence_id": quote_ids[1], "supports_claim": True},
                        ],
                    }
                ],
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
    }

    migrated = normalize_persisted_evidence_map(raw)

    assert migrated["sections"][0]["claims"][0]["confidence_label"] == "high"
    EvidenceMapModel.model_validate(migrated)
