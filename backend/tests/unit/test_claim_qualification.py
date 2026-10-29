"""Unit and regression tests for the deep claim_qualification module (Slice #1)."""

from __future__ import annotations

from app.services.report_agent.claim_qualification import (
    compute_evidence_density,
    evaluate_claim_mode_gate,
    qualify_claim_evidence,
    resolve_claim_evidence_item,
    resolve_document_anchor,
    resolve_independent_source_keys,
    resolve_voice_key,
)


def test_stimme_and_dokumentanker_are_resolved_separately_and_combined_as_sources() -> None:
    """Persona voices (Stimme) and document anchors (Dokumentanker) stay distinct."""
    post_entry = {
        "evidence_id": "ev_post_1",
        "type": "agent_action",
        "source_kind": "agent_quote",
        "provenance_class": "observed_simulation",
        "agent_id": 7,
        "agent_name": "Anna Meier",
        "stakeholder_group": "Handwerk",
    }
    interview_same_persona = {
        "evidence_id": "ev_int_1",
        "type": "agent_interview",
        "source_kind": "interview_response",
        "provenance_class": "synthetic_interview",
        "agent_name": "Anna Meier",
        "stakeholder_group": "Handwerk",
    }
    doc_entry_a = {
        "evidence_id": "ev_doc_1",
        "type": "seed_document",
        "source_kind": "seed_corpus",
        "provenance_class": "source_grounded",
        "source_id_anchor": "seed_doc:doc_42#chunk_1",
        "quote": "Absatz 1",
    }
    doc_entry_b_same_doc = {
        "evidence_id": "ev_doc_2",
        "type": "seed_document",
        "source_kind": "seed_corpus",
        "provenance_class": "source_grounded",
        "source_doc_id": "doc_42",
        "quote": "Absatz 2",
    }

    assert resolve_voice_key(doc_entry_a) is None
    assert resolve_document_anchor(doc_entry_a) == "doc:doc_42"
    assert resolve_document_anchor(doc_entry_b_same_doc) == "doc:doc_42"

    claim = {
        "claim_id": "c1",
        "claim_text": "Handwerk und Vorlage benennen denselben Engpass.",
        "evidence": [
            {"evidence_id": "ev_post_1", "supports_claim": True},
            {"evidence_id": "ev_int_1", "supports_claim": True},
            {"evidence_id": "ev_doc_1", "supports_claim": True},
            {"evidence_id": "ev_doc_2", "supports_claim": True},
        ],
    }
    evidence_index = {
        "ev_post_1": post_entry,
        "ev_int_1": interview_same_persona,
        "ev_doc_1": doc_entry_a,
        "ev_doc_2": doc_entry_b_same_doc,
    }

    qualified = qualify_claim_evidence(claim, evidence_index)
    # Post + interview of Anna Meier collapse to 1 canonical voice ("agent:7")
    assert qualified.independent_voices == frozenset({"agent:7"})
    assert qualified.supporting_voices_count == 1
    # Two chunks from doc_42 collapse to 1 document anchor ("doc:doc_42")
    assert qualified.document_anchors == frozenset({"doc:doc_42"})
    # Together they provide 2 independent sources and cross-source grounding
    assert set(qualified.independent_source_keys) == {
        ("voice", "agent:7"),
        ("doc", "doc:doc_42"),
    }
    assert qualified.distinct_independent_sources == 2
    assert qualified.confidence_scope == "evidence"
    assert qualified.aggregation_basis == "aggregat"


def test_canonical_record_wins_over_inline_spoofing_and_bidirectional_disqualification() -> None:
    """Canonical record metadata cannot be spoofed inline; disqualifiers from either side win."""
    evidence_index = {
        "ev_scaffold": {
            "evidence_id": "ev_scaffold",
            "type": "model_generated_inference",
            "source_kind": "inferred",
            "provenance_class": "template_scaffold",
            "graph_origin": "manual_edit",
        },
        "ev_real": {
            "evidence_id": "ev_real",
            "type": "agent_action",
            "source_kind": "agent_quote",
            "provenance_class": "observed_simulation",
            "agent_id": 11,
            "stakeholder_group": "Kommunen",
            "quote": "Real quote",
        },
    }

    # Inline binding attempts to spoof provenance_class and source_kind on a scaffold item
    spoofed_inline = {
        "evidence_id": "ev_scaffold",
        "source_kind": "seed_corpus",
        "provenance_class": "source_grounded",
        "supports_claim": True,
    }
    resolved_scaffold = resolve_claim_evidence_item(spoofed_inline, evidence_index)
    assert resolved_scaffold["provenance_class"] == "template_scaffold"
    assert resolved_scaffold["graph_origin"] == "manual_edit"

    # Inline binding explicitly marks a real item as contradicting / non-supporting
    contradicting_inline = {
        "evidence_id": "ev_real",
        "supports_claim": False,
        "contradicts_claim": True,
        "entailment": "contradicts",
    }
    claim = {
        "claim_id": "c_disq",
        "claim_text": "Unbelegter Satz",
        "evidence": [spoofed_inline, contradicting_inline],
    }
    qualified = qualify_claim_evidence(claim, evidence_index)
    assert qualified.supporting == ()
    assert len(qualified.contradicting) == 1
    assert qualified.valid_evidence_refs == ()
    assert qualified.confidence_scope == "simulation_consensus"


def test_evaluate_claim_mode_gate_routes_strict_and_balanced_claims() -> None:
    """evaluate_claim_mode_gate centralizes strict/balanced routing and single-source downgrade."""
    evidence_index = {
        "ev_1": {
            "evidence_id": "ev_1",
            "type": "agent_action",
            "source_kind": "agent_quote",
            "provenance_class": "observed_simulation",
            "agent_id": 1,
            "stakeholder_group": "Gewerkschaft",
            "quote": "Einzelstimme",
        }
    }
    single_source_high_claim = {
        "claim_id": "c_single",
        "claim_text": "Hohe Sicherheit trotz Einzelquelle.",
        "confidence_label": "high",
        "evidence": [{"evidence_id": "ev_1", "supports_claim": True}],
    }

    # Single-source high claim is downgraded to low and kept in balanced mode, dropped in strict mode
    decision_balanced = evaluate_claim_mode_gate(
        dict(single_source_high_claim),
        evidence_index,
        report_mode="balanced",
    )
    assert decision_balanced.accepted is True
    assert decision_balanced.single_source_downgraded is True
    assert decision_balanced.confidence == "low"
    assert decision_balanced.text_confidence == "high"

    decision_strict = evaluate_claim_mode_gate(
        dict(single_source_high_claim),
        evidence_index,
        report_mode="strict",
    )
    assert decision_strict.accepted is False
    assert decision_strict.single_source_downgraded is True
    assert decision_strict.drop_reason == "strict_mode_low_confidence"

    # Unverified claim is rejected with no_valid_evidence_refs
    unverified_claim = {
        "claim_id": "c_unv",
        "claim_text": "Reine Vermutung ohne Beleg.",
        "confidence_label": "low",
        "evidence": [],
    }
    decision_unv = evaluate_claim_mode_gate(
        dict(unverified_claim),
        evidence_index,
        report_mode="balanced",
    )
    assert decision_unv.accepted is False
    assert decision_unv.drop_reason == "no_valid_evidence_refs"


def test_compute_evidence_density_counts_distinct_voices_and_groups() -> None:
    """compute_evidence_density aggregates supporting claims, independent sources, and action support."""
    evidence_index = {
        "ev_a": {
            "evidence_id": "ev_a",
            "type": "agent_action",
            "source_kind": "agent_quote",
            "provenance_class": "observed_simulation",
            "agent_id": 1,
            "stakeholder_group": "Mieter",
            "quote": "Post A",
        },
        "ev_b": {
            "evidence_id": "ev_b",
            "type": "agent_interview",
            "source_kind": "interview_response",
            "provenance_class": "synthetic_interview",
            "agent_id": 2,
            "stakeholder_group": "Vermieter",
            "quote": "Interview B",
        },
    }
    evidence_map = {
        "evidence_index": evidence_index,
        "sections": [
            {
                "claims": [
                    {
                        "claim_id": "c1",
                        "claim_text": "Claim 1",
                        "confidence_score": 0.59,
                        "evidence": [
                            {"evidence_id": "ev_a", "supports_claim": True},
                            {"evidence_id": "ev_b", "supports_claim": True},
                        ],
                    },
                    {
                        "claim_id": "c2",
                        "claim_text": "Unbelegt",
                        "evidence": [],
                    },
                ]
            }
        ],
    }
    density = compute_evidence_density(evidence_map)
    assert density.claims_total == 2
    assert density.claims_without_support == 1
    assert density.claims_multi_support == 1
    assert density.claims_multi_independent == 1
    assert density.claims_with_action_support == 1
    assert density.claims_at_single_source_cap == 1
    assert resolve_independent_source_keys([evidence_index["ev_a"], evidence_index["ev_b"]]) == [
        ("voice", "agent:1"),
        ("voice", "agent:2"),
    ]
