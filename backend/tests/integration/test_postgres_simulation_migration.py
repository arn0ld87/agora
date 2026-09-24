"""Die Simulations-Datenmigration muss nachweislich nichts verlieren (§11, PR 7).

Fixture → ``migrate`` → ``verify``: jedes Feld jeder Simulation wird
gegenübergestellt, Kennungen und Zeitstempel bleiben identisch, die Quelle
bleibt byteweise unverändert, ein zweiter Lauf schreibt nichts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

from app.contracts import Project
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
)
from app.infrastructure.postgres.session import Database
from scripts import migrate_simulations_to_postgres as skript

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_ID = 'proj_112233445566'


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
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresSimulationRepository:
    """Wird dem Skript mitgegeben, statt am globalen ``Config.DATABASE_URL`` zu drehen."""
    return PostgresSimulationRepository(database=migrated_db)


def _write_state(root: Path, simulation_id: str, data: dict) -> None:
    directory = root / simulation_id
    directory.mkdir(parents=True)
    # Ein Laufzeit-Artefakt daneben, um zu belegen, dass es unberührt bleibt.
    (directory / 'simulation_config.json').write_text('{"rounds": 3}')
    (directory / 'state.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
    )


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


@pytest.fixture
def bestand(tmp_path: Path) -> Path:
    """Drei Simulationen: voll belegt, Zweig, Altbestand mit ``null``-Feldern."""
    root = tmp_path / 'simulations'
    voll = SimulationRecord(
        simulation_id='sim_voll00000001',
        project_id=PROJECT_ID,
        graph_id='graph_1',
        status='completed',
        entities_count=5,
        entity_types=['Person', 'Behörde'],
        config_generated=True,
        config_reasoning='Begründung',
        current_round=7,
        created_at='2026-09-02T08:15:00.123456',
        updated_at='2026-09-02T09:00:00',
        root_simulation_id='sim_voll00000001',
        persona_floor=20,
    )
    zweig = SimulationRecord(
        simulation_id='sim_zweig0000001',
        project_id=PROJECT_ID,
        graph_id='graph_1',
        created_at='2026-09-03T10:00:00',
        updated_at='2026-09-03T11:00:00',
        source_simulation_id='sim_voll00000001',
        root_simulation_id='sim_voll00000001',
        branch_name='Variante B',
        branch_depth=1,
    )
    _write_state(root, voll.simulation_id, voll.to_dict())
    _write_state(root, zweig.simulation_id, zweig.to_dict())
    _write_state(
        root,
        'sim_alt000000001',
        {
            'project_id': PROJECT_ID,
            'status': 'ready',
            'branch_depth': None,
            'entity_types': None,
            'created_at': '2026-08-01T00:00:00',
            'updated_at': '2026-08-01T00:00:00',
        },
    )
    # Ein Verzeichnis ohne state.json ist keine Simulation.
    (root / 'sim_halb00000001').mkdir()
    return root


def test_migrate_then_verify_is_lossless(bestand, repo):
    vorher = _fingerprint(bestand)

    summary = skript.migrate(bestand, repository=repo)

    assert (summary.scanned, summary.inserted, summary.skipped, summary.failed) == (3, 3, 0, 0)
    result = skript.verify(bestand, repository=repo)
    assert result.deviations == []
    assert (result.verified, result.checked) == (3, 3)
    loaded = repo.get('sim_voll00000001')
    assert loaded is not None
    assert loaded.created_at == '2026-09-02T08:15:00.123456'
    assert loaded.updated_at == '2026-09-02T09:00:00'
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
    assert repo.list() == []


def test_verify_reports_a_changed_field(bestand, repo):
    skript.migrate(bestand, repository=repo)
    record = repo.get('sim_zweig0000001')
    assert record is not None
    record.branch_name = 'manipuliert'
    repo.save(record)

    result = skript.verify(bestand, repository=repo)

    assert result.mismatched == {'sim_zweig0000001'}
    assert any('sim_zweig0000001.branch_name' in line for line in result.deviations)


def test_orphan_and_unreadable_simulations_fail_individually(bestand, repo):
    """Fehlendes Projekt und kaputte state.json brechen den Lauf nicht ab."""
    _write_state(
        bestand,
        'sim_waise0000001',
        {'project_id': 'proj_geloescht00', 'created_at': 'x', 'updated_at': 'x'},
    )
    kaputt = bestand / 'sim_kaputt000001'
    kaputt.mkdir()
    (kaputt / 'state.json').write_text('{kein json')

    summary = skript.migrate(bestand, repository=repo)

    assert summary.inserted == 3
    assert summary.failed == 2
    assert any('sim_waise0000001' in line for line in summary.failures)
    assert any('sim_kaputt000001' in line for line in summary.failures)


def test_cli_exit_codes(bestand, repo, monkeypatch, capsys):
    monkeypatch.setattr(skript, 'PostgresSimulationRepository', lambda: repo)

    assert skript.main(['--simulations-dir', str(bestand), '--dry-run']) == 0
    assert 'Scanned:   3' in capsys.readouterr().out
    assert skript.main(['--simulations-dir', str(bestand), '--verify']) == 1
    assert skript.main(['--simulations-dir', str(bestand)]) == 0
    assert skript.main(['--simulations-dir', str(bestand), '--verify']) == 0
    assert 'Verified:  3/3' in capsys.readouterr().out
