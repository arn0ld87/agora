"""Direkttests für ``downgrade_medium_without_agent_grounded``.

Die Regel lag bis zu diesem Slice inline in
``ReportAgent._finalize_section_claims`` und war nur über eine
``__new__``-Instanz des Agents erreichbar. Als freie Funktion neben ihrer
Schwesterregel ``auto_downgrade_unsupported_high_claims`` lässt sie sich
direkt prüfen — inklusive der Randfälle, die über den Agent-Pfad nur
umständlich zu stellen waren.

ADR-0002 Stufe agent_grounded: ``medium`` verlangt mind. 1 ``agent_quote``
(mit nicht-leerem Zitat) UND mind. 1 ``seed_corpus``. Der Validator bleibt
strikt; diese Funktion sorgt dafür, dass das verletzende Label gar nicht
erst entsteht.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.report_agent.evidence import (
    downgrade_medium_without_agent_grounded,
)


def _evidence(evidence_id: str, source_kind: str, **extra: object) -> dict:
    item: dict = {
        "evidence_id": evidence_id,
        "source_kind": source_kind,
        "supports_claim": True,
        "quote": "Ein belastbares Zitat aus der Quelle.",
    }
    item.update(extra)
    return item


def _claim(label: str, evidence: list[dict], claim_id: str = "claim_01") -> dict:
    return {
        "claim_id": claim_id,
        "claim_text": "Die Migration senkt die organische Sichtbarkeit kurzfristig.",
        "confidence_label": label,
        "confidence_score": 0.55,
        "evidence": evidence,
    }


def test_medium_ohne_agent_quote_faellt_auf_low():
    claim = _claim("medium", [
        _evidence("ev_a", "seed_corpus"),
        _evidence("ev_b", "graph_relation"),
    ])

    decision = downgrade_medium_without_agent_grounded(claim)

    assert claim["confidence_label"] == "low"
    assert decision is not None
    assert decision["claim_id"] == "claim_01"
    assert decision["violation"] == "medium_without_agent_grounded_evidence"
    assert decision["action"] == "downgraded_to_low"


def test_medium_mit_agent_quote_und_seed_corpus_bleibt():
    claim = _claim("medium", [
        _evidence("ev_a", "agent_quote"),
        _evidence("ev_b", "seed_corpus"),
    ])

    decision = downgrade_medium_without_agent_grounded(claim)

    assert claim["confidence_label"] == "medium"
    assert decision is None


def test_andere_labels_bleiben_unberuehrt():
    """high/verified sind Sache der Schwesterregel, low ist bereits am Boden."""
    for label in ("low", "high", "verified"):
        claim = _claim(label, [_evidence("ev_a", "seed_corpus")], claim_id=f"c_{label}")
        decision = downgrade_medium_without_agent_grounded(claim)
        assert claim["confidence_label"] == label
        assert decision is None


def test_label_casing_wird_toleriert():
    """Der Agent-Pfad normalisierte das Label vorher selbst — die Funktion
    darf sich darauf nicht verlassen, sonst rutscht 'MEDIUM' ungeprüft durch.
    """
    claim = _claim("MEDIUM", [_evidence("ev_a", "seed_corpus")])

    decision = downgrade_medium_without_agent_grounded(claim)

    assert claim["confidence_label"] == "low"
    assert decision is not None


def test_detail_wird_auf_500_zeichen_begrenzt():
    claim = _claim("medium", [_evidence("ev_a", "seed_corpus")])

    decision = downgrade_medium_without_agent_grounded(claim)

    assert decision is not None
    assert len(decision["detail"]) <= 500


def test_logger_ist_optional_und_wird_genutzt():
    claim = _claim("medium", [_evidence("ev_a", "seed_corpus")])
    logger = MagicMock()

    downgrade_medium_without_agent_grounded(claim, logger=logger)

    assert logger.warning.called

    # ohne Logger darf nichts brechen
    claim2 = _claim("medium", [_evidence("ev_b", "seed_corpus")], claim_id="claim_02")
    assert downgrade_medium_without_agent_grounded(claim2) is not None


def test_claim_ohne_id_bekommt_platzhalter():
    claim = _claim("medium", [_evidence("ev_a", "seed_corpus")])
    del claim["claim_id"]

    decision = downgrade_medium_without_agent_grounded(claim)

    assert decision is not None
    assert decision["claim_id"] == "<no-id>"


def test_claim_ohne_evidence_faellt_ebenfalls_auf_low():
    """Der Agent-Pfad fängt evidenzlose medium-Claims schon vorher ab; die
    Funktion selbst muss den Fall trotzdem korrekt behandeln, weil sie jetzt
    unabhängig aufrufbar ist.
    """
    claim = _claim("medium", [])

    decision = downgrade_medium_without_agent_grounded(claim)

    assert claim["confidence_label"] == "low"
    assert decision is not None
