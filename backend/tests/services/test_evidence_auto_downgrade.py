"""Auto-Downgrade von ``confidence_label='high'``/``'verified'`` bei
unzureichender Cross-Stakeholder-Evidence (Smoke-Live 2026-05-15).

ADR-0002 Anker 4 (``cross_stakeholder_for_high``) verlangt für ``high``-
und ``verified``-Labels mindestens 2 unterschiedliche Stakeholder-Gruppen.
LLM-Output respektiert das nicht zuverlässig; statt den ganzen Report
abzubrechen, wird der Claim auf ``medium`` ehrlich runterstuft, bevor
der Validator läuft.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.report_agent.evidence import (
    auto_downgrade_unsupported_high_claims,
    normalize_claims_for_contract,
    normalize_sections_for_contract,
)


def _claim(label: str, evidence: list[dict]) -> dict:
    return {
        "claim_id": "claim_xx",
        "text": "Test claim text mit mindestens 10 Zeichen",
        "confidence_label": label,
        "evidence": evidence,
    }


def _quote_evidence(group: str, supports: bool = True) -> dict:
    return {
        "source_kind": "agent_quote",
        "supports_claim": supports,
        "persona_stakeholder_group": group,
        "snippet": "Bla bla",
    }


def test_high_with_two_distinct_groups_unchanged() -> None:
    claim = _claim("high", [_quote_evidence("A"), _quote_evidence("B")])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "high"


def test_high_with_one_group_downgrades() -> None:
    claim = _claim("high", [_quote_evidence("A"), _quote_evidence("A")])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "medium"


def test_high_with_no_supporting_evidence_downgrades() -> None:
    claim = _claim("high", [])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "medium"


def test_high_with_only_opposing_quotes_downgrades() -> None:
    claim = _claim("high", [
        _quote_evidence("A", supports=False),
        _quote_evidence("B", supports=False),
    ])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "medium"


def test_verified_with_one_group_downgrades() -> None:
    claim = _claim("verified", [_quote_evidence("A")])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "medium"


def test_medium_low_labels_untouched() -> None:
    medium = _claim("medium", [])
    low = _claim("low", [])
    result = auto_downgrade_unsupported_high_claims([medium, low])
    assert result[0]["confidence_label"] == "medium"
    assert result[1]["confidence_label"] == "low"


def test_logger_warning_on_downgrade() -> None:
    claim = _claim("high", [_quote_evidence("A")])
    fake_logger = MagicMock()
    auto_downgrade_unsupported_high_claims([claim], logger=fake_logger)
    fake_logger.warning.assert_called_once()
    msg = fake_logger.warning.call_args[0][0]
    assert "→ 'medium'" in msg


def test_normalize_claims_for_contract_strips_legacy_fields_and_downgrades() -> None:
    claim = {
        "claim_id": "x",
        "claim": "legacy text",  # legacy alias to strip
        "confidence": "ignored",  # legacy alias to strip
        "evidence_items": "legacy",  # legacy alias to strip
        "confidence_label": "high",
        "evidence": [_quote_evidence("Only-One")],
    }
    out = normalize_claims_for_contract([claim])
    assert "claim" not in out[0]
    assert "confidence" not in out[0]
    assert "evidence_items" not in out[0]
    assert out[0]["confidence_label"] == "medium"


def test_normalize_sections_for_contract_propagates_downgrade() -> None:
    section = {
        "section_title": "Test",
        "section_summary": "Summary",
        "claims": [_claim("high", [_quote_evidence("OnlyOne")])],
    }
    out = normalize_sections_for_contract([section])
    assert out[0]["claims"][0]["confidence_label"] == "medium"


def test_normalize_sections_filters_placeholder_hypotheses() -> None:
    """LLM-Output mit ``---``/leeren ``hypothesis_text`` darf den
    Pydantic-Validator (``min_length=8``) nicht erreichen — sonst bricht
    der Report-Build (Smoke-Live 2026-05-15)."""
    section = {
        "section_title": "Test",
        "section_summary": "Summary",
        "claims": [],
        "hypotheses": [
            {"hypothesis_text": "Valide Hypothese mit genug Text", "confidence_label": "low"},
            {"hypothesis_text": "---"},  # Platzhalter → raus
            {"hypothesis_text": ""},     # leer → raus
            {"hypothesis_text": "n/a"},  # unentschieden → raus
            {"hypothesis_text": "Weitere echte Hypothese"},
        ],
    }
    out = normalize_sections_for_contract([section])
    assert len(out[0]["hypotheses"]) == 2
    assert all(h["hypothesis_text"] not in ("---", "", "n/a") for h in out[0]["hypotheses"])


def test_normalize_sections_filters_placeholder_data_gaps() -> None:
    section = {
        "section_title": "Test",
        "section_summary": "Summary",
        "claims": [],
        "data_gaps": [
            {"claim_text": "Echter offener Punkt mit Mehrtext"},
            {"claim_text": "—"},
            {"claim_text": "TBD"},
        ],
    }
    out = normalize_sections_for_contract([section])
    assert len(out[0]["data_gaps"]) == 1


def test_normalize_sections_empty_summary_gets_default() -> None:
    """Whitespace-only ``section_summary`` → Default-Fallback statt
    leer (Pydantic-Validator hat ``min_length=1``)."""
    section = {"section_title": "Test", "section_summary": "   "}
    out = normalize_sections_for_contract([section])
    assert out[0]["section_summary"] == "Recovered summary"

    # Komplett leer → genauso Default
    section2 = {"section_title": "Test", "section_summary": ""}
    out2 = normalize_sections_for_contract([section2])
    assert out2[0]["section_summary"] == "Test"
