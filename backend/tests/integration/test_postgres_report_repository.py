"""Der PostgreSQL-Adapter muss dieselben Zusagen halten wie der Dateiadapter.

Referenz ist ``backend/tests/contracts/test_report_repository_contract.py``;
die Zusagen werden hier gegen eine echte PostgreSQL-Instanz nachgezogen.

Schwerpunkte: Roundtrip über **alle** Vertragsfelder, Ablageschlüssel ≠
``report_id`` (Altbestand), Fremdschlüssel auf ``agora.simulations``,
Löschen über ``ReportManager`` und ein Export, der mit beiden Backends
byte-gleich ausfällt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text

from app.config import Config
from app.contracts import Project
from app.contracts.report_record_contract import ReportRecord
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.repositories.report_repository import (
    PostgresReportRepository,
    ReportSimulationMissing,
)
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
)
from app.infrastructure.postgres.session import Database
from app.repositories.report_repository import ReportRepository

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_ID = 'proj_aaaabbbbcccc'
SIM_A = 'sim_aaaa00000001'
SIM_B = 'sim_bbbb00000001'


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank mit ``alembic upgrade head``, einem Projekt und zwei
    Simulationen."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    command.upgrade(_alembic_config(), 'head')
    database = Database(postgres_database_url)
    PostgresProjectRepository(database=database).add_existing(
        Project(
            project_id=PROJECT_ID,
            name='Projekt',
            created_at='2026-09-01T10:00:00',
            updated_at='2026-09-01T10:00:00',
        )
    )
    simulations = PostgresSimulationRepository(database=database)
    for simulation_id in (SIM_A, SIM_B):
        simulations.add_existing(
            SimulationRecord(
                simulation_id=simulation_id,
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
    return PostgresReportRepository(database=migrated_db)


def _record(report_id: str, simulation_id: str = SIM_A, **overrides: Any) -> ReportRecord:
    base: dict[str, Any] = {
        'report_id': report_id,
        'simulation_id': simulation_id,
        'graph_id': 'graph_1',
        'simulation_requirement': 'Frage',
        'status': 'completed',
        'created_at': '2026-09-02T10:00:00',
    }
    base.update(overrides)
    return ReportRecord(**base)


def _full_record() -> ReportRecord:
    """Jedes Vertragsfeld abweichend vom Vorgabewert belegt."""
    return ReportRecord(
        report_id='report_voll000001',
        simulation_id=SIM_A,
        graph_id='graph_äöü',
        simulation_requirement='Wie reagieren "Stakeholder" auf X?',
        status='completed',
        outline={
            'title': 'Titel',
            'summary': 'Zusammenfassung',
            'sections': [{'title': 'Abschnitt', 'content': 'Inhalt', 'description': 'Beschreibung'}],
        },
        markdown_content='# Titel\n\nText mit Umlauten: äöüß',
        missing_sections=['Anhang'],
        created_at='2026-09-02T08:15:00.123456',
        completed_at='2026-09-02T09:00:00',
        error='Fehlertext',
        has_evidence=True,
        evidence_sections=3,
        simulation_snapshot={'status': 'completed', 'current_round': 5},
        run_degradations=[{'kind': 'low_interview_coverage', 'detail': 'x'}],
    )


# -- Port und Roundtrip ------------------------------------------------------


def test_adapter_satisfies_the_port(repo):
    assert isinstance(repo, ReportRepository)


def test_roundtrip_over_every_contract_field(repo):
    record = _full_record()
    repo.save(record)

    loaded = repo.get(record.report_id)

    assert loaded is not None
    assert loaded.to_dict() == record.to_dict()
    assert set(record.to_dict()) == set(ReportRecord.model_fields)


def test_save_returns_record_creates_then_overwrites(repo):
    record = _record('report_upd000001', status='generating')
    assert repo.save(record) is record

    record.status = 'completed'
    record.markdown_content = 'fertig'
    repo.save(record)

    loaded = repo.get('report_upd000001')
    assert loaded is not None
    assert (loaded.status, loaded.markdown_content) == ('completed', 'fertig')
    assert repo.list_ids() == ['report_upd000001']


def test_get_returns_none_for_unknown_key(repo):
    assert repo.get('report_gibtesnicht') is None


def test_list_and_filter_by_simulation(repo):
    repo.save(_record('report_a00000001', simulation_id=SIM_A))
    repo.save(_record('report_b00000001', simulation_id=SIM_B))

    assert {r.report_id for r in repo.list()} == {'report_a00000001', 'report_b00000001'}
    assert [r.report_id for r in repo.list(simulation_id=SIM_B)] == ['report_b00000001']
    assert repo.list(simulation_id='sim_gibtesnicht0') == []
    assert repo.list_ids() == ['report_a00000001', 'report_b00000001']


def test_legacy_key_differs_from_report_id(repo):
    """Altbestand: Ordner ``report_deepseek_<hex>``, Manifest ``report_<hex>``.
    ``get`` und ``list_ids`` arbeiten mit dem Schlüssel, nicht mit der ID."""
    record = _record('report_abc123')
    assert repo.add_existing('report_deepseek_abc123', record) is True

    assert repo.list_ids() == ['report_deepseek_abc123']
    loaded = repo.get('report_deepseek_abc123')
    assert loaded is not None and loaded.report_id == 'report_abc123'
    assert repo.get('report_abc123') is None


def test_save_under_report_id_updates_the_legacy_row(repo):
    """``save`` kennt nur die ``report_id``. Liegt der Report unter einem
    abweichenden Ablageschlüssel, muss dieselbe Zeile aktualisiert werden —
    sonst entstünde ein Duplikat (CodeRabbit-Review auf #1607)."""
    assert repo.add_existing('report_deepseek_abc123', _record('report_abc123'))

    repo.save(_record('report_abc123', status='failed'))

    assert repo.list_ids() == ['report_deepseek_abc123']
    loaded = repo.get('report_deepseek_abc123')
    assert loaded is not None and loaded.status == 'failed'
    assert repo.get('report_abc123') is None


def test_unreadable_row_does_not_break_the_list(repo, migrated_db):
    repo.save(_record('report_gut0000001'))
    with migrated_db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.reports (id, report_id, status, payload) '
                "VALUES ('report_kaputt001', 'report_kaputt001', 'completed', "
                '\'{"report_id": "report_kaputt001"}\'::jsonb)'
            )
        )

    assert repo.get('report_kaputt001') is None
    assert [r.report_id for r in repo.list()] == ['report_gut0000001']


def test_delete_removes_only_the_row(repo):
    repo.save(_record('report_weg000001'))

    assert repo.delete('report_weg000001') is True
    assert repo.get('report_weg000001') is None
    assert repo.delete('report_weg000001') is False


# -- Fremdschlüssel auf agora.simulations --------------------------------------


def test_new_report_with_unknown_simulation_is_rejected_not_dropped(repo):
    with pytest.raises(ReportSimulationMissing):
        repo.save(_record('report_waise00001', simulation_id='sim_gibtesnicht0'))
    with pytest.raises(ReportSimulationMissing):
        repo.add_existing(
            'report_waise00002', _record('report_waise00002', simulation_id='sim_gibtesnicht0')
        )
    assert repo.list_ids() == []


def test_deleting_the_simulation_keeps_the_report_readable(repo, migrated_db):
    """``ON DELETE SET NULL``: der Datensatz im ``payload`` bleibt unverändert,
    ``list(simulation_id=...)`` findet ihn weiter — wie der Dateiadapter."""
    repo.save(_record('report_haengt001', simulation_id=SIM_B))
    with migrated_db.session() as session:
        session.execute(text(f"DELETE FROM agora.simulations WHERE id = '{SIM_B}'"))
        stored = session.execute(
            text("SELECT simulation_id FROM agora.reports WHERE id = 'report_haengt001'")
        ).scalar_one()
    assert stored is None

    loaded = repo.get('report_haengt001')
    assert loaded is not None and loaded.simulation_id == SIM_B
    assert [r.report_id for r in repo.list(simulation_id=SIM_B)] == ['report_haengt001']


def test_report_in_progress_still_saves_after_simulation_deletion(repo, migrated_db):
    """Die Report-Erzeugung hält das ``Report``-Objekt über den Lauf im
    Speicher. Wird die Simulation währenddessen gelöscht, darf der nächste
    ``save`` nicht scheitern (Lehre aus dem Codex-Review auf #1598)."""
    report = _record('report_laeuft001', simulation_id=SIM_B, status='generating')
    repo.save(report)
    with migrated_db.session() as session:
        session.execute(text(f"DELETE FROM agora.simulations WHERE id = '{SIM_B}'"))

    report.status = 'completed'
    repo.save(report)

    loaded = repo.get('report_laeuft001')
    assert loaded is not None and loaded.status == 'completed'


def test_add_existing_is_idempotent_and_does_not_overwrite(repo):
    record = _full_record()
    assert repo.add_existing(record.report_id, record) is True

    changed = _full_record()
    changed.status = 'failed'
    assert repo.add_existing(record.report_id, changed) is False

    loaded = repo.get(record.report_id)
    assert loaded is not None and loaded.status == 'completed'


def test_add_existing_counts_a_detached_report_as_existing(repo, migrated_db):
    record = _record('report_wiederh01', simulation_id=SIM_B)
    assert repo.add_existing(record.report_id, record) is True
    with migrated_db.session() as session:
        session.execute(text(f"DELETE FROM agora.simulations WHERE id = '{SIM_B}'"))

    assert repo.add_existing(record.report_id, record) is False


@pytest.mark.parametrize('payload', ['1', 'true', '"text"', '[1, 2]', 'null'])
def test_non_object_payload_counts_as_unreadable(repo, migrated_db, payload):
    repo.save(_record('report_gut0000002'))
    with migrated_db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.reports (id, report_id, status, payload) '
                "VALUES ('report_skalar001', 'report_skalar001', 'completed', "
                f"'{payload}'::jsonb)"
            )
        )

    assert repo.get('report_skalar001') is None
    assert [r.report_id for r in repo.list()] == ['report_gut0000002']


# -- Alembic ---------------------------------------------------------------


def test_the_migration_can_be_taken_back(postgres_database_url, monkeypatch):
    """Der Rückweg aus dem Runbook muss laufen: ``downgrade 3f9b2d7e6a41``
    entfernt nur ``agora.reports``; Modell und Migration bleiben deckungsgleich."""
    from sqlalchemy import create_engine, inspect

    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = _alembic_config()

    command.upgrade(config, 'head')
    command.check(config)
    engine = create_engine(postgres_database_url)
    try:
        assert 'reports' in inspect(engine).get_table_names(schema='agora')

        command.downgrade(config, '3f9b2d7e6a41')
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'reports' not in tabellen
        assert 'runs' in tabellen

        command.upgrade(config, 'head')
        assert 'reports' in inspect(engine).get_table_names(schema='agora')
    finally:
        engine.dispose()


# -- ReportManager und Export mit beiden Backends ----------------------------


@pytest.fixture
def report_on_disk(tmp_path, monkeypatch):
    """Ein Report im Dateiformat: ``meta.json`` plus Inhalte daneben."""
    from app.services.report_agent import ReportManager

    reports_dir = tmp_path / 'reports'
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(reports_dir))
    # Snapshot und Degradations in der Form, die der Export-Vertrag prüft.
    record = _full_record()
    record.simulation_snapshot = {
        'rounds_completed': 45,
        'total_rounds': 48,
        'simulation_running': False,
        'simulation_status': 'failed',
        'captured_at': '2026-09-02T09:00:00',
    }
    from app.services.report_prompts import DEFAULT_REPORT_SECTIONS

    record.outline = {
        'title': 'Titel',
        'summary': 'Zusammenfassung',
        'sections': [
            {'title': title, 'content': description, 'description': description}
            for title, description in DEFAULT_REPORT_SECTIONS
        ],
    }
    record.run_degradations = [
        {
            'component': 'simulation',
            'reason': 'incomplete_rounds',
            'detail': '45 von 48 Runden',
            'severity': 'warning',
        }
    ]
    folder = reports_dir / record.report_id
    folder.mkdir(parents=True)
    (folder / 'meta.json').write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8'
    )
    (folder / 'evidence-map.json').write_text('{"sections": []}', encoding='utf-8')
    return record, reports_dir


def _use_postgres(monkeypatch, database: Database) -> None:
    from app.infrastructure.postgres import session as session_module

    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'postgres')
    monkeypatch.setattr(session_module, '_database', database)


def _export_bytes(report_id: str) -> bytes:
    from app.services.report_agent import ReportManager
    from app.services.report_export import ReportExportService

    report = ReportManager.get_report(report_id)
    assert report is not None
    envelope = ReportExportService.build_export_envelope(
        report, ReportManager.get_evidence_map(report_id)
    )
    # ``exported_at`` ist die Uhrzeit des Exports, kein Report-Inhalt.
    return envelope.model_dump_json(exclude={'exported_at'}).encode('utf-8')


def test_report_export_is_byte_identical_with_both_backends(
    report_on_disk, repo, migrated_db, monkeypatch
):
    record, reports_dir = report_on_disk
    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'file')
    from_file = _export_bytes(record.report_id)

    assert repo.add_existing(record.report_id, record) is True
    (reports_dir / record.report_id / 'meta.json').unlink()
    _use_postgres(monkeypatch, migrated_db)
    from_postgres = _export_bytes(record.report_id)

    assert from_postgres == from_file


def test_manager_delete_removes_row_and_contents_with_postgres(
    report_on_disk, repo, migrated_db, monkeypatch
):
    """Ohne ``delete`` am Port bliebe die Zeile stehen, und der gelöschte
    Report tauchte in jeder Liste wieder auf."""
    from app.services.report_agent import ReportManager

    record, reports_dir = report_on_disk
    repo.add_existing(record.report_id, record)
    _use_postgres(monkeypatch, migrated_db)

    assert ReportManager.delete_report(record.report_id) is True

    assert repo.get(record.report_id) is None
    assert not (reports_dir / record.report_id).exists()
    assert ReportManager.list_reports() == []


def test_manager_save_and_list_go_through_postgres(report_on_disk, repo, migrated_db, monkeypatch):
    from app.models.report import Report, ReportStatus
    from app.services.report_agent import ReportManager

    _, reports_dir = report_on_disk
    _use_postgres(monkeypatch, migrated_db)
    report = Report(
        report_id='report_neu0000001',
        simulation_id=SIM_B,
        graph_id='graph_1',
        simulation_requirement='Frage',
        status=ReportStatus.PENDING,
        created_at='2026-09-03T10:00:00',
    )

    ReportManager.save_report(report)

    assert not (reports_dir / 'report_neu0000001' / 'meta.json').exists()
    stored = repo.get('report_neu0000001')
    assert stored is not None and stored.simulation_id == SIM_B
    assert ReportManager.get_report_by_simulation(SIM_B).report_id == 'report_neu0000001'


def test_manager_delete_removes_the_flat_legacy_file_with_postgres(
    tmp_path, repo, migrated_db, monkeypatch
):
    """Ein Report im Flachformat ``<id>.json`` lag vor der Migration nur als
    Datei vor. Nach dem Löschen im Postgres-Modus darf sie nicht liegen
    bleiben, sonst taucht er beim Rückweg auf ``file`` wieder auf
    (CodeRabbit-Review auf #1607)."""
    from app.services.report_agent import ReportManager

    reports_dir = tmp_path / 'reports'
    reports_dir.mkdir()
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(reports_dir))
    record = _record('report_flach000001')
    flat = reports_dir / 'report_flach000001.json'
    flat.write_text(json.dumps(record.to_dict()), encoding='utf-8')
    assert repo.add_existing('report_flach000001', record)
    _use_postgres(monkeypatch, migrated_db)

    assert ReportManager.delete_report('report_flach000001') is True

    assert not flat.exists()
    assert repo.get('report_flach000001') is None
