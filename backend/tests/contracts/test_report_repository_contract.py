"""Contract-Tests fuer ``app.repositories.report_repository`` (Issue #1580).

Prueft die Invarianten, die der Port in seinen Docstrings festschreibt, gegen
``FileReportRepository`` — den einen heutigen Adapter. Der PostgreSQL-Adapter
aus #1588 muss dieselben Zusagen einhalten; diese Datei ist die Referenz
dafuer (wiederverwendbares Muster wie
``tests/contracts/test_simulation_repository_contract.py``:
``pytest.mark.parametrize`` ueber ``repo`` fuer weitere Adapter).

Jede Fixture bekommt ihr eigenes ``tmp_path``, damit kein Test in das echte
Upload-Verzeichnis schreibt.

Kerninvarianten:
1. ``get`` gibt ``None`` zurueck fuer unbekannte IDs, korrupte Manifeste und
   Manifeste ohne Pflichtfeld — nie ein Raise.
2. ``get`` faellt auf das Legacy-Flachformat (``<report_id>.json``) zurueck,
   wenn das Ordnerformat fehlt.
3. ``save`` schreibt ausschliesslich ``meta.json`` — kein Report-Inhalt
   (``report-v3.json``, ``full_report.md``, ``outline.json``, Sections, Logs)
   laeuft ueber den Port (Plan §11 Klasse B).
4. ``list`` filtert optional nach ``simulation_id`` und findet Reports aus
   beiden Formaten.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.report_record_contract import ReportRecord
from app.repositories.report_repository import ReportRepository, get_report_repository
from app.services.file_report_store import FileReportRepository

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_record(
    report_id: str = "report_aabbccdd0011",
    simulation_id: str = "sim_aabbccdd0011",
    graph_id: str = "graph_001",
    status: str = "completed",
    **overrides: Any,
) -> ReportRecord:
    base: dict[str, Any] = {
        "report_id": report_id,
        "simulation_id": simulation_id,
        "graph_id": graph_id,
        "simulation_requirement": "Testfrage",
        "status": status,
        "outline": {
            "title": "Demo",
            "summary": "Zusammenfassung",
            "sections": [
                {"title": "Intro", "content": "Body", "description": "—"}
            ],
        },
        "markdown_content": "# Demo\n\nBody",
        "missing_sections": [],
        "created_at": "2026-04-23T00:00:00",
        "completed_at": "2026-04-23T00:05:00",
        "error": None,
        "has_evidence": True,
        "evidence_sections": 1,
        "simulation_snapshot": {"status": "completed", "current_round": 5},
        "run_degradations": [{"kind": "low_interview_coverage", "detail": "..."}],
    }
    base.update(overrides)
    return ReportRecord(**base)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> FileReportRepository:
    """Isolierter Dateiadapter — jeder Test schreibt in sein eigenes tmp_path."""
    return FileReportRepository(str(tmp_path / "reports"))


# ---------------------------------------------------------------------------
# ReportRecord — Pflichtfelder und Roundtrip
# ---------------------------------------------------------------------------


def test_report_record_requires_five_mandatory_fields():
    """Ohne ``status`` scheitert ``from_dict`` mit ``ValidationError``.

    Genau wie der bisherige Ladepfad (``data['status']``) bei einem
    fehlenden Schluessel mit ``KeyError`` scheiterte.
    """
    data = {
        "report_id": "report_aabbccdd0011",
        "simulation_id": "sim_aabbccdd0011",
        "graph_id": "graph_001",
        "simulation_requirement": "Testfrage",
        # status fehlt
    }
    with pytest.raises(ValidationError):
        ReportRecord.from_dict(data)


def test_report_record_optional_fields_fall_back_to_defaults():
    """Ein Altbestand ohne die juengeren Felder bleibt lesbar."""
    minimal = {
        "report_id": "report_aabbccdd0011",
        "simulation_id": "sim_aabbccdd0011",
        "graph_id": "graph_001",
        "simulation_requirement": "Testfrage",
        "status": "pending",
    }
    record = ReportRecord.from_dict(minimal)

    assert record.outline is None
    assert record.markdown_content == ""
    assert record.missing_sections == []
    assert record.simulation_snapshot is None
    assert record.run_degradations == []


def test_report_record_roundtrip_preserves_all_fields():
    record = _make_record()
    dumped = record.to_dict()

    restored = ReportRecord.from_dict(dumped)
    assert restored.to_dict() == dumped


def test_report_record_covers_every_key_of_report_to_dict():
    """``ReportRecord`` hat ``extra="ignore"``: ein neues Feld in
    ``Report.to_dict()`` ohne Gegenstueck im Vertrag ginge beim Speichern
    ueber den Port still verloren. Dieser Test schlaegt dann an."""
    from app.models.report import Report, ReportStatus

    report = Report(
        report_id='report_keys',
        simulation_id='sim_keys',
        graph_id='graph_keys',
        simulation_requirement='Frage',
        status=ReportStatus.COMPLETED,
    )

    assert set(report.to_dict()) == set(ReportRecord.model_fields)
    assert ReportRecord.from_dict(report.to_dict()).to_dict() == report.to_dict()


# ---------------------------------------------------------------------------
# get — None-Zusage
# ---------------------------------------------------------------------------


def test_get_returns_none_for_unknown_report_id(repo):
    assert repo.get("report_unbekannt00") is None


def test_get_returns_record_after_save(repo):
    record = _make_record()
    repo.save(record)

    loaded = repo.get(record.report_id)

    assert loaded is not None
    assert loaded.report_id == record.report_id
    assert loaded.status == "completed"
    assert loaded.outline == record.outline


def test_get_returns_none_for_corrupt_meta_json(repo, tmp_path):
    """Korruptes JSON -> ``None``, kein Crash."""
    reports_dir = tmp_path / "reports"
    report_dir = reports_dir / "report_kaputt0001"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "meta.json").write_text("{ kaputtes JSON", encoding="utf-8")

    assert repo.get("report_kaputt0001") is None


def test_get_returns_none_for_manifest_missing_mandatory_field(repo, tmp_path):
    """Ein valides JSON ohne Pflichtfeld zaehlt als fehlend, kein Raise."""
    reports_dir = tmp_path / "reports"
    report_dir = reports_dir / "report_unvollst01"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "meta.json").write_text(
        json.dumps({"report_id": "report_unvollst01"}), encoding="utf-8"
    )

    assert repo.get("report_unvollst01") is None


def test_get_falls_back_to_legacy_flat_format(repo, tmp_path):
    """Fehlt das Ordnerformat, wird ``<report_id>.json`` direkt gelesen."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    record = _make_record(report_id="report_legacy0001")
    (reports_dir / "report_legacy0001.json").write_text(
        json.dumps(record.to_dict()), encoding="utf-8"
    )

    loaded = repo.get("report_legacy0001")

    assert loaded is not None
    assert loaded.report_id == "report_legacy0001"
    assert loaded.simulation_id == record.simulation_id


def test_get_prefers_folder_format_over_legacy_flat_format(repo, tmp_path):
    """Existieren beide Formate, gewinnt das Ordnerformat (meta.json)."""
    reports_dir = tmp_path / "reports"
    report_dir = reports_dir / "report_beide00001"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "meta.json").write_text(
        json.dumps(_make_record(report_id="report_beide00001", status="completed").to_dict()),
        encoding="utf-8",
    )
    (reports_dir / "report_beide00001.json").write_text(
        json.dumps(_make_record(report_id="report_beide00001", status="failed").to_dict()),
        encoding="utf-8",
    )

    loaded = repo.get("report_beide00001")

    assert loaded is not None
    assert loaded.status == "completed"


# ---------------------------------------------------------------------------
# save — schreibt ausschliesslich meta.json (Plan §11 Klasse A vs. B)
# ---------------------------------------------------------------------------


def test_save_persists_to_disk_as_meta_json(repo, tmp_path):
    record = _make_record()
    repo.save(record)

    meta_path = tmp_path / "reports" / record.report_id / "meta.json"
    assert meta_path.exists()


def test_save_returns_the_saved_record(repo):
    record = _make_record()
    returned = repo.save(record)

    assert returned.report_id == record.report_id
    assert returned.status == record.status


def test_save_overwrites_previous_version(repo):
    original = _make_record(status="generating")
    repo.save(original)

    updated = _make_record(status="completed")
    repo.save(updated)

    loaded = repo.get(original.report_id)
    assert loaded is not None
    assert loaded.status == "completed"


def test_save_writes_only_meta_json_no_report_v3_or_markdown_files(repo, tmp_path):
    """Regressionstest (#1580): Report-Inhalte laufen NICHT ueber den Port.

    ``ReportV3``-Artefakte (``report-v3.json``), Roh-Markdown
    (``full_report.md``), Outline-Datei (``outline.json``) und Sections sind
    Plan-§11-Klasse-B-Inhalte — sie werden weiterhin direkt ueber
    ``report_agent/storage.py`` geschrieben, nie ueber
    ``ReportRepository.save``.
    """
    record = _make_record()
    repo.save(record)

    report_dir = tmp_path / "reports" / record.report_id
    written_files = {p.name for p in report_dir.iterdir()}

    assert written_files == {"meta.json"}
    assert "report-v3.json" not in written_files
    assert "full_report.md" not in written_files
    assert "outline.json" not in written_files


# ---------------------------------------------------------------------------
# list — Filter und Format-Uebergreifend
# ---------------------------------------------------------------------------


def test_list_returns_empty_for_missing_reports_dir(repo):
    assert repo.list() == []


def test_list_returns_all_reports_without_filter(repo):
    repo.save(_make_record(report_id="report_aaaa00000001", simulation_id="sim_a"))
    repo.save(_make_record(report_id="report_bbbb00000002", simulation_id="sim_b"))

    records = repo.list()

    assert {r.report_id for r in records} == {
        "report_aaaa00000001",
        "report_bbbb00000002",
    }


def test_list_filters_by_simulation_id(repo):
    repo.save(_make_record(report_id="report_aaaa00000001", simulation_id="sim_a"))
    repo.save(_make_record(report_id="report_bbbb00000002", simulation_id="sim_b"))

    records = repo.list(simulation_id="sim_b")

    assert [r.report_id for r in records] == ["report_bbbb00000002"]


def test_list_includes_legacy_flat_format_entries(repo, tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    legacy = _make_record(report_id="report_legacy0002", simulation_id="sim_legacy")
    (reports_dir / "report_legacy0002.json").write_text(
        json.dumps(legacy.to_dict()), encoding="utf-8"
    )
    repo.save(_make_record(report_id="report_neu00000001", simulation_id="sim_neu"))

    records = repo.list()

    assert {r.report_id for r in records} == {"report_legacy0002", "report_neu00000001"}


def test_list_skips_unreadable_entries(repo, tmp_path):
    reports_dir = tmp_path / "reports"
    report_dir = reports_dir / "report_kaputt0002"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "meta.json").write_text("{ kaputtes JSON", encoding="utf-8")
    repo.save(_make_record(report_id="report_gesund0001"))

    records = repo.list()

    assert [r.report_id for r in records] == ["report_gesund0001"]


# ---------------------------------------------------------------------------
# Fabrik
# ---------------------------------------------------------------------------


def test_get_report_repository_returns_file_adapter(tmp_path):
    repository: ReportRepository = get_report_repository(reports_dir=str(tmp_path / "reports"))

    assert isinstance(repository, FileReportRepository)
