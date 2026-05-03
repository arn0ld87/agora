"""Tests für scripts/migrate_reports_v1_to_v2.py.

Alle Tests rufen main(argv) direkt auf — kein Subprozess.
Fixtures verwenden tmp_path.

Import-Hinweis: ``tests/scripts/__init__.py`` registriert ``scripts`` als
Tests-Package, was den Top-Level-Import von ``backend/scripts`` verdeckt.
Wir laden das Migrations-Modul daher direkt per importlib.util, um den
Namespace-Konflikt zu umgehen, ohne die Test-Package-Struktur zu ändern.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import types

from app.contracts import EvidenceMapModel
from app.services.evidence_migrations import CURRENT_SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Migrations-Modul direkt laden (Namespace-Konflikt tests/scripts vs backend/scripts)
# ---------------------------------------------------------------------------
_BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_MIGRATION_SCRIPT = _BACKEND_ROOT / "scripts" / "migrate_reports_v1_to_v2.py"

_spec = importlib.util.spec_from_file_location(
    "backend_scripts.migrate_reports_v1_to_v2",
    _MIGRATION_SCRIPT,
    submodule_search_locations=[],
)
assert _spec is not None and _spec.loader is not None, (
    f"Migrations-Skript nicht gefunden: {_MIGRATION_SCRIPT}"
)
_migration_mod: types.ModuleType = importlib.util.module_from_spec(_spec)
# Pfad-Kontext: backend/ muss in sys.path sein, damit app.* Imports im Skript greifen
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
_spec.loader.exec_module(_migration_mod)  # type: ignore[union-attr]

main = _migration_mod.main
_process_file = _migration_mod._process_file


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Test-Fixtures
# ---------------------------------------------------------------------------

def _minimal_v1(report_id: str = "rep-001", simulation_id: str = "sim-001") -> dict:
    """Minimales v1-Evidence-Map-Payload mit einem validen Claim."""
    return {
        "schema_version": 1,
        "report_id": report_id,
        "simulation_id": simulation_id,
        "global_evidence": [],
        "sections": [
            {
                "schema_version": 1,
                "section_index": 1,
                "section_title": "Test-Section",
                "section_summary": "Zusammenfassung der Sektion",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Ein valider Test-Claim",
                        "confidence_label": "low",
                        "confidence_score": 0.3,
                        "evidence": [],
                        "audit_trail": [],
                    }
                ],
            }
        ],
    }


def _minimal_v2(report_id: str = "rep-001", simulation_id: str = "sim-001") -> dict:
    """Minimales v2-Payload — schema_version=2, keine section.schema_version."""
    return {
        "schema_version": 2,
        "report_id": report_id,
        "simulation_id": simulation_id,
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Test-Section",
                "section_summary": "Zusammenfassung der Sektion",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Ein valider Test-Claim",
                        "confidence_label": "low",
                        "confidence_score": 0.3,
                        "evidence": [],
                        "audit_trail": [],
                    }
                ],
            }
        ],
    }


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test 1: v1 → v2 Migration
# ---------------------------------------------------------------------------

def test_v1_migrated_to_v2_with_backup(tmp_path: pathlib.Path) -> None:
    """v1-Report wird zu v2 migriert; Backup .v1.bak.json enthält Originalinhalt."""
    target = tmp_path / "report.json"
    original = _minimal_v1()
    _write_json(target, original)

    exit_code = main([str(target)])

    assert exit_code == 0, "Exit-Code muss 0 sein"

    # Datei auf v2 gehoben
    result = _read_json(target)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION

    # Backup existiert mit Originalinhalt
    backup = tmp_path / "report.v1.bak.json"
    assert backup.exists(), "Backup .v1.bak.json muss existieren"
    backup_data = _read_json(backup)
    assert backup_data["schema_version"] == 1
    assert backup_data == original


# ---------------------------------------------------------------------------
# Test 2: Zweiter Lauf ist no-op (idempotent)
# ---------------------------------------------------------------------------

def test_second_run_is_noop(tmp_path: pathlib.Path) -> None:
    """Zweiter Lauf: schema_version bereits 2 → kein zweites Backup, Datei unverändert."""
    target = tmp_path / "report.json"
    _write_json(target, _minimal_v1())

    # Erster Lauf: migriert
    assert main([str(target)]) == 0

    backup = tmp_path / "report.v1.bak.json"
    assert backup.exists()
    backup_mtime_after_first = backup.stat().st_mtime
    target_content_after_first = _read_json(target)

    # Zweiter Lauf: no-op
    assert main([str(target)]) == 0

    # Backup unverändert (mtime gleich)
    assert backup.stat().st_mtime == backup_mtime_after_first, (
        "Backup darf beim zweiten Lauf nicht überschrieben werden"
    )
    # Dateiinhalt unverändert
    assert _read_json(target) == target_content_after_first


# ---------------------------------------------------------------------------
# Test 3: --dry-run schreibt nichts
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path: pathlib.Path) -> None:
    """--dry-run: weder Backup noch migrierte Datei werden geschrieben."""
    target = tmp_path / "report.json"
    original = _minimal_v1()
    _write_json(target, original)

    exit_code = main([str(target), "--dry-run"])

    assert exit_code == 0

    # Datei unverändert (noch v1)
    assert _read_json(target)["schema_version"] == 1

    # Kein Backup
    backup = tmp_path / "report.v1.bak.json"
    assert not backup.exists(), "--dry-run darf kein Backup anlegen"


# ---------------------------------------------------------------------------
# Test 4: Kaputtes JSON → errors>=1, Exit-Code 1, andere Files noch verarbeitet
# ---------------------------------------------------------------------------

def test_broken_json_increments_errors_and_continues(tmp_path: pathlib.Path) -> None:
    """Kaputtes JSON: errors >= 1, Exit-Code 1, valide Dateien trotzdem migriert."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not valid json", encoding="utf-8")

    good = tmp_path / "good.json"
    _write_json(good, _minimal_v1("rep-002", "sim-002"))

    exit_code = main([str(tmp_path), "--glob", "*.json"])

    assert exit_code == 1, "Exit-Code muss 1 sein wegen Fehler in broken.json"

    # Valide Datei trotzdem migriert
    assert _read_json(good)["schema_version"] == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Test 5: Rekursives Verzeichnis mit gemischten v1/v2/Müll-Files
# ---------------------------------------------------------------------------

def test_recursive_directory_mixed_files(tmp_path: pathlib.Path) -> None:
    """Verzeichnis mit v1, v2 und nicht-JSON-Dateien: korrekte Zählung."""
    subdir = tmp_path / "sub"
    subdir.mkdir()

    # v1 in root
    v1_root = tmp_path / "v1_root.json"
    _write_json(v1_root, _minimal_v1("r1", "s1"))

    # v2 in subdir (soll übersprungen werden)
    v2_sub = subdir / "v2_sub.json"
    _write_json(v2_sub, _minimal_v2("r2", "s2"))

    # v1 in subdir
    v1_sub = subdir / "v1_sub.json"
    _write_json(v1_sub, _minimal_v1("r3", "s3"))

    # Nicht-JSON-Datei (soll ignoriert werden, da Glob *.json)
    (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")

    exit_code = main([str(tmp_path), "--glob", "*.json"])
    assert exit_code == 0

    # Beide v1-Dateien migriert
    assert _read_json(v1_root)["schema_version"] == CURRENT_SCHEMA_VERSION
    assert _read_json(v1_sub)["schema_version"] == CURRENT_SCHEMA_VERSION

    # v2-Datei unverändert
    assert _read_json(v2_sub)["schema_version"] == 2

    # Backups nur für v1-Dateien
    assert (tmp_path / "v1_root.v1.bak.json").exists()
    assert (subdir / "v1_sub.v1.bak.json").exists()
    assert not (subdir / "v2_sub.v1.bak.json").exists()


# ---------------------------------------------------------------------------
# Test 6: Migrierte Daten sind gegen EvidenceMapModel valide
# ---------------------------------------------------------------------------

def test_migrated_data_validates_against_contract(tmp_path: pathlib.Path) -> None:
    """Nach Migration: Dateiinhalt besteht EvidenceMapModel.model_validate."""
    target = tmp_path / "report.json"
    _write_json(target, _minimal_v1())

    assert main([str(target)]) == 0

    result = _read_json(target)
    # Darf keine ValidationError werfen
    model = EvidenceMapModel.model_validate(result)
    assert model.schema_version == CURRENT_SCHEMA_VERSION
    assert model.report_id == "rep-001"
    assert model.simulation_id == "sim-001"
    assert len(model.sections) == 1
    assert model.sections[0].section_title == "Test-Section"
