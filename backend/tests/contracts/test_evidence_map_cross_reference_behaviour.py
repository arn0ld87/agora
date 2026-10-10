"""Verhaltensfestlegung fuer ``EvidenceMapModel.validate_evidence_cross_references``.

Deckt die Regeln ab, die der Zerlegungs-Slice (Komplexitaets-Gate MAI-17)
auseinanderzieht: Index-/Ledger-Integritaet, die medium-Regel, die
inferred-Sperre fuer high/verified und die drei Begruendungen der
ADR-0022-Pruefung. Die Tests entstanden **vor** dem Refactoring und
beschreiben das Verhalten von Branch ``uebernahme/1808``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import EvidenceMapModel

EV_QUOTE_A = "ev_000000000000000000000000000000aa"
EV_QUOTE_B = "ev_000000000000000000000000000000bb"
EV_SEED = "ev_000000000000000000000000000000cc"
EV_INFERRED = "ev_000000000000000000000000000000dd"
EV_MANUAL = "ev_000000000000000000000000000000ee"
UNKNOWN_ID = "ev_ffffffffffffffffffffffffffffffff"


def _quote(evidence_id: str, group: str, *, family: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "evidence_id": evidence_id,
        "producer_key": f"interview:{group}",
        "type": "agent_interview",
        "source": "report_tool",
        "snippet": f"Persona aus {group}: Beispiel-Aussage.",
        "quote": f"Original-Zitat aus {group}.",
        "source_kind": "agent_quote",
        "persona_stakeholder_group": group,
    }
    if family is not None:
        record["persona_role_family"] = family
    return record


def _seed(evidence_id: str = EV_SEED) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "producer_key": "seed-corpus:doc-a1:7",
        "type": "seed_document",
        "source": "report_tool",
        "snippet": "Passage aus dem Seed-Korpus.",
        "source_kind": "seed_corpus",
    }


def _inferred(evidence_id: str = EV_INFERRED) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "producer_key": "model:opus",
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Aus dem Modell abgeleiteter Fakt.",
        "source_kind": "inferred",
    }


def _manual(evidence_id: str = EV_MANUAL) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "producer_key": "graph-fact:hand",
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Von Hand eingetragener Fakt.",
        "source_kind": "graph_relation",
        "graph_origin": "manual",
    }


def _binding(evidence_id: str, *, score: float = 0.7, supports: bool = True) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "match_score": score,
        "entailment": "SUPPORTED",
        "supports_claim": supports,
    }


def _map(records: dict[str, dict[str, Any]], bindings: list[dict[str, Any]], *, label: str, score: float = 0.86) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "report_id": "report-xref",
        "simulation_id": "run-xref",
        "evidence_index": records,
        "global_evidence_refs": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Zusammenfassung der beobachteten Wirkung.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Reform wird von mehreren Gruppen getragen.",
                        "confidence_label": label,
                        "confidence_score": score,
                        "evidence": bindings,
                    }
                ],
            }
        ],
    }


_TWO_GROUPS = {
    EV_QUOTE_A: _quote(EV_QUOTE_A, "Buerger", family="buergerschaft"),
    EV_QUOTE_B: _quote(EV_QUOTE_B, "Verwaltung", family="verwaltung"),
}


# ── Index- und Ledger-Integritaet ─────────────────────────────────────────


def test_index_key_must_equal_evidence_id() -> None:
    payload = _map(dict(_TWO_GROUPS), [_binding(EV_QUOTE_A), _binding(EV_QUOTE_B)], label="high")
    payload["evidence_index"] = {UNKNOWN_ID: _TWO_GROUPS[EV_QUOTE_A]}

    with pytest.raises(ValidationError, match="evidence_index-Key"):
        EvidenceMapModel.model_validate(payload)


def test_unknown_global_ref_is_rejected() -> None:
    payload = _map(dict(_TWO_GROUPS), [_binding(EV_QUOTE_A), _binding(EV_QUOTE_B)], label="high")
    payload["global_evidence_refs"] = [UNKNOWN_ID]

    with pytest.raises(ValidationError, match="global_evidence_refs enthalten unbekannte Evidence"):
        EvidenceMapModel.model_validate(payload)


def test_unknown_claim_binding_names_section_and_claim() -> None:
    payload = _map(
        dict(_TWO_GROUPS), [_binding(EV_QUOTE_A), _binding(UNKNOWN_ID)], label="high"
    )

    with pytest.raises(ValidationError, match="Section 1 Claim claim_01 referenziert unbekannte"):
        EvidenceMapModel.model_validate(payload)


def test_ledger_row_pointing_into_the_void_is_rejected() -> None:
    payload = _map(dict(_TWO_GROUPS), [_binding(EV_QUOTE_A), _binding(EV_QUOTE_B)], label="high")
    payload["evidence_coverage_ledger"] = [
        {
            "source_result_id": "tool:42",
            "fact": "42 Prozent",
            "status": "canonicalized",
            "canonical_evidence_id": UNKNOWN_ID,
        }
    ]

    with pytest.raises(ValidationError, match="evidence_coverage_ledger verweist auf unbekannte"):
        EvidenceMapModel.model_validate(payload)


def test_dropped_ledger_row_needs_no_canonical_id() -> None:
    """Eine ehrliche ``dropped``-Zeile ist kein Verweis ins Leere."""
    payload = _map(dict(_TWO_GROUPS), [_binding(EV_QUOTE_A), _binding(EV_QUOTE_B)], label="high")
    payload["evidence_coverage_ledger"] = [
        {"source_result_id": "tool:42", "fact": "42 Prozent", "status": "dropped", "reason": "Dublette"}
    ]

    EvidenceMapModel.model_validate(payload)


# ── medium: agent_quote und seed_corpus ───────────────────────────────────


def test_medium_accepts_quote_plus_seed() -> None:
    records = {**_TWO_GROUPS, EV_SEED: _seed()}
    payload = _map(records, [_binding(EV_QUOTE_A), _binding(EV_SEED)], label="medium", score=0.7)

    assert EvidenceMapModel.model_validate(payload).sections[0].claims[0].confidence_label == "medium"


def test_medium_requires_both_sources() -> None:
    """Nur Zitate, kein ``seed_corpus`` — medium ist nicht erfuellt."""
    records: dict[str, dict[str, Any]] = {
        EV_QUOTE_A: _quote(EV_QUOTE_A, "Buerger", family="buergerschaft"),
        EV_SEED: _seed(),
    }
    payload = _map(records, [_binding(EV_QUOTE_A)], label="medium", score=0.7)

    with pytest.raises(ValidationError, match="medium verlangt agent_quote und seed_corpus"):
        EvidenceMapModel.model_validate(payload)


def test_medium_rule_precedes_the_graph_origin_rule() -> None:
    """Reihenfolge-Festlegung: die medium-Regel schlaegt zuerst zu.

    Ein Claim, der allein an Handarbeit haengt, erfuellt medium ohnehin nicht
    (agent_quote und seed_corpus fehlen) — die medium-Meldung kommt zuerst.
    """
    records = {**_TWO_GROUPS, EV_MANUAL: _manual()}
    payload = _map(records, [_binding(EV_MANUAL, score=0.95)], label="medium", score=0.7)

    with pytest.raises(ValidationError, match="medium verlangt agent_quote und seed_corpus"):
        EvidenceMapModel.model_validate(payload)


def test_medium_needs_a_quote_text_not_just_the_source_kind() -> None:
    """``agent_quote`` ohne ``quote``-Feld zaehlt fuer medium nicht."""
    bare = deepcopy(_quote(EV_QUOTE_A, "Buerger", family="buergerschaft"))
    bare.pop("quote")
    records = {EV_QUOTE_A: bare, EV_SEED: _seed()}
    payload = _map(records, [_binding(EV_QUOTE_A), _binding(EV_SEED)], label="medium", score=0.7)

    with pytest.raises(ValidationError, match="medium verlangt agent_quote und seed_corpus"):
        EvidenceMapModel.model_validate(payload)


# ── medium: zwei Aktionsstimmen (ADR-0002-Nachtrag 2026-10-10, #1778) ─────

EV_ACTION_A = "ev_000000000000000000000000000000a1"
EV_ACTION_B = "ev_000000000000000000000000000000a2"


def _action(evidence_id: str, voice_key: str) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "producer_key": f"simulation-action:{voice_key}",
        "type": "agent_action",
        "source": "simulation_actions",
        "snippet": f"Beitrag von {voice_key} in der Simulation.",
        "source_kind": "agent_action",
        "voice_key": voice_key,
    }


def test_medium_accepts_two_action_voices() -> None:
    records = {EV_ACTION_A: _action(EV_ACTION_A, "agent:1"), EV_ACTION_B: _action(EV_ACTION_B, "agent:2")}
    payload = _map(records, [_binding(EV_ACTION_A), _binding(EV_ACTION_B)], label="medium", score=0.7)

    assert EvidenceMapModel.model_validate(payload).sections[0].claims[0].confidence_label == "medium"


def test_medium_rejects_two_actions_of_the_same_voice() -> None:
    records = {EV_ACTION_A: _action(EV_ACTION_A, "agent:1"), EV_ACTION_B: _action(EV_ACTION_B, "agent:1")}
    payload = _map(records, [_binding(EV_ACTION_A), _binding(EV_ACTION_B)], label="medium", score=0.7)

    with pytest.raises(ValidationError, match="medium verlangt agent_quote und seed_corpus"):
        EvidenceMapModel.model_validate(payload)


def test_medium_rejects_a_non_supporting_second_action_voice() -> None:
    records = {EV_ACTION_A: _action(EV_ACTION_A, "agent:1"), EV_ACTION_B: _action(EV_ACTION_B, "agent:2")}
    payload = _map(
        records, [_binding(EV_ACTION_A), _binding(EV_ACTION_B, supports=False)], label="medium", score=0.7
    )

    with pytest.raises(ValidationError, match="medium verlangt agent_quote und seed_corpus"):
        EvidenceMapModel.model_validate(payload)


def test_high_stays_blocked_for_two_action_voices() -> None:
    records = {EV_ACTION_A: _action(EV_ACTION_A, "agent:1"), EV_ACTION_B: _action(EV_ACTION_B, "agent:2")}
    payload = _map(records, [_binding(EV_ACTION_A), _binding(EV_ACTION_B)], label="high")

    with pytest.raises(ValidationError, match="high/verified verlangt zwei stuetzende Stakeholder-Gruppen"):
        EvidenceMapModel.model_validate(payload)


# ── high/verified: inferred ist unzulaessig ───────────────────────────────


def test_high_rejects_inferred_evidence_among_two_groups() -> None:
    records = {**_TWO_GROUPS, EV_INFERRED: _inferred()}
    payload = _map(
        records, [_binding(EV_QUOTE_A), _binding(EV_QUOTE_B), _binding(EV_INFERRED)], label="high"
    )

    with pytest.raises(ValidationError, match="inferred Evidence ist fuer high/verified unzulaessig"):
        EvidenceMapModel.model_validate(payload)


def test_low_label_tolerates_inferred_evidence() -> None:
    records = {**_TWO_GROUPS, EV_INFERRED: _inferred()}
    payload = _map(records, [_binding(EV_INFERRED)], label="low", score=0.4)

    assert EvidenceMapModel.model_validate(payload).sections[0].claims[0].confidence_label == "low"


# ── ADR-0022: Handarbeit traegt kein Label allein ─────────────────────────


def test_verified_blames_graph_evidence_that_carries_the_strong_match() -> None:
    """Der einzige heute erreichbare ADR-0022-Fall.

    Zwei Gruppen tragen ``high`` ueber ``supports_claim=True``; die
    ``match_score``-Schwelle des ``verified``-Labels erreicht allein die
    Handevidence. Genau das wird benannt.
    """
    records = {**_TWO_GROUPS, EV_MANUAL: _manual()}
    payload = _map(
        records,
        [
            _binding(EV_MANUAL, score=0.95, supports=True),
            _binding(EV_QUOTE_A, supports=True),
            _binding(EV_QUOTE_B, supports=True),
        ],
        label="verified",
        score=0.93,
    )

    with pytest.raises(ValidationError, match="match_score >= 0.85 nur an solcher Evidence"):
        EvidenceMapModel.model_validate(payload)


def test_two_of_three_adr0022_reasons_are_unreachable_by_construction() -> None:
    """Die Begruendungen ``ausschliesslich...`` und ``supports_claim=True...``
    koennen heute nicht ausgeloest werden — das wird hier festgehalten, damit
    ein spaeterer Umbau sie nicht unbemerkt wieder entstehbar macht.

    Begruendung 1 (``counted`` leer) setzt voraus, dass kein
    Confidence-tragender Beleg gebunden ist. Fuer ``high``/``verified`` verlangt
    die Stakeholder-Regel zwei stuetzende ``agent_quote``-Gruppen, fuer
    ``medium`` ein ``agent_quote`` *und* ein ``seed_corpus``. Beides kann kein
    ``graph_relation`` mit ``graph_origin`` sein (``graph_origin`` verlangt
    ``source_kind=graph_relation``), also waere mindestens ein ``counted``
    Beleg gebunden.

    Begruendung 2 (``supports_claim=True`` nur an solcher Evidence) verlangt
    umgekehrt, dass keinzaehliger Beleg traegt. Die zwei stuetzenden Gruppen
    fuer ``high``/``verified`` sind aber genau diese ``counted`` Belege.
    """
    nur_handarbeit = _map(
        {EV_MANUAL: _manual()}, [_binding(EV_MANUAL, score=0.95, supports=True)], label="high"
    )
    supports_nur_an_handarbeit = _map(
        {**_TWO_GROUPS, EV_MANUAL: _manual()},
        [
            _binding(EV_MANUAL, score=0.9, supports=True),
            _binding(EV_QUOTE_A, supports=False),
            _binding(EV_QUOTE_B, supports=False),
        ],
        label="high",
    )
    for payload in (nur_handarbeit, supports_nur_an_handarbeit):
        with pytest.raises(ValidationError, match="stuetzende Stakeholder-Gruppen"):
            EvidenceMapModel.model_validate(payload)


def test_high_stays_valid_when_met_without_manual_evidence() -> None:
    """Die harte Regel greift nur, wenn die Handarbeit das Label *rettet*."""
    records = {**_TWO_GROUPS, EV_MANUAL: _manual()}
    payload = _map(
        records,
        [_binding(EV_MANUAL, score=0.95), _binding(EV_QUOTE_A), _binding(EV_QUOTE_B)],
        label="high",
    )

    assert EvidenceMapModel.model_validate(payload).sections[0].claims[0].confidence_label == "high"


def test_hand_made_evidence_may_join_a_fully_met_claim() -> None:
    """Handevidence neben zwei traegenden Gruppen: ``medium`` bleibt gueltig."""
    records = {
        EV_QUOTE_A: _quote(EV_QUOTE_A, "Buerger"),
        EV_SEED: _seed(),
        EV_MANUAL: _manual(),
    }
    payload = _map(
        records,
        [_binding(EV_QUOTE_A), _binding(EV_SEED), _binding(EV_MANUAL)],
        label="medium",
        score=0.7,
    )

    assert EvidenceMapModel.model_validate(payload).sections[0].claims[0].confidence_label == "medium"


@pytest.mark.parametrize("label", ["low", "speculative"])
def test_hand_made_evidence_may_carry_a_visible_low_label(label: str) -> None:
    records = {**_TWO_GROUPS, EV_MANUAL: _manual()}
    payload = _map(records, [_binding(EV_MANUAL, score=0.95)], label=label, score=0.3)

    assert EvidenceMapModel.model_validate(payload).sections[0].claims[0].confidence_label == label
