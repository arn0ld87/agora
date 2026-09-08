"""Regression zur Confidence-Label-Ableitung in ``_extract_claims_for_section``.

Aus der Kette wurden drei unerreichbare ``elif``-Zweige entfernt
("high"/"verified" → "high", "medium" → "medium", "low" → "low"). Sie konnten
nie feuern: ihre Labels liegen samt und sonders in ``_valid_confidence`` und
wurden bereits vom ersten Zweig abgefangen. Diese Tests halten fest, dass die
Ableitung sich für jedes Label unverändert verhält — insbesondere für die
Labels, die jene toten Zweige vorgaben zu behandeln.
"""

from __future__ import annotations

import pytest

from app.services.report_agent.manager import _extract_claims_for_section


def _claim(label: str, evidence_count: int = 2) -> dict:
    return {
        "claim_id": "claim_01",
        "claim_text": "Die Migration senkt die organische Sichtbarkeit kurzfristig.",
        "confidence_label": label,
        "evidence": [
            {"evidence_id": f"ev_{i}", "supports_claim": True}
            for i in range(evidence_count)
        ],
    }


@pytest.mark.parametrize(
    "label,erwartet",
    [
        ("speculative", "speculative"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("verified", "verified"),
    ],
)
def test_bekannte_labels_werden_unveraendert_uebernommen(label, erwartet):
    claims = _extract_claims_for_section(
        [_claim(label)], section_index=1, evidence_index={}, report_mode="balanced"
    )

    assert len(claims) == 1
    assert claims[0].confidence == erwartet


@pytest.mark.parametrize("label", ["", "unbekannt", "HIGH", "Medium", "sehr sicher"])
def test_unbekannte_labels_fallen_auf_speculative(label):
    """Casing zaehlt: 'HIGH' ist kein bekanntes Label und faellt zurueck.

    Das war vor dem Entfernen der toten Zweige genauso — der erste Zweig
    prueft exakte Mitgliedschaft, nicht case-insensitiv.
    """
    claims = _extract_claims_for_section(
        [_claim(label)], section_index=1, evidence_index={}, report_mode="balanced"
    )

    assert len(claims) == 1
    assert claims[0].confidence == "speculative"


def test_fehlendes_label_faellt_auf_speculative():
    claim = _claim("low")
    del claim["confidence_label"]

    claims = _extract_claims_for_section(
        [claim], section_index=1, evidence_index={}, report_mode="balanced"
    )

    assert claims[0].confidence == "speculative"


@pytest.mark.parametrize("label", ["medium", "high", "verified"])
def test_single_source_stuft_ab_und_merkt_den_wortlaut(label):
    """Eine einzige stuetzende Quelle traegt kein medium/high/verified."""
    claims = _extract_claims_for_section(
        [_claim(label, evidence_count=1)],
        section_index=1,
        evidence_index={},
        report_mode="balanced",
    )

    assert claims[0].confidence == "low"
    assert claims[0].text_confidence == label


def test_strict_mode_droppt_speculative_und_low():
    claims = _extract_claims_for_section(
        [_claim("speculative"), _claim("low"), _claim("high")],
        section_index=1,
        evidence_index={},
        report_mode="strict",
    )

    assert [c.confidence for c in claims] == ["high"]


def test_ids_zaehlen_nur_akzeptierte_claims():
    """Issue #1341: die ID beschreibt die finale Liste, nicht die Rohextraktion."""
    ohne_evidence = _claim("high", evidence_count=0)
    claims = _extract_claims_for_section(
        [ohne_evidence, _claim("high"), _claim("high")],
        section_index=3,
        evidence_index={},
        report_mode="balanced",
    )

    assert [c.id for c in claims] == ["C3_01", "C3_02"]
