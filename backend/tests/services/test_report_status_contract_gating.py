"""
Tests für Issue #1299 — Reportstatus an Contract-Validität koppeln.

Deckt zwei Bausteine ab:

1. ``apply_report_v3_validation_downgrade`` / ``apply_quote_validation_downgrade``
   (app.services.report_agent.output_contract) — reine Downgrade-Helper,
   analog zu ``apply_degradation_downgrade`` (Issue #1006): stufen COMPLETED
   auf INCOMPLETE ab, werten aber nie auf.
2. Die Verdrahtung in ``generate_report()`` (workflow.py):
   - ``quote_validation_failed=True`` auf mind. einer Section →
     ``report.status != ReportStatus.COMPLETED``.
   - Ein ReportV3, das ``ReportV3.model_validate`` nicht besteht (fehlendes
     Pflichtfeld) → ``report.status != ReportStatus.COMPLETED`` UND
     ``ReportManager.save_report`` wird ein zweites Mal mit dem abgestuften
     Status aufgerufen (der erste Save lief bereits mit dem alten Status).
   - Der unauffällige Fall (gültige Quotes, gültiges ReportV3) bleibt
     COMPLETED — kein False-Positive-Downgrade.

Strategie für die Workflow-Tests: identisch zu
``test_report_agent_workflow_quote_validation.py`` (M11.8e) — Agent und
``ReportManager`` werden gemockt, so dass ``generate_report()`` den
Section-Loop und den ReportV3-Validierungsblock sauber durchläuft.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.report import ReportStatus
from app.services.report_agent import ReportAgent
from app.services.report_agent.output_contract import (
    apply_quote_validation_downgrade,
    apply_report_v3_validation_downgrade,
)


# ---------------------------------------------------------------------------
# 1. Unit-Tests für die neuen Downgrade-Helper (output_contract.py)
# ---------------------------------------------------------------------------


class TestApplyQuoteValidationDowngrade:
    def test_downgrades_completed_when_section_failed(self):
        assert (
            apply_quote_validation_downgrade(ReportStatus.COMPLETED, [2])
            == ReportStatus.INCOMPLETE
        )

    def test_leaves_completed_untouched_when_no_failures(self):
        assert (
            apply_quote_validation_downgrade(ReportStatus.COMPLETED, [])
            == ReportStatus.COMPLETED
        )

    def test_does_not_upgrade_failed(self):
        assert (
            apply_quote_validation_downgrade(ReportStatus.FAILED, [1])
            == ReportStatus.FAILED
        )

    def test_leaves_incomplete_as_incomplete(self):
        assert (
            apply_quote_validation_downgrade(ReportStatus.INCOMPLETE, [1])
            == ReportStatus.INCOMPLETE
        )


class TestApplyReportV3ValidationDowngrade:
    def test_downgrades_completed_when_errors_present(self):
        errors = [{"type": "missing", "loc": ("report_id",)}]
        assert (
            apply_report_v3_validation_downgrade(ReportStatus.COMPLETED, errors)
            == ReportStatus.INCOMPLETE
        )

    def test_leaves_completed_untouched_when_no_errors(self):
        assert (
            apply_report_v3_validation_downgrade(ReportStatus.COMPLETED, [])
            == ReportStatus.COMPLETED
        )

    def test_does_not_upgrade_failed(self):
        errors = [{"type": "missing", "loc": ("report_id",)}]
        assert (
            apply_report_v3_validation_downgrade(ReportStatus.FAILED, errors)
            == ReportStatus.FAILED
        )


# ---------------------------------------------------------------------------
# Helpers (analog zu test_report_agent_workflow_quote_validation.py)
# ---------------------------------------------------------------------------

_EVIDENCE_MAP_WITH_ANCHOR = {
    "schema_version": 2,
    "report_id": "report_gating_test",
    "simulation_id": "sim_1299",
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
    """Minimaler ReportAgent-Stub ohne echten LLM-Call."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_1299"
    agent.simulation_id = "sim_1299"
    agent.simulation_requirement = "Contract-Status-Gating-Test"
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
    # MIN_PERSONA_TABLE_ROWS = 50 (Slice P1.2). Ein vollwertiger Persona-Pool
    # ist nötig, damit generate_report bis zum Section-Generation-Loop läuft.
    agent.persona_ids = [f"persona_{i:02d}" for i in range(1, 51)]

    agent.ReportLogger = MagicMock()
    agent.ReportConsoleLogger = MagicMock()
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent._save_evidence_section = MagicMock()
    agent._get_tools_description = MagicMock(return_value="(keine Tools)")
    return agent


def _make_outline_with_section(section_title: str = "Persona-Reaktionen") -> object:
    """Minimaler Outline-Stub mit einer Section."""
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
    """Section-Text mit einem gültigen <simulated_quote>-Tag."""
    return (
        f"Die Simulation zeigt klare Reaktionen:\n\n"
        f'<simulated_quote persona_id="{persona_id}" seed_anchor="ev_valid_001">'
        f"Das Angebot überzeugt durch seine Klarheit."
        f"</simulated_quote>\n\n"
        f"Diese Einschätzung basiert auf den Simulationsdaten."
    )


def _invalid_section_text() -> str:
    """Section-Text mit ungültigem Quote (fehlt persona_id)."""
    return (
        "Einige Personas zeigen Skepsis:\n\n"
        '<simulated_quote seed_anchor="ev_valid_001">'
        "Ich bin skeptisch."
        "</simulated_quote>"
    )


def _base_report_manager_mock(mock_rm: MagicMock, *, section_text: str) -> None:
    """Setzt die für generate_report() nötigen ReportManager-Stubs."""
    mock_rm.get_report.return_value = None
    mock_rm.get_generated_sections.return_value = []
    mock_rm.assemble_full_report.return_value = "# Test-Report\n\nInhalt."
    mock_rm._ensure_report_folder.return_value = None
    mock_rm.save_report.return_value = None
    mock_rm.save_outline.return_value = None
    mock_rm.save_section.return_value = None
    mock_rm.update_progress.return_value = None
    mock_rm._clean_section_content.return_value = section_text
    # Kein persistiertes ReportV3 per Default — isoliert den Quote-Test vom
    # ReportV3-Validierungsblock.
    mock_rm.get_report_v3.return_value = None


# ---------------------------------------------------------------------------
# 2. quote_validation_failed=True → report.status != COMPLETED
# ---------------------------------------------------------------------------


class TestQuoteValidationFailureDowngradesStatus:
    def test_quote_validation_failed_downgrades_report_status(self):
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        invalid_text = _invalid_section_text()

        with (
            patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
            patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
            patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
            patch("app.services.report_agent.workflow.generate_section_metadata") as mock_meta,
            patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
            patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        ):
            mock_plan.return_value = outline
            mock_gsr.return_value = invalid_text
            mock_meta.return_value = {}
            empty_evidence_map = {
                "schema_version": 2,
                "report_id": "report_gating_quote_01",
                "simulation_id": "sim_1299",
                "global_evidence": [],  # kein ev_valid_001 → unbound → ungültig
                "sections": [],
            }
            mock_migrate.return_value = empty_evidence_map
            mock_rm.get_evidence_map.return_value = empty_evidence_map
            _base_report_manager_mock(mock_rm, section_text=invalid_text)

            from app.services.report_agent.workflow import generate_report
            report = generate_report(agent, report_id="report_gating_quote_01")

        assert section.metadata.get("quote_validation_failed") is True, (
            "Vorbedingung: quote_validation_failed muss gesetzt sein, sonst "
            "testet dieser Test nichts."
        )
        assert report.status != ReportStatus.COMPLETED, (
            f"report.status={report.status!r} — ein Report mit "
            f"quote_validation_failed=True darf nie COMPLETED sein (#1299)."
        )


# ---------------------------------------------------------------------------
# 3. ReportV3-Validierungsfehler → report.status != COMPLETED, erneuter Save
# ---------------------------------------------------------------------------


class TestReportV3ValidationFailureDowngradesStatus:
    def test_invalid_report_v3_downgrades_status_and_resaves(self):
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        valid_text = _valid_section_text()

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
            _base_report_manager_mock(mock_rm, section_text=valid_text)
            # Persistiertes ReportV3 fehlt Pflichtfelder (report_id,
            # generated_at) → ReportV3.model_validate() wirft ValidationError.
            # Ein leeres Dict wäre falsy und würde den Validierungsblock in
            # generate_report() (``if report_v3_raw:``) gar nicht erreichen —
            # daher ein nicht-leeres, aber unvollständiges Dict.
            mock_rm.get_report_v3.return_value = {"schema_version": 4}

            # ``report`` ist dasselbe (mutierte) Objekt bei jedem
            # save_report-Aufruf — call_args_list würde am Ende überall den
            # finalen Status zeigen. Der Status ist aber ein unveränderliches
            # str-Enum-Mitglied, also snapshotten wir ihn per side_effect zum
            # jeweiligen Aufrufzeitpunkt.
            saved_statuses: list[ReportStatus] = []
            mock_rm.save_report.side_effect = lambda r: saved_statuses.append(r.status)

            from app.services.report_agent.workflow import generate_report
            report = generate_report(agent, report_id="report_gating_v3_01")

        assert report.status != ReportStatus.COMPLETED, (
            f"report.status={report.status!r} — ein Report mit invalidem "
            f"ReportV3-Contract darf nie COMPLETED sein (#1299)."
        )

        # generate_report() ruft save_report() mehrfach entlang des Workflows
        # auf (u. a. nach "Initializing", nach der Outline-Planung). Relevant
        # hier sind die letzten beiden Aufrufe: der reguläre Save direkt nach
        # dem Section-Loop (mit dem noch nicht abgestuften Status) und —
        # NEU durch #1299 — der erneute Save im ``except ValidationError``-
        # Zweig, nachdem der Status wegen des invaliden ReportV3-Contracts
        # abgestuft wurde.
        assert len(saved_statuses) >= 2, (
            f"Erwartet mind. 2 save_report-Aufrufe (regulär + Downgrade), "
            f"tatsächlich: {len(saved_statuses)}"
        )
        assert saved_statuses[-2] == ReportStatus.COMPLETED, (
            f"Vorbedingung: der Save direkt nach dem Section-Loop muss noch "
            f"den nicht abgestuften Status tragen. Tatsächlich: "
            f"{saved_statuses[-2]!r} (alle Saves: {saved_statuses!r})"
        )
        assert saved_statuses[-1] != ReportStatus.COMPLETED, (
            "Der letzte persistierte save_report-Aufruf (nach dem "
            "ReportV3-Downgrade) muss den abgestuften Status tragen. "
            f"Alle Saves: {saved_statuses!r}"
        )


# ---------------------------------------------------------------------------
# 4. Kein False-Positive: gültige Quotes + gültiges ReportV3 → COMPLETED
#    bleibt möglich.
# ---------------------------------------------------------------------------


class TestNoFalsePositiveDowngrade:
    def test_valid_quotes_and_no_persisted_report_v3_stays_completed(self):
        """Ohne persistiertes ReportV3 (get_report_v3 → None/leer) und ohne
        quote_validation_failed bleibt COMPLETED möglich — der neue Gate-Code
        degradiert nicht ungefragt."""
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        valid_text = _valid_section_text()

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
            _base_report_manager_mock(mock_rm, section_text=valid_text)

            from app.services.report_agent.workflow import generate_report
            report = generate_report(agent, report_id="report_gating_ok_01")

        assert not section.metadata.get("quote_validation_failed", False)
        assert report.status == ReportStatus.COMPLETED, (
            f"report.status={report.status!r} — ohne Contract-Verstoß darf "
            f"der neue Gate-Code nicht ungefragt abstufen."
        )
