"""Die Run-Datenmigration muss nachweislich nichts verlieren (§11, PR 8).

Fixture → ``migrate`` → ``verify``: jedes Feld jedes Manifests wird
gegenübergestellt, Kennungen und Zeitstempel bleiben identisch, die Quelle
bleibt byteweise unverändert, ein zweiter Lauf schreibt nichts.
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
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.repositories.run_repository import (
    PostgresRunRepository,
)
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
)
from app.infrastructure.postgres.session import Database
from scripts import migrate_runs_to_postgres as skript

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
def repo(migrated_db: Database) -> PostgresRunRepository:
    """Wird dem Skript mitgegeben, statt am globalen ``Config.DATABASE_URL`` zu drehen."""
    return PostgresRunRepository(database=migrated_db)


def _write_manifest(root: Path, name: str, data: Any) -> None:
    root.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
    (root / f'{name}.json').write_text(text, encoding='utf-8')


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


@pytest.fixture
def bestand(tmp_path: Path) -> Path:
    """Drei Runs: Simulationslauf mit Lease und Events, Graph-Build ohne
    Simulation, Altbestand mit fehlenden Feldern — plus Temp-Datei."""
    root = tmp_path / 'run_registry'
    _write_manifest(
        root,
        'run_sim000000001',
        {
            'run_id': 'run_sim000000001',
            'run_type': 'simulation_run',
            'entity_id': SIM_ID,
            'parent_run_id': None,
            'status': 'completed',
            'progress': 100,
            'message': 'Simulation abgeschlossen',
            'message_key': 'run.simulation_completed',
            'error': None,
            'started_at': '2026-09-02T08:15:00.123456',
            'updated_at': '2026-09-02T09:00:00',
            'completed_at': '2026-09-02T09:00:00',
            'artifacts': {'simulation': {'state': 'state.json'}},
            'resume_capability': {'available': True, 'action': 'resume'},
            'metadata': {
                'owner_pid': 4242,
                'owner_token': 'tok',
                'heartbeat_at': '2026-09-02T08:59:00+00:00',
                'lease_ttl_s': 90,
            },
            'linked_ids': {'simulation_id': SIM_ID, 'project_id': PROJECT_ID},
            'events': [{'timestamp': '2026-09-02T08:15:00', 'type': 'created'}],
        },
    )
    _write_manifest(
        root,
        'run_graph0000001',
        {
            'run_id': 'run_graph0000001',
            'run_type': 'graph_build',
            'entity_id': PROJECT_ID,
            'status': 'failed',
            'started_at': '2026-09-01T08:00:00',
            'updated_at': '2026-09-01T08:30:00',
            'linked_ids': {'project_id': PROJECT_ID, 'graph_id': 'graph_1'},
        },
    )
    # Altbestand: nur Kennung und Status, kein Zeitstempel.
    _write_manifest(root, 'run_alt000000001', {'run_id': 'run_alt000000001', 'status': 'ready'})
    # Temp-Datei eines atomaren Schreibvorgangs — kein Run.
    _write_manifest(root, '.tmp-json-abc', {'run_id': 'run_tmp000000001'})
    return root


def test_migrate_then_verify_is_lossless(bestand, repo):
    vorher = _fingerprint(bestand)

    summary = skript.migrate(bestand, repository=repo)

    assert (summary.scanned, summary.inserted, summary.skipped, summary.failed) == (3, 3, 0, 0)
    result = skript.verify(bestand, repository=repo)
    assert result.deviations == []
    assert (result.verified, result.checked) == (3, 3)
    loaded = repo.get('run_sim000000001')
    assert loaded is not None
    assert loaded.started_at == '2026-09-02T08:15:00.123456'
    assert loaded.metadata['owner_token'] == 'tok'
    # Der Altbestand bleibt so dünn, wie er war.
    alt = repo.get('run_alt000000001')
    assert alt is not None
    assert alt.to_manifest() == {'run_id': 'run_alt000000001', 'status': 'ready'}
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
    assert repo.list_all() == []


def test_missing_registry_dir_is_empty_and_not_created(tmp_path, repo):
    root = tmp_path / 'gibtesnicht'

    summary = skript.migrate(root, repository=repo)

    assert (summary.scanned, summary.failed) == (0, 0)
    assert not root.exists()


def test_verify_reports_a_changed_field(bestand, repo):
    skript.migrate(bestand, repository=repo)
    record = repo.get('run_graph0000001')
    assert record is not None
    record.status = 'manipuliert'
    repo.save(record)

    result = skript.verify(bestand, repository=repo)

    assert result.mismatched == {'run_graph0000001'}
    assert any('run_graph0000001.status' in line for line in result.deviations)


def test_verify_reports_a_field_present_on_one_side_only(bestand, repo):
    skript.migrate(bestand, repository=repo)
    record = repo.get('run_alt000000001')
    assert record is not None
    record.error = None  # gesetzt → steht jetzt als null im Manifest
    repo.save(record)

    result = skript.verify(bestand, repository=repo)

    assert result.mismatched == {'run_alt000000001'}
    assert any('run_alt000000001.error' in line for line in result.deviations)


def test_orphan_mismatched_and_unreadable_runs_fail_individually(bestand, repo):
    """Fehlende Simulation, abweichende Kennung und kaputtes JSON brechen den
    Lauf nicht ab."""
    _write_manifest(
        bestand,
        'run_waise0000001',
        {'run_id': 'run_waise0000001', 'linked_ids': {'simulation_id': 'sim_geloescht000'}},
    )
    _write_manifest(bestand, 'run_umbenannt001', {'run_id': 'run_anderer000001'})
    _write_manifest(bestand, 'run_kaputt000001', '{kein json')

    summary = skript.migrate(bestand, repository=repo)

    assert summary.inserted == 3
    assert summary.failed == 3
    assert any('run_waise0000001' in line and 'sim_geloescht000' in line for line in summary.failures)
    assert any('run_umbenannt001' in line for line in summary.failures)
    assert any('run_kaputt000001' in line for line in summary.failures)
    assert repo.get('run_anderer000001') is None


def test_cli_exit_codes(bestand, repo, monkeypatch, capsys):
    monkeypatch.setattr(skript, 'PostgresRunRepository', lambda: repo)

    assert skript.main(['--registry-dir', str(bestand), '--dry-run']) == 0
    assert 'Scanned:   3' in capsys.readouterr().out
    assert skript.main(['--registry-dir', str(bestand), '--verify']) == 1
    assert skript.main(['--registry-dir', str(bestand)]) == 0
    out = capsys.readouterr().out
    assert 'Inserted:  3' in out and 'Failed:    0' in out
    assert skript.main(['--registry-dir', str(bestand), '--verify']) == 0
    assert 'Verified:  3/3' in capsys.readouterr().out
