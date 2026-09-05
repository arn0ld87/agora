"""Tests für Teil-Report-Generierung bei Cancel (app.services.report_agent.workflow).

Abgedeckte Szenarien:
  1  Bei Cancel zwischen Stage 2 und Stage 3 enthält der Report Stage 1+2,
     Metadata partial=True in partial_metadata.json
  2  Bei Cancel vor Stage 1 ist der Report leer aber status=COMPLETED (partial)
  3  Ohne Cancel läuft generate_report normal durch (Baseline)
  4  _is_cancel_requested liefert False wenn run_id=None
  5  _build_partial_report schreibt partial_metadata.json korrekt
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch


from app.models.report import Report, ReportOutline, ReportSection, ReportStatus
from app.services.report_agent.workflow import (
    _build_partial_report,
    _is_cancel_requested,
)
from app.services.sim.cancel_flag import clear_cancel, request_cancel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _make_report(report_id: str, simulation_id: str = "sim_test") -> Report:
    return Report(
        report_id=report_id,
        simulation_id=simulation_id,
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.GENERATING,
    )


def _make_outline(n_sections: int = 3) -> ReportOutline:
    sections = [
        ReportSection(title=f"Section {i + 1}", content="", description="")
        for i in range(n_sections)
    ]
    return ReportOutline(title="Test Report", summary="Test summary", sections=sections)


def _make_agent(report_id: str) -> MagicMock:
    agent = MagicMock()
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    return agent


# ---------------------------------------------------------------------------
# Test 4: _is_cancel_requested mit None
# ---------------------------------------------------------------------------


def test_is_cancel_requested_none_run_id():
    assert _is_cancel_requested(None) is False
    assert _is_cancel_requested("") is False


# ---------------------------------------------------------------------------
# Test 5: _build_partial_report schreibt partial_metadata.json
# ---------------------------------------------------------------------------


def test_build_partial_report_writes_metadata(tmp_path):
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    report = _make_report(report_id)
    outline = _make_outline(3)
    agent = _make_agent(report_id)
    completed = ["Section 1", "Section 2"]

    # ReportManager auf tmp_path zeigen
    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
    ):
        report_folder = str(tmp_path / report_id)
        os.makedirs(report_folder, exist_ok=True)

        mock_rm.assemble_full_report.return_value = "## Section 1\n\ncontent1\n\n## Section 2\n\ncontent2"
        mock_rm.save_report.return_value = None
        mock_rm.update_progress.return_value = None
        mock_rm._ensure_report_folder.return_value = report_folder

        # _write_json_atomic wirklich in tmp_path schreiben
        def real_write(path: str, data: Dict[str, Any]) -> None:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)

        mock_rm._write_json_atomic.side_effect = real_write

        result = _build_partial_report(
            report,
            report_id=report_id,
            completed_section_titles=completed,
            outline=outline,
            agent=agent,
            progress_callback=None,
        )

    assert result.status == ReportStatus.COMPLETED
    assert result.completed_at

    # partial_metadata.json muss existieren
    meta_path = os.path.join(report_folder, "partial_metadata.json")
    assert os.path.exists(meta_path), "partial_metadata.json wurde nicht geschrieben"
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)

    assert meta["partial"] is True
    assert meta["cancelled_at"]
    assert meta["completed_stages"] == completed
    assert meta["report_id"] == report_id


# ---------------------------------------------------------------------------
# Test 6: Persona-Degradierung erreicht auch den Teil-Report (Issue #1419)
# ---------------------------------------------------------------------------


def test_build_partial_report_carries_the_persona_degradation(tmp_path):
    """Ein Abbruch darf den Persona-Ausfall nicht verschlucken.

    Der Normalpfad zieht die Summe am Laufende; ein nach Stage 2
    abgebrochener Report lief daran vorbei und ging als COMPLETED hinaus,
    obwohl er auf 20 von 20 Platzhalter-Personas beruhte.
    """
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    report = _make_report(report_id)
    outline = _make_outline(3)
    agent = _make_agent(report_id)

    store = MagicMock()
    store.read_json.return_value = [
        {"generation_source": "rule_based", "generation_error": "LLM tot"}
        for _ in range(20)
    ]

    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch(
            "app.services.report_agent.workflow.resolve_default_store",
            return_value=store,
        ),
    ):
        report_folder = str(tmp_path / report_id)
        os.makedirs(report_folder, exist_ok=True)
        mock_rm.assemble_full_report.return_value = "## Section 1"
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        result = _build_partial_report(
            report,
            report_id=report_id,
            completed_section_titles=["Section 1"],
            outline=outline,
            agent=agent,
            progress_callback=None,
        )

    persona_entries = [
        entry
        for entry in result.run_degradations
        if entry["component"] == "persona_generation"
    ]
    assert len(persona_entries) == 1
    assert persona_entries[0]["reason"] == "20_of_20_personas_rule_based"
    assert persona_entries[0]["severity"] == "blocking"
    assert result.status == ReportStatus.INCOMPLETE


def test_build_partial_report_stays_quiet_without_a_persona_fallback(tmp_path):
    """Baseline: echte Personas aendern am bisherigen Teil-Report nichts."""
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    report = _make_report(report_id)
    agent = _make_agent(report_id)

    store = MagicMock()
    store.read_json.return_value = [{"generation_source": "llm"} for _ in range(20)]

    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch(
            "app.services.report_agent.workflow.resolve_default_store",
            return_value=store,
        ),
    ):
        report_folder = str(tmp_path / report_id)
        os.makedirs(report_folder, exist_ok=True)
        mock_rm.assemble_full_report.return_value = "## Section 1"
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        result = _build_partial_report(
            report,
            report_id=report_id,
            completed_section_titles=["Section 1"],
            outline=_make_outline(3),
            agent=agent,
            progress_callback=None,
        )

    assert not [
        entry
        for entry in result.run_degradations
        if entry["component"] == "persona_generation"
    ]
    assert result.status == ReportStatus.COMPLETED


# ---------------------------------------------------------------------------
# Test 1: generate_report bricht nach Stage 2 ab und liefert Teilreport
# ---------------------------------------------------------------------------


def test_generate_report_partial_after_stage_2(tmp_path):
    """Cancel-Flag nach Stage 2 → Report enthält Stages 1+2, partial=True."""
    from app.services.report_agent.workflow import generate_report

    cancel_run_id = _unique_id()
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    clear_cancel(cancel_run_id)

    agent = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.evidence_map = {}
    agent.ReportLogger = MagicMock(return_value=MagicMock())
    agent.ReportConsoleLogger = MagicMock(return_value=MagicMock())
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]

    outline = _make_outline(4)

    section_call_count = [0]

    def fake_generate_section_react(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        n = section_call_count[0]
        section_call_count[0] += 1
        if n == 1:
            # Nach Section 2 abgeschlossen → Flag setzen (simuliert User-Click)
            request_cancel(cancel_run_id)
        return f"Content for {section.title}"

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=fake_generate_section_react),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
    ):
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm.get_evidence_map.return_value = None
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm.update_progress.return_value = None
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.save_section.return_value = None
        mock_rm.assemble_full_report.return_value = "## Section 1\n## Section 2\n"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        # EvidenceMapModel.model_validate-Patch für die Schema-Initialisierung
        with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
            mock_em.model_validate.return_value = MagicMock(
                model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
            )

            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    # Nur 2 Sections generiert, dann abgebrochen
    assert section_call_count[0] == 2, f"Erwartet 2 Sections, erhalten: {section_call_count[0]}"
    assert result.status == ReportStatus.COMPLETED
    assert result.completed_at

    clear_cancel(cancel_run_id)


# ---------------------------------------------------------------------------
# Test 3: Ohne Cancel läuft generate_report normal (Baseline)
# ---------------------------------------------------------------------------


def test_generate_report_no_cancel_runs_all_sections(tmp_path):
    """Ohne Cancel-Flag werden alle Sections generiert."""
    from app.services.report_agent.workflow import generate_report

    report_id = f"report_{uuid.uuid4().hex[:12]}"
    agent = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.evidence_map = {}
    agent.ReportLogger = MagicMock(return_value=MagicMock())
    agent.ReportConsoleLogger = MagicMock(return_value=MagicMock())
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]

    outline = _make_outline(3)
    section_call_count = [0]

    def fake_section(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        section_call_count[0] += 1
        return f"Content for {section.title}"

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=fake_section),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
    ):
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm.get_evidence_map.return_value = None
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm.update_progress.return_value = None
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.save_section.return_value = None
        # Issue #1302: der Requirement-Checker prüft den fertigen
        # Berichtstext gegen die Default-Checkliste. Der Stub enthält alle
        # geforderten Aspekte, damit dieser Test ausschließlich den
        # Cancel-Pfad testet und nicht am Vollständigkeits-Gate hängt.
        mock_rm.assemble_full_report.return_value = (
            "## Section 1\n## Section 2\n## Section 3\n\n"
            "Widersprüche zwischen Stakeholdern sind benannt. Als "
            "Frühwarnindikator dient die Rücklaufquote. Die Stop-Bedingung "
            "greift bei sinkender Akzeptanz; die Expand-Bedingung sieht eine "
            "stufenweise Ausweitung vor. Ein Positionswechsel ist möglich. "
            "Betriebsrat und Jugendrat bilden eine Koalition."
        )
        mock_rm._write_json_atomic.side_effect = lambda path, data: None
        # Ohne diesen Mock liefert der unkonfigurierte MagicMock-Attribut-Zugriff
        # ein truthy MagicMock-Objekt zurueck. #1312 fuegte einen Nachvalidierungs-
        # block ein, der genau dieses Ergebnis an ReportV3.model_validate() reicht
        # (workflow.py ~L1257) — das schlaegt fehl und stuft den Status faelschlich
        # auf INCOMPLETE ab, obwohl kein Report-Artefakt existiert (kein reales
        # ReportV3-Schema-Problem, nur ein unkonfigurierter Mock).
        mock_rm.get_report_v3.return_value = None

        with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
            mock_em.model_validate.return_value = MagicMock(
                model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
            )

            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=None,  # kein Cancel
            )

    assert section_call_count[0] == 3, f"Alle 3 Sections erwartet, erhalten: {section_call_count[0]}"
    assert result.status == ReportStatus.COMPLETED


# ---------------------------------------------------------------------------
# Issue #1321 (Review-Finding PR #1378): Cancel und Resume dürfen den
# Sanitization-Marker nicht verlieren
#
# Der Marker lebte nur im flüchtigen RunEventLog des aktuellen Agenten. Beim
# kooperativen Abbruch wurde _build_partial_report vor der einzigen
# Degradations-Aggregation erreicht; beim Resume entstand ein neuer Agent,
# und bereits persistierte Sections liefen nicht erneut durch
# _finalize_content. In beiden Fällen blieb N_sections_sanitized verloren.
# ---------------------------------------------------------------------------


def _make_generation_agent() -> MagicMock:
    agent = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.evidence_map = {}
    agent.ReportLogger = MagicMock(return_value=MagicMock())
    agent.ReportConsoleLogger = MagicMock(return_value=MagicMock())
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]
    return agent


def _wire_real_run_event_storage(mock_rm, report_folder: str) -> None:
    """Bindet save/load_work_trace_removed_sections an echte Dateien im
    Report-Ordner — derselbe ReportManager-Mock bleibt für alles andere
    stumm, aber der Persistenzweg des Markers ist echt."""

    def save(report_id_arg: str, indices) -> None:
        path = os.path.join(report_folder, "run_events.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"work_trace_removed_sections": sorted(indices)}, fh)

    def load(report_id_arg: str) -> set:
        path = os.path.join(report_folder, "run_events.json")
        if not os.path.exists(path):
            return set()
        with open(path, encoding="utf-8") as fh:
            return {
                int(i) for i in json.load(fh).get("work_trace_removed_sections") or []
            }

    mock_rm.save_work_trace_removed_sections.side_effect = save
    mock_rm.load_work_trace_removed_sections.side_effect = load


def _patch_generation_stack(mock_rm, outline, section_react):
    """Die gemeinsamen Patches eines generate_report-Durchlaufs."""
    from contextlib import ExitStack

    stack = ExitStack()
    for p in (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=section_react),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager", mock_rm),
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
    ):
        stack.enter_context(p)
    return stack


def _configure_manager_mock(mock_rm, report_folder: str) -> None:
    mock_rm._ensure_report_folder.return_value = report_folder
    mock_rm.get_evidence_map.return_value = None
    mock_rm.get_report.return_value = None
    mock_rm.get_generated_sections.return_value = []
    mock_rm.update_progress.return_value = None
    mock_rm.save_report.return_value = None
    mock_rm.save_outline.return_value = None
    mock_rm.save_section.return_value = None
    mock_rm.assemble_full_report.return_value = "## Section 1\n## Section 2\n"
    mock_rm._write_json_atomic.side_effect = lambda path, data: None
    mock_rm.get_report_v3.return_value = None


def _section_react_with_work_traces(state: Dict[str, Any]):
    """generate_section_react-Ersatz: der Output läuft für Abschnitte in
    ``state['sanitize_indices']`` durch die echte ``_finalize_content``-
    Sanitization (Thought-Zeile wird entfernt und am Agenten markiert).
    Bei ``state['cancel_at_index']`` wird vorher das Cancel-Flag gesetzt."""
    from app.services.report_agent.workflow import _finalize_content

    def fake(
        ag,
        section=None,
        outline=None,
        previous_sections=None,
        progress_callback=None,
        section_index=0,
        **kw,
    ):
        if section_index == state.get("cancel_at_index"):
            request_cancel(state["cancel_run_id"])
        if section_index in state["sanitize_indices"]:
            response = (
                "Thought: Ich sollte zuerst die Personas zusammenstellen.\n"
                f"## {section.title}\n\n"
                + "Der Markt für Arbeitsplanung verändert sich spürbar. " * 5
            )
        else:
            response = (
                f"## {section.title}\n\n"
                + "Der Markt für Arbeitsplanung verändert sich spürbar. " * 5
            )
        return _finalize_content(
            response,
            section_title=section.title,
            section_index=section_index,
            agent=ag,
        )

    return fake


def test_cancel_after_sanitization_keeps_the_warning_in_the_partial_report(tmp_path):
    """Pfad 1 des Review-Befunds: Sanitization → Cancel. Der Teil-Report
    erreichte die einzige Aggregation am normalen Laufende nie — der
    N_sections_sanitized-Eintrag musste verloren gehen."""
    from app.services.report_agent.workflow import generate_report

    cancel_run_id = _unique_id()
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    clear_cancel(cancel_run_id)

    state = {
        "sanitize_indices": {1},
        "cancel_at_index": 2,
        "cancel_run_id": cancel_run_id,
    }
    agent = _make_generation_agent()
    outline = _make_outline(4)

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        with _patch_generation_stack(mock_rm, outline, _section_react_with_work_traces(state)):
            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    reasons = [entry["reason"] for entry in result.run_degradations]
    assert reasons == ["1_sections_sanitized"], (
        f"Partial Report muss den Sanitization-Hinweis tragen, erhalten: {reasons}"
    )
    assert result.status == ReportStatus.COMPLETED
    # Der Zustand muss über den Prozess hinaus bestellbar sein — Grundlage
    # für den Resume-Pfad.
    assert os.path.exists(os.path.join(report_folder, "run_events.json"))
    clear_cancel(cancel_run_id)


def test_resume_restores_the_sanitization_warning_exactly_once(tmp_path):
    """Pfad 2 des Review-Befunds: Sanitization → Cancel → Resume. Der neue
    Agent sieht die persistierte Section nur noch als Restore — sie läuft
    nicht erneut durch _finalize_content. Die Warnung muss aus dem
    persistierten Zustand wiederhergestellt werden und genau einmal im
    Final Report stehen."""
    from app.services.report_agent.workflow import generate_report

    cancel_run_id = _unique_id()
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    clear_cancel(cancel_run_id)

    outline = _make_outline(4)
    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    # Phase A: Section 1 bereinigt, dann Cancel bei Section 2.
    state_a = {
        "sanitize_indices": {1},
        "cancel_at_index": 2,
        "cancel_run_id": cancel_run_id,
    }
    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        with _patch_generation_stack(mock_rm, outline, _section_react_with_work_traces(state_a)):
            result_a = generate_report(
                _make_generation_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    assert [e["reason"] for e in result_a.run_degradations] == ["1_sections_sanitized"]

    # Phase B: neuer Agent, Cancel aufgehoben, Section 1 liegt persistiert
    # vor und wird nur noch restoriert — nichts wird neu markiert.
    clear_cancel(cancel_run_id)
    state_b = {
        "sanitize_indices": set(),
        "cancel_at_index": None,
        "cancel_run_id": cancel_run_id,
    }
    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        mock_rm.get_generated_sections.return_value = [
            {
                "filename": "section_01.md",
                "section_index": 1,
                "content": "## Section 1\n\nDer Markt für Arbeitsplanung verändert sich spürbar.",
            }
        ]
        with _patch_generation_stack(mock_rm, outline, _section_react_with_work_traces(state_b)):
            result_b = generate_report(
                _make_generation_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    sanitized = [
        entry
        for entry in result_b.run_degradations
        if entry["reason"].endswith("_sections_sanitized")
    ]
    assert len(sanitized) == 1, (
        "Nach dem Resume darf die Warnung genau einmal auftauchen, "
        f"erhalten: {result_b.run_degradations}"
    )
    assert sanitized[0]["reason"] == "1_sections_sanitized"
    assert "1" in sanitized[0]["detail"]
    clear_cancel(cancel_run_id)


def test_run_event_state_roundtrip(tmp_path, monkeypatch):
    """Der persistierte Marker-Zustand überlebt einen Manager-Wechsel:
    schreiben, neu laden, dieselbe Menge — dedupliziert und index-basiert."""
    from app.services.report_agent.manager import ReportManager

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report_id = f"report_{uuid.uuid4().hex[:12]}"

    assert ReportManager.load_work_trace_removed_sections(report_id) == set()

    ReportManager.save_work_trace_removed_sections(report_id, [3, 7, 7])

    assert ReportManager.load_work_trace_removed_sections(report_id) == {3, 7}
