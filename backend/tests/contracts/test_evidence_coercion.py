"""Sub-Slice 05.7 — Pre-Validator-Coercion für hypothesis_text/claim_text.

Live-Smoke: LLMs stopften komplette Markdown-Tabellen in
``ReportSectionHypothesisModel.hypothesis_text`` und
``ReportSectionDataGapModel.claim_text``, was Pydantic mit
``string_too_long`` ablehnte und den ganzen Report-Save abriss.

Fix: ``field_validator(mode='before')`` truncated den Wert auf <= 1000
chars, bevorzugt am ersten Newline/Pipe (Tabellen-Marker).

Layer-0-Anti-Regression: ``max_length=1000`` BLEIBT erhalten — die
Coercion ist ein Pre-Validator, kein Schwächen des Field-Constraints.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ReportSectionDataGapModel,
    ReportSectionHypothesisModel,
    _coerce_text_to_max_1000,
)


class TestCoerceTextToMax1000:
    """Helper-Funktion direkt — Truncation-Regeln."""

    def test_short_text_unchanged(self):
        assert _coerce_text_to_max_1000("Eine kurze Aussage.") == "Eine kurze Aussage."

    def test_exact_1000_unchanged(self):
        text = "x" * 1000
        assert _coerce_text_to_max_1000(text) == text

    def test_truncates_at_newline_when_present(self):
        """Wenn LLM eine Tabelle reinstopft (`\\n|`) → bei erstem Newline abschneiden."""
        body = "Aussage über das Segment.\n| Segment | Anzahl |\n| --- | --- |\n" + "x" * 1500
        result = _coerce_text_to_max_1000(body)
        assert len(result) <= 1000
        assert "|" not in result, "Tabellen-Pipe darf nicht im truncated text bleiben"
        assert result.startswith("Aussage über das Segment.")

    def test_truncates_at_pipe_when_no_early_newline(self):
        body = "Single-line statement with table | Segment | Anzahl " + "x" * 1500
        result = _coerce_text_to_max_1000(body)
        assert len(result) <= 1000
        assert "|" not in result

    def test_hard_truncate_with_ellipsis_when_no_marker(self):
        """Lange Prosa ohne Tabellen-Marker → hart auf <1000 + Ellipsis."""
        body = "x" * 5000
        result = _coerce_text_to_max_1000(body)
        assert len(result) <= 1000
        assert result.endswith("…")

    def test_non_string_passes_through(self):
        """None / int / dict werden nicht angefasst — Pydantic kümmert sich um Type-Fehler."""
        assert _coerce_text_to_max_1000(None) is None
        assert _coerce_text_to_max_1000(42) == 42

    def test_warning_logged_on_truncation(self, monkeypatch):
        """Truncation muss eine Warning erzeugen (Visibility)."""
        captured: list[str] = []

        def fake_warning(msg, *args, **kwargs):
            try:
                captured.append(msg % args if args else msg)
            except TypeError:
                captured.append(str(msg))

        # Logger über die Standard-Library mocken — robust gegen unseren
        # eigenen get_logger-Setup.
        target_logger = logging.getLogger("agora.report_contract")
        monkeypatch.setattr(target_logger, "warning", fake_warning)

        _coerce_text_to_max_1000("x" * 2000)
        assert any("evidence-coercion" in m for m in captured), (
            f"Truncation muss als WARNING geloggt werden — captured: {captured}"
        )


class TestHypothesisModelCoercion:
    """Pre-Validator auf hypothesis_text + rationale."""

    def test_long_hypothesis_text_coerced_not_rejected(self):
        """LLM-Bloat in hypothesis_text → truncated, kein ValidationError."""
        instance = ReportSectionHypothesisModel.model_validate(
            {
                "hypothesis_id": "hypothesis_01",
                "hypothesis_text": (
                    "Die Persona ist vorsichtig.\n"
                    "| Segment | Anzahl | Haltung |\n"
                    "| --- | --- | --- |\n" + "x" * 2000
                ),
                "rationale": "Die Datenbasis legt das nahe.",
            }
        )
        assert len(instance.hypothesis_text) <= 1000
        assert "|" not in instance.hypothesis_text
        assert instance.hypothesis_text.startswith("Die Persona ist vorsichtig.")

    def test_long_rationale_also_coerced(self):
        instance = ReportSectionHypothesisModel.model_validate(
            {
                "hypothesis_id": "hypothesis_02",
                "hypothesis_text": "Aussage hier.",
                "rationale": "Begründung.\n" + "x" * 5000,
            }
        )
        assert len(instance.rationale) <= 1000

    def test_layer0_anker_max_length_1000_stays(self):
        """Anti-Regression: max_length=1000 BLEIBT im Field-Constraint.

        Coercion vor-Validator darf den Anker nicht ausschalten — der
        Constraint muss noch greifen, falls jemand den Validator umgeht.
        """
        # JSON-Schema-Inspektion: max_length muss noch 1000 sein
        schema = ReportSectionHypothesisModel.model_json_schema()
        ht_constraint = schema["properties"]["hypothesis_text"].get("maxLength")
        assert ht_constraint == 1000, (
            f"Layer-0-Anker verletzt: hypothesis_text.maxLength={ht_constraint}"
        )
        rat_constraint = schema["properties"]["rationale"].get("maxLength")
        assert rat_constraint == 1000

    def test_min_length_still_enforced(self):
        """Pre-Validator truncated nur — min_length=8 muss noch greifen."""
        with pytest.raises(ValidationError, match="at least 8"):
            ReportSectionHypothesisModel.model_validate(
                {
                    "hypothesis_id": "hypothesis_03",
                    "hypothesis_text": "kurz",  # 4 chars < 8
                    "rationale": "Begründungstext.",
                }
            )


class TestDataGapModelCoercion:
    """Pre-Validator auf claim_text."""

    def test_long_claim_text_coerced(self):
        instance = ReportSectionDataGapModel.model_validate(
            {
                "gap_id": "gap_01",
                "claim_text": "Es fehlt eine Erhebung zur Persona Y.\n| col1 | col2 |\n" + "x" * 2000,
                "gap_reason": "Keine Quelle vorhanden.",
            }
        )
        assert len(instance.claim_text) <= 1000
        assert "|" not in instance.claim_text

    def test_layer0_anker_claim_text_max_length_1000_stays(self):
        schema = ReportSectionDataGapModel.model_json_schema()
        ct_constraint = schema["properties"]["claim_text"].get("maxLength")
        assert ct_constraint == 1000

    def test_short_claim_unchanged_after_coercion(self):
        instance = ReportSectionDataGapModel.model_validate(
            {
                "gap_id": "gap_02",
                "claim_text": "Eine knappe Lücken-Aussage.",
                "gap_reason": "fehlt",
            }
        )
        assert instance.claim_text == "Eine knappe Lücken-Aussage."
