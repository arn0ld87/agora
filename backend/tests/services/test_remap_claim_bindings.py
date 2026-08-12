"""Regressionstests für ``_remap_claim_bindings`` — Issue #1277-6.

Bisher war die Deduplizierung bei ID-Kollision First-Wins
(``merged.setdefault(target, binding)``): die schwächere Bindung konnte die
stärkere still verdrängen, wenn sie zuerst kam. Der Docstring versprach ein
Zusammenführen. Jetzt gewinnt die stärkere Bindung (Entailment-Rang, Tie-Break
über ``match_score``).
"""
from __future__ import annotations

from app.services.report_agent.agent import _remap_claim_bindings


def test_remap_keeps_strongest_entailment_on_id_collision() -> None:
    """#1277-6: Zwei Bindungen, die auf dieselbe Ziel-ID gemapt werden — die
    stärkere (SUPPORTED) gewinnt unabhängig von der Reihenfolge.

    Vor dem Fix: ``setdefault`` behielt die erste Bindung (RELATED_ONLY) und
    verwarf die SUPPORTED-Bindung. In ``_finalize_section_claims`` blieb
    ``supporting_ids`` leer und der Claim wanderte mit Gate-Entscheidung
    ``no_supporting_evidence`` in die Hypothesen.
    """
    claims = [{
        "evidence": [
            {"evidence_id": "ev_weak", "entailment": "RELATED_ONLY",
             "match_score": 0.3},
            {"evidence_id": "ev_strong", "entailment": "SUPPORTED",
             "match_score": 0.9},
        ],
    }]
    id_remap = {"ev_weak": "ev_target", "ev_strong": "ev_target"}

    result = _remap_claim_bindings(claims, id_remap)
    bindings = result[0]["evidence"]
    assert len(bindings) == 1, (
        f"eine Bindung nach Merge erwartet, bekam {len(bindings)}: {bindings}"
    )
    assert bindings[0]["evidence_id"] == "ev_target"
    assert bindings[0]["entailment"] == "SUPPORTED"
    assert bindings[0]["match_score"] == 0.9


def test_remap_strongest_wins_regardless_of_order() -> None:
    """#1277-6 Guard: auch wenn die stärkere Bindung zuerst kommt, bleibt sie —
    der Stärke-Vergleich darf nicht von der Reihenfolge abhängen.
    """
    claims = [{
        "evidence": [
            {"evidence_id": "ev_strong", "entailment": "SUPPORTED",
             "match_score": 0.9},
            {"evidence_id": "ev_weak", "entailment": "RELATED_ONLY",
             "match_score": 0.3},
        ],
    }]
    id_remap = {"ev_weak": "ev_target", "ev_strong": "ev_target"}

    result = _remap_claim_bindings(claims, id_remap)
    bindings = result[0]["evidence"]
    assert len(bindings) == 1
    assert bindings[0]["entailment"] == "SUPPORTED"
    assert bindings[0]["match_score"] == 0.9


def test_remap_tiebreak_uses_match_score_when_entailment_equal() -> None:
    """#1277-6: Bei gleichem Entailment-Rang entscheidet der höhere match_score."""
    claims = [{
        "evidence": [
            {"evidence_id": "ev_a", "entailment": "SUPPORTED",
             "match_score": 0.7},
            {"evidence_id": "ev_b", "entailment": "SUPPORTED",
             "match_score": 0.9},
        ],
    }]
    id_remap = {"ev_a": "ev_target", "ev_b": "ev_target"}

    result = _remap_claim_bindings(claims, id_remap)
    bindings = result[0]["evidence"]
    assert len(bindings) == 1
    assert bindings[0]["match_score"] == 0.9


def test_remap_without_collision_keeps_all_bindings() -> None:
    """#1277-6 Guard: ohne ID-Kollision bleibt jede Bindung erhalten."""
    claims = [{
        "evidence": [
            {"evidence_id": "ev_a", "entailment": "SUPPORTED",
             "match_score": 0.9},
            {"evidence_id": "ev_b", "entailment": "RELATED_ONLY",
             "match_score": 0.3},
        ],
    }]
    id_remap = {"ev_a": "ev_a_new"}

    result = _remap_claim_bindings(claims, id_remap)
    bindings = result[0]["evidence"]
    assert len(bindings) == 2
    ids = {b["evidence_id"] for b in bindings}
    assert ids == {"ev_a_new", "ev_b"}


def test_remap_preserves_non_evidence_bindings() -> None:
    """#1277-6 Guard: Bindungen ohne evidence_id (z. B. Legacy-Einträge)
    bleiben unangetastet und werden den gemergten vorangestellt."""
    claims = [{
        "evidence": [
            {"note": "Legacy-Eintrag ohne ID"},
            {"evidence_id": "ev_a", "entailment": "SUPPORTED",
             "match_score": 0.9},
            {"evidence_id": "ev_b", "entailment": "SUPPORTED",
             "match_score": 0.7},
        ],
    }]
    id_remap = {"ev_a": "ev_target", "ev_b": "ev_target"}

    result = _remap_claim_bindings(claims, id_remap)
    bindings = result[0]["evidence"]
    # Legacy-Eintrag + 1 gemergte Bindung
    assert len(bindings) == 2
    assert bindings[0] == {"note": "Legacy-Eintrag ohne ID"}
    assert bindings[1]["evidence_id"] == "ev_target"
    assert bindings[1]["match_score"] == 0.9