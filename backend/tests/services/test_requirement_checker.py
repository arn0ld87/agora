"""
Tests für Issue #1302 — Requirement-Checker vor Report-Abschluss.

Deckt drei Bausteine ab:

1. Die sieben Einzel-Prüfregeln in ``requirement_checker.py`` — je Regel ein
   Present/Missing-Paar (Testplan: "Unit test per requirement: present →
   pass, missing → fail").
2. ``RequirementChecker.check`` (Aggregation) und
   ``apply_requirement_check_downgrade`` (app.services.report_agent.
   output_contract) — reiner Downgrade-Helper, analog zu
   ``apply_quote_validation_downgrade``/``apply_report_v3_validation_downgrade``
   (Issue #1299): stuft COMPLETED auf INCOMPLETE ab, wertet aber nie auf.
3. Die Verdrahtung in ``generate_report()`` (workflow.py) — patcht das
   modul-lokale ``REQUIREMENT_CHECKLIST`` (Default: leer, siehe
   ``requirement_checker.py``-Moduldocstring für die Begründung) mit einer
   Test-Checkliste, um den End-to-End-Pfad zu prüfen:
   - Report ohne Stop-Bedingungen → INCOMPLETE + Fehlerliste in
     ``report.error`` (Testplan-Regressionstest, wörtlich aus #1302).
   - Report, der alle konfigurierten Punkte abdeckt → COMPLETED bleibt
     möglich (kein False-Positive-Downgrade).

Mocking-Strategie identisch zu ``test_report_status_contract_gating.py``:
Agent und ``ReportManager`` werden gemockt, ``get_report_v3`` wird explizit
auf ``None`` gesetzt — ein unkonfigurierter ``MagicMock`` dort ist truthy und
würde den ReportV3-Validierungsblock fälschlich durchlaufen und die
Statusprüfung dieser Tests verfälschen (bekannte Falle, siehe
``_base_report_manager_mock`` dort).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.report import ReportStatus
from app.services.report_agent import ReportAgent
from app.services.report_agent.output_contract import apply_requirement_check_downgrade
from app.services.report_agent.requirement_checker import (
    ISSUE_1302_DEFAULT_CHECKLIST,
    RequirementCheck,
    RequirementChecker,
    check_all_four_variants_covered,
    check_coalitions_identified,
    check_early_warning_indicators_named,
    check_expand_conditions_defined,
    check_position_changes_documented,
    check_stakeholder_contradictions_addressed,
    check_stop_conditions_defined,
)

# ---------------------------------------------------------------------------
# 1. Unit-Tests je Prüfregel: present → pass, missing → fail
# ---------------------------------------------------------------------------


class TestIndividualRequirementChecks:
    def test_stakeholder_contradictions_present(self):
        text = "Zwischen den Stakeholdern besteht ein klarer Widerspruch, der im Text adressiert wird."
        assert check_stakeholder_contradictions_addressed(text) is True

    def test_stakeholder_contradictions_missing(self):
        text = "Alle Stakeholder sind sich vollkommen einig."
        assert check_stakeholder_contradictions_addressed(text) is False

    def test_early_warning_indicators_present(self):
        text = "Als Frühwarnindikator gilt ein Rückgang der Zustimmung um 10 Prozentpunkte."
        assert check_early_warning_indicators_named(text) is True

    def test_early_warning_indicators_missing(self):
        text = "Der Bericht beschreibt die aktuelle Stimmungslage."
        assert check_early_warning_indicators_named(text) is False

    def test_stop_conditions_present(self):
        text = "Eine Stop-Bedingung ist erreicht, sobald die Ablehnung 60% übersteigt."
        assert check_stop_conditions_defined(text) is True

    def test_stop_conditions_missing(self):
        text = "Der Report beschreibt nur die aktuelle Lage, keine Abbruchkriterien."
        assert check_stop_conditions_defined(text) is False

    def test_expand_conditions_present(self):
        text = "Die Expand-Bedingung greift, sobald drei Gruppen zustimmen."
        assert check_expand_conditions_defined(text) is True

    def test_expand_conditions_missing(self):
        text = "Der Report nennt keine Kriterien für eine Ausweitung."
        assert check_expand_conditions_defined(text) is False

    def test_position_changes_present(self):
        text = "Ein deutlicher Positionswechsel zeigt sich bei der Gruppe der Early Adopters."
        assert check_position_changes_documented(text) is True

    def test_position_changes_missing(self):
        text = "Die Positionen der Gruppen blieben im Beobachtungszeitraum stabil."
        assert check_position_changes_documented(text) is False

    def test_coalitions_present(self):
        text = "Es bildet sich eine Koalition aus Verbänden und kritischen Kundengruppen."
        assert check_coalitions_identified(text) is True

    def test_coalitions_missing(self):
        text = "Die Gruppen agieren unabhängig voneinander."
        assert check_coalitions_identified(text) is False

    def test_all_four_variants_present(self):
        text = "Variante 1 überzeugt, Variante 2 ist neutral, Variante 3 wird abgelehnt, Variante 4 ist unklar."
        assert check_all_four_variants_covered(text) is True

    def test_all_four_variants_missing(self):
        text = "Variante 1 überzeugt, Variante 2 ist neutral, Variante 3 wird abgelehnt."
        assert check_all_four_variants_covered(text) is False


# ---------------------------------------------------------------------------
# 2a. RequirementChecker.check (Aggregation über eine Checkliste)
# ---------------------------------------------------------------------------


class TestRequirementCheckerCheck:
    def test_all_checks_pass_returns_empty_list(self):
        content = (
            "Zwischen den Stakeholdern gibt es einen Widerspruch, der adressiert wird. "
            "Frühwarnindikator: sinkende Zustimmung. Stop-Bedingung ab 60% Ablehnung. "
            "Expand-Bedingung ab drei zustimmenden Gruppen. "
            "Ein Positionswechsel zeigt sich bei den Early Adopters. "
            "Es bildet sich eine Koalition kritischer Gruppen. "
            "Variante 1, Variante 2, Variante 3 und Variante 4 wurden bewertet."
        )
        failed = RequirementChecker.check(content, ISSUE_1302_DEFAULT_CHECKLIST)
        assert failed == []

    def test_missing_aspect_is_reported(self):
        content = "Ein Report ohne jede der geprüften Formulierungen."
        failed = RequirementChecker.check(content, ISSUE_1302_DEFAULT_CHECKLIST)
        failed_keys = {check.key for check in failed}
        assert failed_keys == {check.key for check in ISSUE_1302_DEFAULT_CHECKLIST}

    def test_only_stop_conditions_missing(self):
        content = (
            "Zwischen den Stakeholdern gibt es einen Widerspruch, der adressiert wird. "
            "Frühwarnindikator: sinkende Zustimmung. "
            "Expand-Bedingung ab drei zustimmenden Gruppen. "
            "Ein Positionswechsel zeigt sich bei den Early Adopters. "
            "Es bildet sich eine Koalition kritischer Gruppen. "
            "Variante 1, Variante 2, Variante 3 und Variante 4 wurden bewertet."
        )
        failed = RequirementChecker.check(content, ISSUE_1302_DEFAULT_CHECKLIST)
        assert [check.key for check in failed] == ["stop_conditions_defined"]

    def test_empty_checklist_never_fails(self):
        assert RequirementChecker.check("beliebiger Text", ()) == []

    def test_custom_checklist_is_honored(self):
        """Konfigurierbarkeit: eine frei definierte Checkliste wird geprüft,
        nicht nur die im Issue vorgegebenen 7 Punkte."""
        custom = (
            RequirementCheck(
                "mentions_budget",
                "Budget erwähnt",
                lambda text: "budget" in text.lower(),
            ),
        )
        assert RequirementChecker.check("Der Report nennt kein Zahlenwerk.", custom) == list(custom)
        assert RequirementChecker.check("Das Budget beträgt 10.000 Euro.", custom) == []


# ---------------------------------------------------------------------------
# 2b. apply_requirement_check_downgrade — downgrade-only, nie Aufwertung
# ---------------------------------------------------------------------------


class TestApplyRequirementCheckDowngrade:
    def test_downgrades_completed_when_checks_failed(self):
        failed = [ISSUE_1302_DEFAULT_CHECKLIST[0]]
        assert (
            apply_requirement_check_downgrade(ReportStatus.COMPLETED, failed)
            == ReportStatus.INCOMPLETE
        )

    def test_leaves_completed_untouched_when_no_failures(self):
        assert (
            apply_requirement_check_downgrade(ReportStatus.COMPLETED, [])
            == ReportStatus.COMPLETED
        )

    def test_does_not_upgrade_failed(self):
        failed = [ISSUE_1302_DEFAULT_CHECKLIST[0]]
        assert (
            apply_requirement_check_downgrade(ReportStatus.FAILED, failed)
            == ReportStatus.FAILED
        )

    def test_leaves_incomplete_as_incomplete(self):
        failed = [ISSUE_1302_DEFAULT_CHECKLIST[0]]
        assert (
            apply_requirement_check_downgrade(ReportStatus.INCOMPLETE, failed)
            == ReportStatus.INCOMPLETE
        )


# ---------------------------------------------------------------------------
# Helpers für die Workflow-Integrationstests (analog zu
# test_report_status_contract_gating.py)
# ---------------------------------------------------------------------------

_EVIDENCE_MAP_WITH_ANCHOR = {
    "schema_version": 2,
    "report_id": "report_req_checker_test",
    "simulation_id": "sim_1302",
    "global_evidence": [
        {
            "type": "graph_fact",
            "source": "test",
            "snippet": "Snippet",
            "source_id_anchor": "ev_valid_001",
        }
    ],
    "sections": [],
}


def _make_agent() -> object:
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_1302"
    agent.simulation_id = "sim_1302"
    agent.simulation_requirement = "Requirement-Checker-Test"
    agent.llm = MagicMock()
    agent.llm.chat_json.return_value = {"section_title": "Test", "key_takeaways": [], "data_gaps": []}
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = dict(_EVIDENCE_MAP_WITH_ANCHOR)
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None
    agent.persona_ids = [f"persona_{i:02d}" for i in range(1, 51)]

    agent.ReportLogger = MagicMock()
    agent.ReportConsoleLogger = MagicMock()
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent._save_evidence_section = MagicMock()
    agent._get_tools_description = MagicMock(return_value="(keine Tools)")
    return agent


def _make_outline_with_section(section_title: str = "Persona-Reaktionen") -> object:
    section = MagicMock()
    section.title = section_title
    section.content = ""
    section.metadata = {}

    outline = MagicMock()
    outline.title = "Test-Report"
    outline.summary = "Zusammenfassung."
    outline.sections = [section]
    outline.to_dict = MagicMock(return_value={})
    return outline, section


def _valid_section_text(persona_id: str = "persona_01") -> str:
    return (
        f"Die Simulation zeigt klare Reaktionen:\n\n"
        f'<simulated_quote persona_id="{persona_id}" seed_anchor="ev_valid_001">'
        f"Das Angebot überzeugt durch seine Klarheit."
        f"</simulated_quote>\n\n"
        f"Diese Einschätzung basiert auf den Simulationsdaten."
    )


def _base_report_manager_mock(mock_rm: MagicMock, *, section_text: str, assembled_markdown: str) -> None:
    """Setzt die für generate_report() nötigen ReportManager-Stubs.

    ``get_report_v3.return_value = None`` ist Pflicht: ein unkonfigurierter
    ``MagicMock`` dort ist truthy, würde den ReportV3-Validierungsblock
    fälschlich durchlaufen lassen und die Status-Assertions dieser Tests
    verfälschen (siehe Moduldocstring).
    """
    mock_rm.get_report.return_value = None
    mock_rm.get_generated_sections.return_value = []
    mock_rm.assemble_full_report.return_value = assembled_markdown
    mock_rm._ensure_report_folder.return_value = None
    mock_rm.save_report.return_value = None
    mock_rm.save_outline.return_value = None
    mock_rm.save_section.return_value = None
    mock_rm.update_progress.return_value = None
    mock_rm._clean_section_content.return_value = section_text
    mock_rm.get_report_v3.return_value = None


# ---------------------------------------------------------------------------
# 3a. Regressionstest (wörtlich aus #1302): Report ohne Stop-Bedingungen
#     → INCOMPLETE + Fehlerliste in report.error.
# ---------------------------------------------------------------------------


class TestReportWithoutStopConditionsIsIncomplete:
    def test_missing_stop_conditions_downgrades_and_persists_error(self):
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        valid_text = _valid_section_text()
        # Enthält alle Aspekte der Default-Checkliste AUSSER Stop-Bedingungen.
        assembled_markdown = (
            "# Test-Report\n\n"
            "Zwischen den Stakeholdern gibt es einen Widerspruch, der adressiert wird. "
            "Frühwarnindikator: sinkende Zustimmung. "
            "Expand-Bedingung ab drei zustimmenden Gruppen. "
            "Ein Positionswechsel zeigt sich bei den Early Adopters. "
            "Es bildet sich eine Koalition kritischer Gruppen. "
            "Variante 1, Variante 2, Variante 3 und Variante 4 wurden bewertet."
        )

        with (
            patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
            patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
            patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
            patch("app.services.report_agent.workflow.generate_section_metadata") as mock_meta,
            patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
            patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
            patch(
                "app.services.report_agent.workflow.REQUIREMENT_CHECKLIST",
                ISSUE_1302_DEFAULT_CHECKLIST,
            ),
        ):
            mock_plan.return_value = outline
            mock_gsr.return_value = valid_text
            mock_meta.return_value = {}
            mock_migrate.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            mock_rm.get_evidence_map.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            _base_report_manager_mock(
                mock_rm, section_text=valid_text, assembled_markdown=assembled_markdown
            )

            from app.services.report_agent.workflow import generate_report
            report = generate_report(agent, report_id="report_req_checker_stop_01")

        assert report.status != ReportStatus.COMPLETED, (
            f"report.status={report.status!r} — ein Report ohne dokumentierte "
            f"Stop-Bedingungen darf bei aktivierter Checkliste nie COMPLETED "
            f"sein (#1302)."
        )
        assert report.error is not None
        assert "Stop-Bedingungen" in report.error


# ---------------------------------------------------------------------------
# 3b. Integration: Report deckt alle konfigurierten Punkte ab → COMPLETED
#     bleibt möglich (kein False-Positive-Downgrade).
# ---------------------------------------------------------------------------


class TestCompleteReportStaysCompleted:
    def test_all_checklist_aspects_covered_allows_completed(self):
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        valid_text = _valid_section_text()
        assembled_markdown = (
            "# Test-Report\n\n"
            "Zwischen den Stakeholdern gibt es einen Widerspruch, der adressiert wird. "
            "Frühwarnindikator: sinkende Zustimmung. "
            "Stop-Bedingung ab 60% Ablehnung. "
            "Expand-Bedingung ab drei zustimmenden Gruppen. "
            "Ein Positionswechsel zeigt sich bei den Early Adopters. "
            "Es bildet sich eine Koalition kritischer Gruppen. "
            "Variante 1, Variante 2, Variante 3 und Variante 4 wurden bewertet."
        )

        with (
            patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
            patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
            patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
            patch("app.services.report_agent.workflow.generate_section_metadata") as mock_meta,
            patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
            patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
            patch(
                "app.services.report_agent.workflow.REQUIREMENT_CHECKLIST",
                ISSUE_1302_DEFAULT_CHECKLIST,
            ),
        ):
            mock_plan.return_value = outline
            mock_gsr.return_value = valid_text
            mock_meta.return_value = {}
            mock_migrate.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            mock_rm.get_evidence_map.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            _base_report_manager_mock(
                mock_rm, section_text=valid_text, assembled_markdown=assembled_markdown
            )

            from app.services.report_agent.workflow import generate_report
            report = generate_report(agent, report_id="report_req_checker_ok_01")

        assert report.status == ReportStatus.COMPLETED, (
            f"report.status={report.status!r} — deckt der Report alle "
            f"konfigurierten Checklistenpunkte ab, darf der neue Gate-Code "
            f"nicht ungefragt abstufen."
        )

    def test_default_wiring_checklist_is_empty_and_never_downgrades(self):
        """Ohne explizite Aktivierung (Produktionsdefault) bleibt jeder
        bestehende Report unangetastet — die Checkliste ist konfigurierbar,
        aber nicht standardmäßig hart für jeden Report-Typ erzwungen."""
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        valid_text = _valid_section_text()
        # Enthält keinen einzigen der 7 Checklistenbegriffe.
        assembled_markdown = "# Test-Report\n\nEin ganz gewöhnlicher Opinion-Report ohne Szenario-Vokabular."

        with (
            patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
            patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
            patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
            patch("app.services.report_agent.workflow.generate_section_metadata") as mock_meta,
            patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
            patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        ):
            mock_plan.return_value = outline
            mock_gsr.return_value = valid_text
            mock_meta.return_value = {}
            mock_migrate.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            mock_rm.get_evidence_map.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            _base_report_manager_mock(
                mock_rm, section_text=valid_text, assembled_markdown=assembled_markdown
            )

            from app.services.report_agent.workflow import generate_report
            report = generate_report(agent, report_id="report_req_checker_default_01")

        assert report.status == ReportStatus.COMPLETED
        assert report.error is None
