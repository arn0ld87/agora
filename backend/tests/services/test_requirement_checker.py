"""Tests für Issue #1302 — Requirement-Checker vor Report-Abschluss.

Der Reporter setzte ``completed``, ohne maschinell zu prüfen, ob die
geforderten Analyseaspekte im Bericht stehen. ``requirement_checker.py``
prüft den fertigen Berichtstext gegen eine konfigurierbare Checkliste und
liefert fehlende Aspekte als Degradation-Einträge — dieselbe Form wie
``collect_run_degradations`` (Issue #1277), damit die bestehende
Status-Mechanik sie übernimmt.

Unit-Ebene: pro Requirement vorhanden → pass, fehlend → fail; Checkliste
pro Intent; Degradation-Form.
"""
from __future__ import annotations

import re

import pytest

from app.services.report_intent import ReportIntent
from app.services.report_agent.requirement_checker import (
    DEFAULT_REQUIREMENT_CHECKLIST,
    Requirement,
    checklist_for_intent,
    collect_requirement_degradations,
    find_missing_requirements,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: Ein Berichtstext, der alle Default-Requirements erfüllt.
COMPLETE_REPORT_TEXT = """
## Handlungsempfehlung

Die Simulation zeigt einen klaren Widerspruch zwischen Betriebsrat und
Geschäftsführung; die Konfliktlinie verläuft entlang der Datenerhebung.
Als Frühwarnindikator dient die Quote ungenutzter Auswertefunktionen.
Vor einer Ausweitung gilt die Stop-Bedingung: Sinkt die Akzeptanz unter
60 Prozent, wird der Rollout nicht ausgeweitet. Die Expand-Bedingung
sieht eine stufenweise Skalierung nach erfolgreichem Pilot vor. Ein
Positionswechsel ist bei der mittleren Führungsebene möglich, sobald
Schulungen nachweisbar sind. Betriebsrat und Jugendvertretung bilden
eine Koalition gegen die automatisierte Protokollierung.
"""

#: Prosa ohne irgendeinen geforderten Aspekt.
EMPTY_ASPECTS_TEXT = """
## Executive Summary

Die Simulation wurde über zwanzig Runden geführt. Die Personas haben
auf das Szenario reagiert. Es gibt Tabellen zu Segmenten und Multiplikatoren.
"""


# ---------------------------------------------------------------------------
# Unit: pro Requirement vorhanden → pass / fehlend → fail (Testplan #1302)
# ---------------------------------------------------------------------------


class TestDefaultChecklistPerRequirement:
    @pytest.mark.parametrize(
        "requirement_id",
        [req.id for req in DEFAULT_REQUIREMENT_CHECKLIST],
    )
    def test_present_aspect_passes(self, requirement_id):
        """Ein Text, der jeden Aspekt wörtlich benennt, lässt kein Requirement fehlen."""
        missing_ids = {
            req.id
            for req in find_missing_requirements(
                [COMPLETE_REPORT_TEXT], checklist=DEFAULT_REQUIREMENT_CHECKLIST
            )
        }
        assert requirement_id not in missing_ids

    @pytest.mark.parametrize(
        "requirement_id",
        [req.id for req in DEFAULT_REQUIREMENT_CHECKLIST],
    )
    def test_each_requirement_detectable_individually(self, requirement_id):
        """Pro Requirement existiert mindestens ein Erkennungsmuster — der
        vollständige Text erfüllt jedes einzelne davon."""
        req = next(r for r in DEFAULT_REQUIREMENT_CHECKLIST if r.id == requirement_id)
        assert any(
            re.search(pattern, COMPLETE_REPORT_TEXT, re.IGNORECASE)
            for pattern in req.patterns
        ), f"Kein Muster von {requirement_id} trifft auf den Referenztext zu."

    def test_text_without_any_aspect_fails_everything(self):
        missing = find_missing_requirements([EMPTY_ASPECTS_TEXT])
        assert {req.id for req in missing} == {
            req.id for req in DEFAULT_REQUIREMENT_CHECKLIST
        }

    def test_regression_report_without_stop_conditions_is_flagged(self):
        """Akzeptanzkriterium: Report ohne Stop-Bedingungen → fehlt."""
        text = COMPLETE_REPORT_TEXT.replace(
            "Sinkt die Akzeptanz unter\n60 Prozent, wird der Rollout nicht ausgeweitet. ",
            "",
        ).replace("Stop-Bedingung", "Vorgehen")
        text = re.sub(r"[Ss]top-?[Bb]edingung\w*", "Vorgehen", text)
        missing = find_missing_requirements([text])
        flagged = {req.id for req in missing}
        assert "stop_bedingungen" in flagged

    def test_complete_report_has_no_missing_requirements(self):
        assert (
            find_missing_requirements(
                [COMPLETE_REPORT_TEXT], checklist=DEFAULT_REQUIREMENT_CHECKLIST
            )
            == []
        )


# ---------------------------------------------------------------------------
# Unit: Checkliste pro Intent — „alle vier Varianten abgedeckt"
# ---------------------------------------------------------------------------


class TestChecklistForIntent:
    @pytest.mark.parametrize(
        "intent",
        [
            ReportIntent.FULL,
            ReportIntent.OPINION,
            ReportIntent.RISK,
            ReportIntent.COMPARISON,
        ],
    )
    def test_all_four_decision_oriented_presets_use_the_default_checklist(self, intent):
        """Die vier entscheidungsorientierten Presets (FULL/OPINION/RISK/
        COMPARISON) tragen laut #1322 dieselbe Handlungsempfehlung — der
        Checker deckt genau diese vier Varianten ab."""
        assert checklist_for_intent(intent) == DEFAULT_REQUIREMENT_CHECKLIST

    def test_explorative_preset_checks_nothing_by_design(self):
        """#1322: ein Explorationsbericht behauptet keine Entscheidungsreife;
        ihn auf Handlungsempfehlungs-Aspekte zu prüfen, machte jeden
        Explorativ-Report dauerhaft INCOMPLETE."""
        assert checklist_for_intent(ReportIntent.EXPLORATIVE) == ()

    def test_checklist_is_configurable_via_explicit_parameter(self):
        """Nicht hartkodiert für einen Report-Typ: ein Aufrufer kann eine
        eigene Checkliste reichen — sie gewinnt gegen den Default."""
        custom = (
            Requirement(
                id="nur_mein_aspekt",
                title="Nur mein Aspekt",
                description="Test.",
                patterns=(r"sonderfall",),
            ),
        )
        missing = find_missing_requirements([COMPLETE_REPORT_TEXT], checklist=custom)
        assert [req.id for req in missing] == ["nur_mein_aspekt"]

    def test_empty_texts_yield_no_crash_and_full_gap_list(self):
        assert len(find_missing_requirements(["", None or ""])) == len(
            DEFAULT_REQUIREMENT_CHECKLIST
        )


# ---------------------------------------------------------------------------
# Unit: Degradation-Form (analog collect_run_degradations)
# ---------------------------------------------------------------------------


class TestCollectRequirementDegradations:
    def test_one_blocking_entry_per_missing_requirement(self):
        missing = find_missing_requirements([EMPTY_ASPECTS_TEXT])
        entries = collect_requirement_degradations(missing)
        assert len(entries) == len(missing)
        for entry, req in zip(entries, missing):
            assert entry["component"] == "requirement_checker"
            assert entry["reason"] == f"{req.id}_missing"
            assert req.title in entry["detail"]
            assert entry["severity"] == "blocking"

    def test_no_gaps_no_entries(self):
        assert collect_requirement_degradations([]) == []

    def test_downgrade_mechanism_reacts_to_the_entries(self):
        """Die Einträge müssen durch das bestehende apply_run_degradation_
        downgrade wirken — keine zweite Statuslogik (#1302-Naht)."""
        from app.models.report import ReportStatus
        from app.services.report_agent.run_degradation import (
            apply_run_degradation_downgrade,
        )

        entries = collect_requirement_degradations(
            find_missing_requirements([EMPTY_ASPECTS_TEXT])
        )
        assert (
            apply_run_degradation_downgrade(ReportStatus.COMPLETED, entries)
            == ReportStatus.INCOMPLETE
        )
