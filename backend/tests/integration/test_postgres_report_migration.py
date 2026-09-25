"""Die Report-Datenmigration muss nachweislich nichts verlieren (§11, PR 9).

Fixture → ``migrate`` → ``verify``: jedes Feld jedes Reports wird
gegenübergestellt, Schlüssel, Kennungen und Zeitstempel bleiben identisch,
die Quelle bleibt byteweise unverändert, ein zweiter Lauf schreibt nichts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

from app.contracts import Project
from app.contracts.report_record_contract import ReportRecord
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.repositories.report_repository import (
    PostgresReportRepository,
)
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
)
from app.infrastructure.postgres.session import Database
from scripts import migrate_reports_to_postgres as skript

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_ID = 'proj_112233445566'
SIM_ID = 'sim_112233445566'


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    command.upgrade(config, 'head')
    database = Database(postgres_database_url)
    PostgresProjectRepository(database=database).add_existing(
        Project(
            project_id=PROJECT_ID,
            name='Projekt',
            created_at='2026-09-01T10:00:00',
            updated_at='2026-09-01T10:00:00',
        )
    )
    PostgresSimulationRepository(database=database).add_existing(
        SimulationRecord(
            simulation_id=SIM_ID,
            project_id=PROJECT_ID,
            graph_id='graph_1',
            created_at='2026-09-01T11:00:00',
            updated_at='2026-09-01T11:00:00',
        )
    )
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresReportRepository:
    """Wird dem Skript mitgegeben, statt am globalen ``Config.DATABASE_URL`` zu drehen."""
    return PostgresReportRepository(database=migrated_db)


def _meta(report_id: str, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        'report_id': report_id,
        'simulation_id': SIM_ID,
        'graph_id': 'graph_1',
        'simulation_requirement': 'Frage',
        'status': 'completed',
    }
    data.update(overrides)
    return data


def _write_folder(root: Path, key: str, data: Any) -> None:
    folder = root / key
    folder.mkdir(parents=True)
    # Ein Report-Inhalt daneben, um zu belegen, dass er unberührt bleibt.
    (folder / 'report-v3.json').write_text('{"version": 3}', encoding='utf-8')
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
    (folder / 'meta.json').write_text(text, encoding='utf-8')


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


@pytest.fixture
def bestand(tmp_path: Path) -> Path:
    """Drei Reports: voll belegt, Altbestand mit abweichendem Ordnernamen,
    Legacy-Flachformat — plus ein Ordner ohne ``meta.json``."""
    root = tmp_path / 'reports'
    voll = ReportRecord(
        **_meta(
            'report_voll000001',
            outline={'title': 'T', 'summary': 'S', 'sections': []},
            markdown_content='# T\n\näöü',
            missing_sections=['X'],
            created_at='2026-09-02T08:15:00.123456',
            completed_at='2026-09-02T09:00:00',
            has_evidence=True,
            evidence_sections=2,
            simulation_snapshot={'rounds_completed': 3},
            run_degradations=[{'component': 'simulation', 'reason': 'r'}],
        )
    )
    _write_folder(root, voll.report_id, voll.to_dict())
    # Ordnername ≠ report_id im Manifest (Codex-Review auf #1601).
    _write_folder(root, 'report_deepseek_abc123', _meta('report_abc123'))
    (root / 'report_flach000001.json').write_text(
        json.dumps(_meta('report_flach000001')), encoding='utf-8'
    )
    # Ein Ordner ohne meta.json ist kein Report.
    (root / 'report_halb0000001').mkdir()
    return root


def test_migrate_then_verify_is_lossless(bestand, repo):
    vorher = _fingerprint(bestand)

    summary = skript.migrate(bestand, repository=repo)

    assert (summary.scanned, summary.inserted, summary.skipped, summary.failed) == (3, 3, 0, 0)
    result = skript.verify(bestand, repository=repo)
    assert result.deviations == []
    assert (result.verified, result.checked) == (3, 3)
    assert sorted(repo.list_ids()) == [
        'report_deepseek_abc123',
        'report_flach000001',
        'report_voll000001',
    ]
    alt = repo.get('report_deepseek_abc123')
    assert alt is not None and alt.report_id == 'report_abc123'
    voll = repo.get('report_voll000001')
    assert voll is not None and voll.created_at == '2026-09-02T08:15:00.123456'
    # Quelle unverändert.
    assert _fingerprint(bestand) == vorher


def test_second_run_is_idempotent(bestand, repo):
    skript.migrate(bestand, repository=repo)
    summary = skript.migrate(bestand, repository=repo)

    assert (summary.inserted, summary.skipped, summary.failed) == (0, 3, 0)


def test_dry_run_writes_nothing(bestand, repo):
    summary = skript.migrate(bestand, dry_run=True, repository=repo)

    assert summary.scanned == 3
    assert summary.inserted == 0
    assert repo.list_ids() == []


def test_missing_reports_dir_is_empty_and_not_created(tmp_path, repo):
    root = tmp_path / 'gibtesnicht'

    summary = skript.migrate(root, repository=repo)

    assert (summary.scanned, summary.failed) == (0, 0)
    assert not root.exists()


def test_verify_reports_a_changed_field(bestand, repo):
    skript.migrate(bestand, repository=repo)
    record = repo.get('report_flach000001')
    assert record is not None
    record.status = 'failed'
    repo.save(record)

    result = skript.verify(bestand, repository=repo)

    assert result.mismatched == {'report_flach000001'}
    assert any('report_flach000001.status' in line for line in result.deviations)


def test_orphan_and_unreadable_reports_fail_individually(bestand, repo):
    _write_folder(bestand, 'report_waise000001', _meta('report_waise000001', simulation_id='sim_geloescht000'))
    _write_folder(bestand, 'report_kaputt00001', '{kein json')
    _write_folder(bestand, 'report_ohnestatus1', {'report_id': 'report_ohnestatus1'})

    summary = skript.migrate(bestand, repository=repo)

    assert summary.inserted == 3
    assert summary.failed == 3
    assert any('report_waise000001' in line and 'sim_geloescht000' in line for line in summary.failures)
    assert any('report_kaputt00001' in line for line in summary.failures)
    assert any('report_ohnestatus1' in line for line in summary.failures)


def test_cli_exit_codes(bestand, repo, monkeypatch, capsys):
    monkeypatch.setattr(skript, 'PostgresReportRepository', lambda: repo)

    assert skript.main(['--reports-dir', str(bestand), '--dry-run']) == 0
    assert 'Scanned:   3' in capsys.readouterr().out
    assert skript.main(['--reports-dir', str(bestand), '--verify']) == 1
    assert skript.main(['--reports-dir', str(bestand)]) == 0
    assert skript.main(['--reports-dir', str(bestand), '--verify']) == 0
    assert 'Verified:  3/3' in capsys.readouterr().out
