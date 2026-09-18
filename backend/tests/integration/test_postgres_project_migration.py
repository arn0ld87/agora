"""Die Datenmigration muss nachweislich nichts verlieren (§11, PR 6).

„Verlustfrei" ist die Zusage des Slices, und sie ist nur dann etwas wert, wenn
sie gegen echte Dateien und eine echte Datenbank geprüft wird. Der Kern ist
deshalb kein Stichprobenvergleich, sondern ``--verify``: es stellt jedes Feld
jedes Projekts gegenüber.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

from app.contracts import Project, ProjectStatus
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.session import Database
from scripts import migrate_projects_to_postgres as skript

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    command.upgrade(config, 'head')
    database = Database(postgres_database_url)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresProjectRepository:
    """Wird dem Skript ausdruecklich mitgegeben.

    ``get_database()`` liest ``Config.DATABASE_URL``, das beim Import
    feststeht — eine Env-Variable zu setzen erreicht es nicht. Statt am
    globalen Zustand zu drehen, nimmt das Skript ein Repository entgegen.
    """
    return PostgresProjectRepository(database=migrated_db)


def _write_project(root: Path, project: Project) -> Path:
    verzeichnis = root / project.project_id
    (verzeichnis / 'files').mkdir(parents=True)
    # Ein Artefakt daneben, um zu belegen, dass es unberuehrt bleibt.
    (verzeichnis / 'files' / 'quelle.pdf').write_text('Inhalt')
    (verzeichnis / 'extracted_text.txt').write_text('Text')
    meta = verzeichnis / 'project.json'
    with open(meta, 'w', encoding='utf-8') as handle:
        json.dump(project.to_dict(), handle, ensure_ascii=False, indent=2)
    return meta


def _bestand(root: Path) -> list[Project]:
    """Drei Projekte: voll belegt, minimal, und eines mit Sonderzeichen."""
    projekte = [
        Project(
            project_id='proj_a1b2c3d4e5f6',
            name='Vollstaendig',
            status=ProjectStatus.GRAPH_COMPLETED,
            created_at='2026-09-01T10:00:00',
            updated_at='2026-09-02T11:30:00',
            files=[{'saved_filename': 'ab12.pdf', 'size': 20481}],
            total_text_length=4096,
            ontology={'entities': ['Behoerde']},
            analysis_summary='Zusammenfassung',
            graph_id='graph_9',
            graph_build_task_id='task_7',
            simulation_requirement='Wie reagieren Anwohner?',
            chunk_size=500,
            chunk_overlap=50,
            llm_model='qwen3',
            llm_provider={'provider': 'ollama', 'api_key_set': True},
            llm_profile_id='profile_3',
            ai_model_ref={'connection_id': 'conn_1'},
            error=None,
        ),
        Project(
            project_id='proj_000000000001',
            name='Minimal',
            created_at='2026-08-01T09:00:00',
            updated_at='2026-08-01T09:00:00',
        ),
        Project(
            project_id='proj_ffffffffffff',
            name='Umlaute und „Anführungszeichen"',
            status=ProjectStatus.FAILED,
            created_at='2026-07-01T08:00:00',
            updated_at='2026-07-01T08:00:00',
            error='Abbruch: Gebäude-Analyse fehlgeschlagen',
        ),
    ]
    for projekt in projekte:
        _write_project(root, projekt)
    return projekte


def test_migration_transfers_every_field_of_every_project(repo, tmp_path):
    root = tmp_path / 'projects'
    root.mkdir()
    erwartet = _bestand(root)

    zaehler = skript.migrate(root, repository=repo)

    assert zaehler == {'gefunden': 3, 'uebertragen': 3, 'uebersprungen': 0}
    # Der eigentliche Nachweis: feldweiser Vergleich beider Seiten.
    assert skript.verify(root, repository=repo) == []

    for projekt in erwartet:
        gespeichert = repo.get(projekt.project_id)
        assert gespeichert is not None
        assert gespeichert.to_dict() == projekt.to_dict()


def test_migration_leaves_the_filesystem_untouched(repo, tmp_path):
    """Die Dateiablage bleibt die Wahrheit und der Rueckweg."""
    root = tmp_path / 'projects'
    root.mkdir()
    _bestand(root)

    vorher = {
        pfad: pfad.read_bytes()
        for pfad in sorted(root.rglob('*'))
        if pfad.is_file()
    }

    skript.migrate(root, repository=repo)

    nachher = {
        pfad: pfad.read_bytes()
        for pfad in sorted(root.rglob('*'))
        if pfad.is_file()
    }
    assert nachher == vorher


def test_a_second_run_changes_nothing(repo, tmp_path):
    """Idempotent: nach einem Abbruch darf ein zweiter Lauf weitermachen,
    ohne einen inzwischen geaenderten Datensatz zu ueberschreiben."""
    root = tmp_path / 'projects'
    root.mkdir()
    _bestand(root)

    skript.migrate(root, repository=repo)
    zweiter = skript.migrate(root, repository=repo)

    assert zweiter == {'gefunden': 3, 'uebertragen': 0, 'uebersprungen': 3}
    assert skript.verify(root, repository=repo) == []


def test_dry_run_writes_nothing(repo, tmp_path):
    root = tmp_path / 'projects'
    root.mkdir()
    _bestand(root)

    zaehler = skript.migrate(root, dry_run=True, repository=repo)

    assert zaehler == {'gefunden': 3, 'uebertragen': 0, 'uebersprungen': 0}
    # Nichts uebertragen heisst: verify meldet alle drei als fehlend.
    assert len(skript.verify(root, repository=repo)) == 3


def test_verify_reports_a_field_that_drifted(repo, tmp_path):
    """``--verify`` muss eine Abweichung auch wirklich finden."""
    root = tmp_path / 'projects'
    root.mkdir()
    _bestand(root)
    skript.migrate(root, repository=repo)

    projekt = repo.get('proj_a1b2c3d4e5f6')
    projekt.name = 'Nachtraeglich geaendert'
    repo.save(projekt)

    abweichungen = skript.verify(root, repository=repo)

    assert any('.name:' in zeile for zeile in abweichungen)


def test_a_directory_without_a_record_is_skipped(repo, tmp_path):
    """Ein halb angelegtes Projekt darf die Migration nicht abbrechen."""
    root = tmp_path / 'projects'
    root.mkdir()
    _bestand(root)
    (root / 'proj_nurverzeichnis').mkdir()

    zaehler = skript.migrate(root, repository=repo)

    assert zaehler['gefunden'] == 3
