"""Auto-Downgrade von ``confidence_label='high'``/``'verified'`` bei
unzureichender Cross-Stakeholder-Evidence (Smoke-Live 2026-05-15).

ADR-0002 Anker 4 (``cross_stakeholder_for_high``) verlangt für ``high``-
und ``verified``-Labels mindestens 2 unterschiedliche Stakeholder-Gruppen.
LLM-Output respektiert das nicht zuverlässig; statt den ganzen Report
abzubrechen, wird der Claim ehrlich runtergestuft, bevor der Validator läuft.

Issue #906 (Defekt 2): Der Zielwert ist nicht mehr pauschal ``medium``,
sonsten hängt vom Provenance-Mix ab — ADR-0002 Stufe agent_grounded
(``agent_quote`` + ``seed_corpus``) trägt ``medium``, Seed-only bzw.
reine Agent-Quote ohne Korpusbezug fallen auf ``low``. Damit bestünde
der downgegradete Claim den nachfolgenden ``medium``-Validator (Issue
#906 Defekt 1) und verhinderte gerade den harten Abbruch, den auto_downgrade
vermeiden soll.
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


def _seed_evidence(supports: bool = True) -> dict:
    return {
        "source_kind": "seed_corpus",
        "supports_claim": supports,
        "snippet": "Seed-Dokument-Auszug mit genug Text.",
    }


# ---- Zielwert high bleibt: ≥2 Stakeholder-Gruppen -------------------------


def test_high_with_two_distinct_groups_unchanged() -> None:
    claim = _claim("high", [_quote_evidence("A"), _quote_evidence("B")])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "high"


def test_high_with_two_groups_and_seed_unchanged() -> None:
    """seed_corpus stört nicht — bei ≥2 Gruppen bleibt high."""
    claim = _claim("high", [_quote_evidence("A"), _quote_evidence("B"), _seed_evidence()])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "high"


# ---- Downgrade auf medium: agent_grounded (agent_quote + seed_corpus) -----


def test_high_with_one_group_and_seed_downgrades_to_medium() -> None:
    """1 Stakeholder-Gruppe, aber agent_quote + seed_corpus vorhanden →
    ADR-0002 agent_grounded rechtfertigt medium (Issue #906 Teststrategie)."""
    claim = _claim("high", [_quote_evidence("A"), _quote_evidence("A"), _seed_evidence()])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "medium"


def test_verified_with_one_group_and_seed_downgrades_to_medium() -> None:
    claim = _claim("verified", [_quote_evidence("A"), _seed_evidence()])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "medium"


# ---- Downgrade auf low: kein agent_grounded-Mix (Issue #906 Defekt 2) -----


def test_high_with_one_group_only_agent_quote_downgrades_to_low() -> None:
    """Nur agent_quote, kein seed_corpus → nicht agent_grounded → low
    (vorher fälschlich medium, Issue #906 Defekt 2)."""
    claim = _claim("high", [_quote_evidence("A"), _quote_evidence("A")])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "low"


def test_high_seed_only_downgrades_to_low() -> None:
    """high mit ausschließlich seed_corpus → Seed-only → low. Das ist der
    Kernbefund aus Issue #906 (≈325 medium-Claims mit nur Seed-Evidence)."""
    claim = _claim("high", [_seed_evidence(), _seed_evidence()])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "low"


def test_high_with_no_supporting_evidence_downgrades_to_low() -> None:
    """high ohne jede Evidence → low (vorher medium)."""
    claim = _claim("high", [])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "low"


def test_high_with_only_opposing_quotes_downgrades_to_low() -> None:
    """Opposing quotes (supports=False), kein seed_corpus → low."""
    claim = _claim("high", [
        _quote_evidence("A", supports=False),
        _quote_evidence("B", supports=False),
    ])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "low"


def test_verified_with_one_group_only_agent_quote_downgrades_to_low() -> None:
    claim = _claim("verified", [_quote_evidence("A")])
    result = auto_downgrade_unsupported_high_claims([claim])
    assert result[0]["confidence_label"] == "low"


def test_medium_low_labels_untouched() -> None:
    medium = _claim("medium", [])
    low = _claim("low", [])
    result = auto_downgrade_unsupported_high_claims([medium, low])
    assert result[0]["confidence_label"] == "medium"
    assert result[1]["confidence_label"] == "low"


def test_logger_warning_on_downgrade_to_low() -> None:
    """Log-Nachricht benennt das tatsächliche Ziel-Label (hier low).
    Logger wird mit lazy %-Formatting gerufen; die formatierte Message
    wird aus Format-String + Args rekonstruiert."""
    claim = _claim("high", [_quote_evidence("A")])  # nur agent_quote → low
    fake_logger = MagicMock()
    auto_downgrade_unsupported_high_claims([claim], logger=fake_logger)
    fake_logger.warning.assert_called_once()
    args = fake_logger.warning.call_args[0]
    msg = args[0] % args[1:]
    assert "→ 'low'" in msg


def test_logger_warning_on_downgrade_to_medium() -> None:
    claim = _claim("high", [_quote_evidence("A"), _seed_evidence()])  # agent_grounded → medium
    fake_logger = MagicMock()
    auto_downgrade_unsupported_high_claims([claim], logger=fake_logger)
    fake_logger.warning.assert_called_once()
    args = fake_logger.warning.call_args[0]
    msg = args[0] % args[1:]
    assert "→ 'medium'" in msg


def test_normalize_claims_for_contract_strips_legacy_fields_and_downgrades() -> None:
    claim = {
        "claim_id": "x",
        "claim": "legacy text",  # legacy alias to strip
        "confidence": "ignored",  # legacy alias to strip
        "evidence_items": "legacy",  # legacy alias to strip
        "confidence_label": "high",
        "evidence": [_quote_evidence("Only-One")],  # nur agent_quote → low
    }
    out = normalize_claims_for_contract([claim])
    assert "claim" not in out[0]
    assert "confidence" not in out[0]
    assert "evidence_items" not in out[0]
    assert out[0]["confidence_label"] == "low"


def test_normalize_claims_for_contract_seed_only_downgrades_to_low() -> None:
    claim = {
        "claim_id": "x",
        "confidence_label": "high",
        "evidence": [_seed_evidence()],
    }
    out = normalize_claims_for_contract([claim])
    assert out[0]["confidence_label"] == "low"


def test_normalize_sections_for_contract_propagates_downgrade() -> None:
    section = {
        "section_title": "Test",
        "section_summary": "Summary",
        "claims": [_claim("high", [_quote_evidence("OnlyOne"), _seed_evidence()])],
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