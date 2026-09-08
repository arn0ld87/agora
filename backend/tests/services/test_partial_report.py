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
        # Issue #1479: _build_partial_report ruft jetzt _apply_requirement_check
        # auf; agent.simulation_requirement ist hier ein unkonfigurierter
        # MagicMock, den detect_report_intent() nicht verarbeiten kann. Der
        # Requirement-Checker ist nicht Gegenstand dieses Tests — Muster aus
        # tests/services/test_report_requirement_gating.py:143-149.
        patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
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

    # Issue #1479: die Outline hat 3 Sections, nur 2 sind fertig — der
    # Abbruch verhinderte die dritte. Ein Teil-Report mit fehlenden Sections
    # ist ein ehrliches INCOMPLETE, nicht COMPLETED.
    assert result.status == ReportStatus.INCOMPLETE
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
        # Issue #1479: _build_partial_report ruft jetzt _apply_requirement_check
        # auf; agent.simulation_requirement ist hier ein unkonfigurierter
        # MagicMock. Der Requirement-Checker ist nicht Gegenstand dieses Tests.
        patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
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
        # Issue #1479: _build_partial_report ruft jetzt _apply_requirement_check
        # auf; agent.simulation_requirement ist hier ein unkonfigurierter
        # MagicMock. Der Requirement-Checker ist nicht Gegenstand dieses Tests.
        patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
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
    # Issue #1479: die Outline hat 3 Sections, nur 1 ist fertig — der Abbruch
    # verhinderte 2 weitere. Kein Persona-Ausfall, aber trotzdem INCOMPLETE.
    assert result.status == ReportStatus.INCOMPLETE


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
        # Issue #1479: _build_partial_report ruft jetzt _apply_requirement_check
        # auf — nicht Gegenstand dieses Tests, der ausschließlich den Cancel-Pfad
        # prüft.
        patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
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
    # Issue #1479: die Outline hat 4 Sections, nur 2 wurden erzeugt — der
    # Abbruch verhinderte die anderen beiden. Ein ehrlicher Teil-Report mit
    # fehlenden Sections ist INCOMPLETE, nicht COMPLETED.
    assert result.status == ReportStatus.INCOMPLETE
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
# Codex-Review PR #1475, Runde 2, Finding 2: eine Markdown-only-Waise (auf
# Platte vorhanden, aber ohne Evidence-Eintrag) darf weder in
# ``previous_sections`` noch in ``completed_section_titles`` einfließen,
# bevor sie regeneriert wurde — sonst sieht der Prompt-Kontext den alten
# Waiseninhalt, und der Fortschritt zählt die Section nach der Regeneration
# ein zweites Mal.
# ---------------------------------------------------------------------------


def test_generate_report_filters_markdown_only_orphan_from_context(tmp_path):
    """Eine gültig persistierte Section fließt in Kontext und Fortschritt ein,
    eine Markdown-only-Waise (kein Evidence-Eintrag) NICHT — bis sie
    regeneriert wurde."""
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

    outline = _make_outline(2)  # "Section 1", "Section 2"

    section_calls: list[Dict[str, Any]] = []

    def fake_section(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        section_calls.append(
            {
                "section_index": section_index,
                "previous_sections": list(previous_sections or []),
            }
        )
        return f"Content for {section.title}"

    progress_snapshots: list[list] = []

    def fake_update_progress(*args: Any, **kwargs: Any) -> None:
        progress_snapshots.append(list(kwargs.get("completed_sections") or []))

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    persisted_evidence_map = {
        "schema_version": 2,
        "sections": [{"section_index": 1, "claims": []}],
    }

    with (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=fake_section),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        # Evidence-Map kommt bereits normalisiert zurück — kein Init-Zweig,
        # kein Pydantic-Roundtrip nötig, um section_index=1 als "hat Evidence"
        # auszuweisen.
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=persisted_evidence_map),
        patch("app.services.report_agent.workflow.normalize_persisted_evidence_map", side_effect=lambda raw: raw),
    ):
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm.get_evidence_map.return_value = persisted_evidence_map
        mock_rm.get_report.return_value = None
        # Section 1: valide persistiert (Evidence vorhanden) — Section 2:
        # Markdown liegt auf Platte, aber kein Evidence-Eintrag (Waise).
        mock_rm.get_generated_sections.return_value = [
            {
                "filename": "section_01.md",
                "section_index": 1,
                "content": "OLD VALID CONTENT",
            },
            {
                "filename": "section_02.md",
                "section_index": 2,
                "content": "OLD ORPHAN CONTENT",
            },
        ]
        mock_rm._clean_section_content.side_effect = lambda content, _title: content
        # Kein reales File-Handling nötig: die Waisen-Entfernung greift nur,
        # wenn unter diesem Pfad tatsächlich etwas liegt.
        mock_rm._get_section_path.return_value = str(tmp_path / "does-not-exist.md")
        mock_rm.update_progress.side_effect = fake_update_progress
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.save_section.return_value = None
        mock_rm.assemble_full_report.return_value = "## Section 1\n## Section 2\n"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None
        mock_rm.get_report_v3.return_value = None

        result = generate_report(
            agent,
            progress_callback=None,
            report_id=report_id,
            cancel_run_id=None,
        )

    # Section 1 (Evidence vorhanden) wird restauriert, nicht neu generiert.
    generated_indices = [c["section_index"] for c in section_calls]
    assert generated_indices == [2], (
        f"Nur die Waise (Section 2) darf neu generiert werden, erhalten: {generated_indices}"
    )

    # Der Prompt-Kontext für die Regeneration von Section 2 sieht ausschließlich
    # den validen Inhalt von Section 1 — nicht den alten Waiseninhalt.
    orphan_call = section_calls[0]
    assert orphan_call["previous_sections"] == ["OLD VALID CONTENT"], (
        "previous_sections darf beim Regenerieren der Waise weder ihren "
        f"eigenen alten Inhalt noch Duplikate enthalten, erhalten: {orphan_call['previous_sections']}"
    )

    # Kein Fortschritts-Snapshot enthält "Section 2" doppelt — die Waise wird
    # erst nach erfolgreicher Regeneration genau einmal als abgeschlossen geführt.
    for snapshot in progress_snapshots:
        assert snapshot.count("Section 2") <= 1, (
            f"Section 2 taucht in einem Fortschritts-Snapshot doppelt auf: {snapshot}"
        )

    # CodeRabbit-Review PR #1475, Runde 3, Finding 4: die Negativ-Assertion
    # oben (<=1 in jedem Snapshot) würde auch dann grün bleiben, wenn
    # "Section 2" in KEINEM Snapshot auftaucht — z. B. weil sie nie als
    # abgeschlossen gemeldet wird. Die Positiv-Assertion stellt sicher, dass
    # sie im letzten Snapshot tatsächlich genau einmal steht.
    assert progress_snapshots[-1].count("Section 2") == 1, (
        "Die regenerierte Section 2 muss im letzten Fortschritts-Snapshot "
        f"genau einmal stehen, erhalten: {progress_snapshots[-1]}"
    )

    assert result is not None


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
    """Bindet save/load_work_trace_removed_sections UND
    save/load_fallback_outline_used an dieselbe echte Datei im Report-Ordner
    — derselbe ReportManager-Mock bleibt für alles andere stumm, aber der
    Persistenzweg beider Marker ist echt (Issue #1479, Codex-Review Runde 3:
    beide Marker teilen sich in der echten Implementierung dasselbe
    Run-Events-Artefakt, siehe ``ReportManager.save_fallback_outline_used``)."""
    path = os.path.join(report_folder, "run_events.json")

    def _read() -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def _write(data: Dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def save_markers(report_id_arg: str, indices) -> None:
        data = _read()
        data["work_trace_removed_sections"] = sorted(indices)
        _write(data)

    def load_markers(report_id_arg: str) -> set:
        return {int(i) for i in _read().get("work_trace_removed_sections") or []}

    def save_fallback(report_id_arg: str, used: bool) -> None:
        data = _read()
        data["fallback_outline_used"] = bool(used)
        _write(data)

    def load_fallback(report_id_arg: str) -> bool:
        return bool(_read().get("fallback_outline_used", False))

    mock_rm.save_work_trace_removed_sections.side_effect = save_markers
    mock_rm.load_work_trace_removed_sections.side_effect = load_markers
    mock_rm.save_fallback_outline_used.side_effect = save_fallback
    mock_rm.load_fallback_outline_used.side_effect = load_fallback


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
    # Codex-Review PR #1475, Runde 2, Finding 1: ein unkonfigurierter
    # ``_get_section_path``-Mock liefert per Default einen synthetischen
    # ``__fspath__``-Wert, der in dieser Umgebung als "existierend" gilt —
    # ``_remove_orphan_markdown`` würde dann versuchen, ihn zu entfernen, und
    # jetzt (statt den Fehler stillschweigend zu schlucken) mit ``OSError``
    # abbrechen. Ein echter, garantiert nicht existierender Pfad unter dem
    # Test-Report-Ordner hält den Mock realistisch, ohne diesen Fehlschlag
    # künstlich zu provozieren.
    mock_rm._get_section_path.side_effect = (
        lambda _report_id, idx: os.path.join(report_folder, f"section_{idx:02d}.md")
    )


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
        with (
            _patch_generation_stack(mock_rm, outline, _section_react_with_work_traces(state)),
            # Issue #1479: _build_partial_report ruft jetzt
            # _apply_requirement_check auf — nicht Gegenstand dieses Tests, der
            # ausschließlich die Sanitization- und Cancel-Degradationen prüft.
            patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
        ):
            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    reasons = [entry["reason"] for entry in result.run_degradations]
    # Issue #1479: die Outline hat 4 Sections, Cancel greift nach Section 2 —
    # 2 Sections wurden nie angefasst. Der Cancel-Hinweis kommt hinzu, ohne
    # den bestehenden Sanitization-Hinweis zu verdrängen.
    assert reasons == ["1_sections_sanitized", "2_sections_missing_after_cancel"], (
        f"Partial Report muss Sanitization- und Cancel-Hinweis tragen, erhalten: {reasons}"
    )
    assert result.status == ReportStatus.INCOMPLETE
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
        with (
            _patch_generation_stack(mock_rm, outline, _section_react_with_work_traces(state_a)),
            # Issue #1479: nicht Gegenstand dieses Tests (siehe Test oben).
            patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
        ):
            result_a = generate_report(
                _make_generation_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    # Issue #1479: outline=4, Cancel nach Section 2 — 2 Sections fehlen.
    assert [e["reason"] for e in result_a.run_degradations] == [
        "1_sections_sanitized",
        "2_sections_missing_after_cancel",
    ]

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


def test_fallback_outline_used_is_persisted_before_missing_sections_early_return(
    tmp_path,
):
    """Codex-Review Runde 2, Finding 2: faellt plan_outline() in den Fallback
    (LLM-Aufruf scheitert, kein Cancel), treffen die drei fest verdrahteten
    Ersatz-Sections weder ein Intent-Preset noch die Pflichtabschnitte aus
    DEFAULT_REPORT_SECTIONS — generate_report() kehrt im missing-Zweig lange
    vor der einzigen Degradations-Aggregation zurueck. Ohne den Fix
    persistiert dieser Pfad ``outline_planning`` nie, obwohl die Struktur des
    Berichts nicht vom Modell stammt. Der Test geht den echten
    plan_outline()-Fallback-Pfad, statt collect_run_degradations() direkt
    aufzurufen."""
    from app.services.report_agent.workflow import generate_report

    report_id = f"report_{uuid.uuid4().hex[:12]}"
    agent = _make_generation_agent()
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {"total_nodes": 0, "total_edges": 0, "entity_types": {}},
        "total_entities": 0,
        "related_facts": [],
    }
    # Echte plan_outline()-Fallback-Logik ausloesen, nicht mocken.
    agent.llm.chat_json.side_effect = RuntimeError("LLM nicht erreichbar")

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "schema_version": 2,
                    "report_id": report_id,
                    "simulation_id": "sim_test",
                    "global_evidence": [],
                    "sections": [],
                }
            )
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        with (
            patch("app.services.report_agent.workflow.ReportManager", mock_rm),
            patch(
                "app.services.report_agent.workflow.migrate_v1_to_v2",
                return_value=None,
            ),
        ):
            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=None,
            )

    assert result.status == ReportStatus.INCOMPLETE
    reasons = [entry["reason"] for entry in result.run_degradations]
    assert "fallback_outline_used" in reasons, (
        "outline_planning-Degradation fehlt im missing-Zweig, erhalten: "
        f"{result.run_degradations}"
    )


def test_run_event_state_roundtrip(tmp_path, monkeypatch):
    """Der persistierte Marker-Zustand überlebt einen Manager-Wechsel:
    schreiben, neu laden, dieselbe Menge — dedupliziert und index-basiert."""
    from app.services.report_agent.manager import ReportManager

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report_id = f"report_{uuid.uuid4().hex[:12]}"

    assert ReportManager.load_work_trace_removed_sections(report_id) == set()

    ReportManager.save_work_trace_removed_sections(report_id, [3, 7, 7])

    assert ReportManager.load_work_trace_removed_sections(report_id) == {3, 7}


# ---------------------------------------------------------------------------
# Codex-Review Runde 3, Finding 1: ``failed_section_indices`` ueberlebt den
# Resume nicht. Eine gescheiterte Section, die ein Resume nur noch aus der
# persistierten Evidence (``generation_failed``) restauriert statt neu zu
# generieren, muss weiterhin als fehlgeschlagen zaehlen — sonst hebt ein
# sonst vollstaendiger Rest-Lauf den Report faelschlich auf COMPLETED.
# ---------------------------------------------------------------------------


def test_resume_keeps_failed_section_marker_after_restore(tmp_path):
    """Section 2 scheitert (LLM-Exception) -> Cancel vor Section 3 -> Resume:
    Section 2 wird aus der persistierten Evidence (generation_failed=True)
    nur restauriert, nicht neu generiert. Der resultierende Report muss
    trotz erfolgreicher restlicher Sections INCOMPLETE bleiben."""
    from app.services.report_agent.workflow import generate_report

    cancel_run_id = _unique_id()
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    clear_cancel(cancel_run_id)

    outline = _make_outline(4)
    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    # Phase A: Section 2 scheitert, danach Cancel vor Section 3.
    def fake_section_a(
        ag,
        section=None,
        outline=None,
        previous_sections=None,
        progress_callback=None,
        section_index=0,
        **kw,
    ):
        if section_index == 2:
            request_cancel(cancel_run_id)
            raise RuntimeError("LLM nicht erreichbar")
        return f"## {section.title}\n\n" + "Inhalt zum Abschnitt. " * 3

    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "schema_version": 2,
                    "report_id": report_id,
                    "simulation_id": "sim_test",
                    "global_evidence": [],
                    "sections": [],
                }
            )
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        with (
            _patch_generation_stack(mock_rm, outline, fake_section_a),
            patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
        ):
            result_a = generate_report(
                _make_generation_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    assert result_a.status == ReportStatus.INCOMPLETE
    reasons_a = [e["reason"] for e in result_a.run_degradations]
    assert "1_sections_failed" in reasons_a, reasons_a

    # Phase B: Resume. Section 2 liegt persistiert vor (Markdown + Evidence
    # mit generation_failed=True) und wird nur restauriert. Sections 3+4
    # generieren erfolgreich.
    clear_cancel(cancel_run_id)

    def fake_section_b(
        ag,
        section=None,
        outline=None,
        previous_sections=None,
        progress_callback=None,
        section_index=0,
        **kw,
    ):
        return f"## {section.title}\n\n" + "Inhalt zum Abschnitt. " * 3

    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "schema_version": 2,
                    "report_id": report_id,
                    "simulation_id": "sim_test",
                    "global_evidence": [],
                    "sections": [
                        {
                            "section_index": 2,
                            "section_title": "Section 2",
                            "claims": [],
                            "hypotheses": [],
                            "hypotheses_appendix": [],
                            "data_gaps": [],
                            "generation_failed": True,
                        }
                    ],
                }
            )
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        mock_rm.get_generated_sections.return_value = [
            {
                "filename": "section_02.md",
                "section_index": 2,
                "content": "## Section 2\n\nDieser Abschnitt konnte nicht generiert werden.",
            }
        ]
        with (
            _patch_generation_stack(mock_rm, outline, fake_section_b),
            patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
        ):
            result_b = generate_report(
                _make_generation_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    assert result_b.status == ReportStatus.INCOMPLETE, (
        "Ein restaurierter, zuvor fehlgeschlagener Abschnitt darf den Report "
        f"nicht auf COMPLETED heben, run_degradations={result_b.run_degradations}"
    )
    reasons_b = [e["reason"] for e in result_b.run_degradations]
    assert "1_sections_failed" in reasons_b, reasons_b
    clear_cancel(cancel_run_id)


# ---------------------------------------------------------------------------
# Codex-Review Runde 3, Finding 2: ``fallback_outline_used`` ueberlebt den
# Resume nicht, UND die in Runde 2 in den missing-Zweig eingebaute Zuweisung
# ersetzt eine bereits persistierte Degradationsliste durch eine frisch
# berechnete statt sie zusammenzufuehren.
# ---------------------------------------------------------------------------


def test_resume_preserves_fallback_outline_degradation_after_cancel(tmp_path):
    """Fallback-Outline (LLM-Planung scheitert) -> Cancel direkt an der
    Post-Outline-Grenze -> Resume: ``outline_planning`` bleibt in
    ``run_degradations`` erhalten, und die beim Cancel zusaetzlich
    persistierte ``run_cancellation``-Degradation darf die
    Runde-2-Zuweisung im missing-Zweig nicht ueberschreiben (letztere kann
    ein frischer ``collect_run_degradations``-Aufruf im missing-Zweig gar
    nicht reproduzieren, da er keine Cancel-Information erhaelt — ihr
    Ueberleben beweist gezielt die Merge- statt Ersetzen-Semantik)."""
    from app.services.report_agent.workflow import generate_report

    cancel_run_id = _unique_id()
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    clear_cancel(cancel_run_id)

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    saved_reports: Dict[str, Any] = {}

    def make_agent() -> MagicMock:
        agent = _make_generation_agent()
        agent.graph_tools.get_simulation_context.return_value = {
            "graph_statistics": {"total_nodes": 0, "total_edges": 0, "entity_types": {}},
            "total_entities": 0,
            "related_facts": [],
        }
        # Echte plan_outline()-Fallback-Logik ausloesen, nicht mocken.
        agent.llm.chat_json.side_effect = RuntimeError("LLM nicht erreichbar")
        return agent

    # Phase A: Cancel ist bereits gesetzt, bevor generate_report startet —
    # der Lauf faellt in plan_outline() in den Fallback und bricht direkt an
    # der Post-Outline-Grenze ab, lange bevor der missing-Zweig erreicht wird.
    request_cancel(cancel_run_id)
    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "schema_version": 2,
                    "report_id": report_id,
                    "simulation_id": "sim_test",
                    "global_evidence": [],
                    "sections": [],
                }
            )
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        mock_rm.save_report.side_effect = lambda report_obj: saved_reports.__setitem__(
            "report", report_obj
        )
        mock_rm.get_report.return_value = None
        with (
            patch("app.services.report_agent.workflow.ReportManager", mock_rm),
            patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
            patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
        ):
            result_a = generate_report(
                make_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    assert result_a.status == ReportStatus.INCOMPLETE
    reasons_a = {e["component"]: e["reason"] for e in result_a.run_degradations}
    assert reasons_a.get("outline_planning") == "fallback_outline_used", (
        result_a.run_degradations
    )
    assert reasons_a.get("run_cancellation") == "3_sections_missing_after_cancel", (
        result_a.run_degradations
    )

    # Phase B: Resume. Cancel aufgehoben, neuer Agent (fallback_outline_used
    # startet wieder bei False). Die persistierte Fallback-Outline existiert
    # bereits -> plan_outline() wird umgangen, der missing-Zweig greift
    # erneut (3 Ersatz-Sections erfuellen die Pflichtabschnitte nicht).
    clear_cancel(cancel_run_id)
    with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "schema_version": 2,
                    "report_id": report_id,
                    "simulation_id": "sim_test",
                    "global_evidence": [],
                    "sections": [],
                }
            )
        )
        mock_rm = MagicMock()
        _configure_manager_mock(mock_rm, report_folder)
        _wire_real_run_event_storage(mock_rm, report_folder)
        mock_rm.get_report.return_value = saved_reports["report"]
        with (
            patch("app.services.report_agent.workflow.ReportManager", mock_rm),
            patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
        ):
            result_b = generate_report(
                make_agent(),
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    assert result_b.status == ReportStatus.INCOMPLETE
    reasons_b = {e["component"]: e["reason"] for e in result_b.run_degradations}
    assert reasons_b.get("outline_planning") == "fallback_outline_used", (
        f"outline_planning-Degradation ueberlebt den Resume nicht: {result_b.run_degradations}"
    )
    assert reasons_b.get("run_cancellation") == "3_sections_missing_after_cancel", (
        "Die Runde-2-Zuweisung im missing-Zweig darf die aus Phase A "
        f"persistierte run_cancellation-Degradation nicht verwerfen: {result_b.run_degradations}"
    )
    clear_cancel(cancel_run_id)
