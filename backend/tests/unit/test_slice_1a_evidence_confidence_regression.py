"""Regressionstests für Slice 1A: Vereinheitlichung von Belegdichte, Provenance und Confidence (Befunde 1.1 bis 1.5)."""

from __future__ import annotations

import pytest

from app.contracts.report_evidence_contract import (
    ClaimEvidenceBindingModel,
    ConfidenceLabel,
    EvidenceRecordModel,
    EvidenceSourceKind,
)
from app.contracts.report_map_contract import (
    IndexedReportClaimModel,
    ReportSectionModel,
    _hand_work_reason,
    _require_quote_and_seed,
)
from app.services.confidence_calculator import (
    _count_independent_sources as calc_independent_sources,
)
from app.services.report_agent.claim_provenance import (
    count_supporting_voices,
    derive_confidence_scope,
    resolve_canonical_voice_keys,
)
from app.services.report_agent.evidence_claims import (
    _count_supporting_stakeholder_groups,
    has_agent_grounded_evidence,
)
from app.services.report_agent.evidence_density import (
    _supporting_entries,
)
from app.services.report_agent.manager_claims import (
    _count_independent_sources as manager_independent_sources,
)


# ---------------------------------------------------------------------------
# Befund 1.1: Kanonischer Index autoritativ + Filter auf disqualifizierende Klassen
# ---------------------------------------------------------------------------


def test_befund_1_1_canonical_index_overrides_claim_inline_fields():
    claim = {
        "evidence": [
            # Inline behauptet supports_claim=True, kanonischer Index sagt supports_claim=False
            {"evidence_id": "ev-1", "supports_claim": True},
        ]
    }
    evidence_index = {
        "ev-1": {"evidence_id": "ev-1", "supports_claim": False, "source_kind": "seed_corpus"}
    }
    supporting = _supporting_entries(claim, evidence_index)
    assert len(supporting) == 0


def test_befund_1_1_disqualifying_provenance_classes_excluded():
    claim = {
        "evidence": [
            {"evidence_id": "scaffold", "supports_claim": True},
            {"evidence_id": "hypo", "supports_claim": True},
            {"evidence_id": "unver", "supports_claim": True},
            {"evidence_id": "inferred_class", "supports_claim": True},
            {"evidence_id": "inferred_kind", "supports_claim": True},
            {"evidence_id": "manual_origin", "supports_claim": True},
            {"evidence_id": "valid", "supports_claim": True},
        ]
    }
    evidence_index = {
        "scaffold": {
            "evidence_id": "scaffold",
            "supports_claim": True,
            "provenance_class": "template_scaffold",
        },
        "hypo": {"evidence_id": "hypo", "supports_claim": True, "provenance_class": "hypothesis"},
        "unver": {"evidence_id": "unver", "supports_claim": True, "provenance_class": "unverified"},
        "inferred_class": {
            "evidence_id": "inferred_class",
            "supports_claim": True,
            "provenance_class": "inferred",
        },
        "inferred_kind": {
            "evidence_id": "inferred_kind",
            "supports_claim": True,
            "source_kind": "inferred",
        },
        "manual_origin": {
            "evidence_id": "manual_origin",
            "supports_claim": True,
            "graph_origin": "manual",
        },
        "valid": {
            "evidence_id": "valid",
            "supports_claim": True,
            "source_kind": "seed_corpus",
            "type": "document",
        },
    }
    supporting = _supporting_entries(claim, evidence_index)
    assert len(supporting) == 1
    assert supporting[0]["evidence_id"] == "valid"


# ---------------------------------------------------------------------------
# Befund 1.2: Unabhängige Quellen über Seed-Dokumente & Übereinstimmung
# ---------------------------------------------------------------------------


def test_befund_1_2_seed_chunks_same_doc_deduplicated_to_single_source():
    # Zwei Chunks aus demselben Seed-Dokument
    evidence = [
        {
            "evidence_id": "chunk_1",
            "source_kind": "seed_corpus",
            "doc_id": "doc_budget_2026",
            "supports_claim": True,
        },
        {
            "evidence_id": "chunk_2",
            "source_kind": "seed_corpus",
            "doc_id": "doc_budget_2026",
            "supports_claim": True,
        },
    ]

    calc_count = calc_independent_sources(evidence)
    assert calc_count == 1

    refs = ["chunk_1", "chunk_2"]
    index = {e["evidence_id"]: e for e in evidence}
    mgr_count = manager_independent_sources(refs, evidence, index)
    assert mgr_count == 1
    assert calc_count == mgr_count


def test_befund_1_2_source_id_anchor_deduplication():
    # Deduplizierung über source_id_anchor (seed_doc:<id>#chunk)
    evidence = [
        {
            "evidence_id": "anchor_1",
            "source_kind": "seed_corpus",
            "source_id_anchor": "seed_doc:plan_a#p1",
            "supports_claim": True,
        },
        {
            "evidence_id": "anchor_2",
            "source_kind": "seed_corpus",
            "source_id_anchor": "seed_doc:plan_a#p2",
            "supports_claim": True,
        },
        {
            "evidence_id": "anchor_3",
            "source_kind": "seed_corpus",
            "source_id_anchor": "seed_doc:plan_b#p1",
            "supports_claim": True,
        },
    ]
    assert calc_independent_sources(evidence) == 2


def test_befund_1_2_source_id_anchor_preserves_colons_in_doc_ids():
    # Dateinamen mit Doppelpunkten führen zu Anchors wie seed_doc:budget:2025#chunk:0
    # Diese dürfen nicht zu doc:budget kollabieren, sondern müssen als zwei
    # unabhängige Dokumente gezählt werden.
    evidence = [
        {
            "evidence_id": "b2025_c0",
            "source_kind": "seed_corpus",
            "source_id_anchor": "seed_doc:budget:2025#chunk:0",
            "supports_claim": True,
        },
        {
            "evidence_id": "b2025_c1",
            "source_kind": "seed_corpus",
            "source_id_anchor": "seed_doc:budget:2025#chunk:1",
            "supports_claim": True,
        },
        {
            "evidence_id": "b2026_c0",
            "source_kind": "seed_corpus",
            "source_id_anchor": "seed_doc:budget:2026#chunk:0",
            "supports_claim": True,
        },
    ]
    assert calc_independent_sources(evidence) == 2

    refs = ["b2025_c0", "b2025_c1", "b2026_c0"]
    index = {e["evidence_id"]: e for e in evidence}
    assert manager_independent_sources(refs, evidence, index) == 2


# ---------------------------------------------------------------------------
# Befund 1.3: Group-Fallback Kollision mit bekanntem Sprecher derselben Gruppe
# ---------------------------------------------------------------------------


def test_befund_1_3_group_fallback_collides_with_known_speaker():
    # Beleg 1: Konkreter Agent 1 mit Gruppe 'Bürger'
    # Beleg 2: Nur Gruppe 'Bürger' gesetzt (anonym)
    pairs = [
        ({"agent_id": "1", "stakeholder_group": "Bürger"}, None),
        ({"stakeholder_group": "Bürger"}, None),
    ]
    voice_keys = resolve_canonical_voice_keys(pairs)
    assert len(set(voice_keys)) == 1
    assert voice_keys[0] == "agent:1"
    assert voice_keys[1] == "agent:1"

    raw_evidence = [
        {
            "evidence_id": "ev1",
            "agent_id": "1",
            "persona_stakeholder_group": "Bürger",
            "supports_claim": True,
        },
        {"evidence_id": "ev2", "persona_stakeholder_group": "Bürger", "supports_claim": True},
    ]
    assert count_supporting_voices(raw_evidence) == 1
    # Scope muss Einzelstimme sein, kein Scheinkonsens!
    assert derive_confidence_scope(raw_evidence) == "simulation_single_voice"


def test_befund_1_3_distinct_groups_remain_separate():
    pairs = [
        ({"agent_id": "1", "stakeholder_group": "Bürger"}, None),
        ({"stakeholder_group": "Verwaltung"}, None),
    ]
    voice_keys = resolve_canonical_voice_keys(pairs)
    assert len(set(voice_keys)) == 2


# ---------------------------------------------------------------------------
# Befund 1.4: Contradicting & Manual Quotes/Seeds abgelehnt
# ---------------------------------------------------------------------------


def test_befund_1_4_has_agent_grounded_evidence_rejects_contradicting_and_manual():
    # Agent-Quote widerspricht dem Claim (supports_claim=False)
    contradicting_quote = [
        {"evidence_id": "q1", "source_kind": "agent_quote", "quote": "Ja", "supports_claim": False},
        {"evidence_id": "s1", "source_kind": "seed_corpus", "supports_claim": True},
    ]
    assert not has_agent_grounded_evidence(contradicting_quote)

    # Seed widerspricht dem Claim (supports_claim=False)
    contradicting_seed = [
        {"evidence_id": "q1", "source_kind": "agent_quote", "quote": "Ja", "supports_claim": True},
        {"evidence_id": "s1", "source_kind": "seed_corpus", "supports_claim": False},
    ]
    assert not has_agent_grounded_evidence(contradicting_seed)

    # Quote stammt aus manueller Bearbeitung (graph_origin="manual")
    manual_quote = [
        {
            "evidence_id": "q1",
            "source_kind": "agent_quote",
            "quote": "Ja",
            "supports_claim": True,
            "graph_origin": "manual",
        },
        {"evidence_id": "s1", "source_kind": "seed_corpus", "supports_claim": True},
    ]
    assert not has_agent_grounded_evidence(manual_quote)


def test_befund_1_4_require_quote_and_seed_rejects_contradicting():
    section = ReportSectionModel(
        section_index=1,
        section_title="Titel der Section",
        section_summary="Zusammenfassung der Section",
    )
    claim = IndexedReportClaimModel(
        claim_id="claim_01",
        claim_text="Gueltiger Claim-Text fuer den Test",
        confidence_label=ConfidenceLabel.medium,
        confidence_score=0.7,
        evidence=[
            ClaimEvidenceBindingModel(
                evidence_id="ev_11111111111111111111111111111111", supports_claim=False
            ),
            ClaimEvidenceBindingModel(
                evidence_id="ev_22222222222222222222222222222222", supports_claim=True
            ),
        ],
    )
    resolved = [
        (
            claim.evidence[0],
            EvidenceRecordModel(
                evidence_id="ev_11111111111111111111111111111111",
                source_kind=EvidenceSourceKind.agent_quote,
                persona_stakeholder_group="Bürger",
                producer_key="interviews",
                type="agent_interview",
                source="interview_01",
                snippet="Snippet des Zitats",
                quote="Wortlaut",
            ),
        ),
        (
            claim.evidence[1],
            EvidenceRecordModel(
                evidence_id="ev_22222222222222222222222222222222",
                source_kind=EvidenceSourceKind.seed_corpus,
                producer_key="seed_corpus",
                type="seed_document",
                source="seed_01",
                snippet="Snippet des Seeds",
            ),
        ),
    ]
    with pytest.raises(ValueError, match="medium verlangt agent_quote und seed_corpus"):
        _require_quote_and_seed(section, claim, resolved)


# ---------------------------------------------------------------------------
# Befund 1.5: Stakeholder-Gruppen filtern Handarbeit & Handwork-Reason für Verified
# ---------------------------------------------------------------------------


def test_befund_1_5_manual_quote_excluded_from_supporting_stakeholder_groups():
    evidence = [
        {
            "source_kind": "agent_quote",
            "persona_stakeholder_group": "Bürger",
            "supports_claim": True,
            "graph_origin": "manual",
        },
        {
            "source_kind": "agent_quote",
            "persona_stakeholder_group": "Gewerbe",
            "supports_claim": True,
        },
    ]
    # Nur Gewerbe darf zählen, Bürger hat graph_origin="manual"
    assert _count_supporting_stakeholder_groups(evidence) == 1


def test_befund_1_5_hand_work_reason_detects_insufficient_sources_for_verified():
    # Ein Claim mit verified braucht mindestens 2 stützende Quellen.
    # Wenn nach Abzug von Handarbeit nur 1 stützende Quelle übrig bleibt:
    claim = IndexedReportClaimModel(
        claim_id="claim_01",
        claim_text="Gueltiger Claim-Text fuer den Test",
        confidence_label=ConfidenceLabel.verified,
        confidence_score=0.92,
        evidence=[
            ClaimEvidenceBindingModel(
                evidence_id="ev_11111111111111111111111111111111",
                supports_claim=True,
                match_score=0.9,
            ),
            ClaimEvidenceBindingModel(
                evidence_id="ev_22222222222222222222222222222222",
                supports_claim=True,
                match_score=0.9,
            ),
        ],
    )
    # Nur ev_1 zählt (ev_2 war Handarbeit und ist in counted nicht mehr enthalten)
    counted = [claim.evidence[0]]
    reason = _hand_work_reason(claim, counted)
    assert reason == "mindestens zwei stuetzende Quellen nur mit solcher Evidence"
