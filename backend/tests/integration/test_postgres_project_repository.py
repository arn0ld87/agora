"""Der PostgreSQL-Adapter muss dieselben Zusagen halten wie der Dateiadapter.

Die Referenz für diese Zusagen ist
``backend/tests/contracts/test_project_repository_contract.py``; sie werden
hier gegen eine echte PostgreSQL-Instanz nachgezogen, weil ein Adapter, der nur
gegen Doubles geprüft ist, über seine Datenbank nichts beweist.

Der wichtigste Test ist der Roundtrip über **alle** Vertragsfelder: der
Spaltenschnitt trennt sieben Kernspalten von einem ``payload``, und genau dort
könnte ein Feld verlorengehen, ohne dass es jemandem auffällt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.contracts import Project, ProjectStatus
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
    ProjectNotStored,
)
from app.infrastructure.postgres.session import Database

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Eine Wegwerf-Datenbank mit ``alembic upgrade head``.

    Gleiches Vorgehen wie in ``test_postgres_llm_profile_repository.py``.
    """
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = Config(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    command.upgrade(config, 'head')
    database = Database(postgres_database_url)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresProjectRepository:
    return PostgresProjectRepository(database=migrated_db)


def _full_project(project_id: str = 'proj_a1b2c3d4e5f6') -> Project:
    """Ein Projekt mit jedem Vertragsfeld belegt — auch den optionalen."""
    return Project(
        project_id=project_id,
        name='Testprojekt',
        status=ProjectStatus.GRAPH_COMPLETED,
        created_at='2026-09-01T10:00:00',
        updated_at='2026-09-02T11:30:00',
        files=[
            {
                'original_filename': 'quelle.pdf',
                'saved_filename': 'ab12cd34.pdf',
                'path': '/uploads/projects/proj_a1b2c3d4e5f6/files/ab12cd34.pdf',
                'size': 20481,
            }
        ],
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
        ai_model_ref={'connection_id': 'conn_1', 'model': 'qwen3'},
        error=None,
    )


def test_every_contract_field_survives_the_roundtrip(repo):
    """Kein Feld darf zwischen Kernspalten und payload verlorengehen.

    Verglichen wird ``to_dict()`` gegen ``to_dict()``, also die
    Serialisierungsform, die auch in der Datei stünde — bis auf
    ``updated_at``, das ``save`` bestimmungsgemäß neu stempelt.
    """
    original = _full_project()
    created = repo.create('Platzhalter')

    stored = original.model_copy(update={'project_id': created.project_id})
    repo.save(stored)

    reloaded = repo.get(created.project_id)
    assert reloaded is not None

    erwartet = stored.to_dict()
    tatsaechlich = reloaded.to_dict()
    erwartet.pop('updated_at')
    tatsaechlich.pop('updated_at')

    assert tatsaechlich == erwartet


def test_the_split_puts_nothing_in_payload_that_has_its_own_column(repo):
    """Kernspalten und payload duerfen sich nicht ueberschneiden."""
    created = repo.create('Mit Nutzlast')

    with repo.db.session() as session:
        payload = session.execute(
            text('SELECT payload FROM agora.projects WHERE id = :id'),
            {'id': created.project_id},
        ).scalar_one()

    for column in ('project_id', 'name', 'status', 'graph_id',
                   'llm_profile_id', 'created_at', 'updated_at'):
        assert column not in payload


def test_create_uses_the_id_format_the_artifact_paths_depend_on(repo):
    project = repo.create('Neu')

    assert project.project_id.startswith('proj_')
    assert len(project.project_id) == len('proj_') + 12
    int(project.project_id.removeprefix('proj_'), 16)


def test_get_returns_none_for_an_unknown_id(repo):
    assert repo.get('proj_gibtesnicht') is None


def test_save_does_not_invent_a_project_that_was_never_created(repo):
    """Wie beim Dateiadapter: Speichern legt kein Projekt an.

    Dort scheitert es am fehlenden Verzeichnis, hier an der fehlenden Zeile.
    Der Fehlertyp unterscheidet sich, die Zusage nicht.
    """
    with pytest.raises(ProjectNotStored):
        repo.save(Project(project_id='proj_niemalsangelegt'))


def test_save_advances_updated_at_and_leaves_created_at_alone(repo):
    created = repo.create('Vorher')
    created_at = created.created_at

    created.name = 'Nachher'
    repo.save(created)

    reloaded = repo.get(created.project_id)
    assert reloaded.name == 'Nachher'
    assert reloaded.created_at == created_at
    assert reloaded.updated_at >= created_at


def test_list_returns_the_newest_first_and_caps_after_sorting(repo):
    for stamp in ('2026-01-01', '2026-06-01', '2026-03-01'):
        project = repo.create(f'Projekt {stamp}')
        project.created_at = f'{stamp}T00:00:00'
        repo.save(project)

    alle = repo.list()
    assert [p.created_at[:10] for p in alle] == [
        '2026-06-01',
        '2026-03-01',
        '2026-01-01',
    ]

    assert [p.created_at[:10] for p in repo.list(limit=1)] == ['2026-06-01']


def test_list_is_empty_and_does_not_raise_when_nothing_exists(repo):
    assert repo.list() == []


def test_one_unreadable_row_does_not_take_down_the_whole_list(repo, monkeypatch):
    """Dieselbe Zusage wie beim Dateiadapter.

    Eine Zeile, deren ``payload`` nicht mehr zum Vertrag passt — etwa nach
    einer Vertragsaenderung oder einem Eingriff von Hand —, darf nicht die
    gesamte Projektuebersicht abschalten.
    """
    intakt = repo.create('Intakt')
    kaputt = repo.create('Wird beschaedigt')

    # ``files`` muss eine Liste sein; hier wird daraus eine Zahl.
    with repo.db.session() as session:
        session.execute(
            text(
                "UPDATE agora.projects SET payload = jsonb_set("
                "payload, '{files}', '42'::jsonb) WHERE id = :id"
            ),
            {'id': kaputt.project_id},
        )

    from app.infrastructure.postgres.repositories import project_repository as modul

    warnungen: list[str] = []
    monkeypatch.setattr(
        modul.logger,
        'warning',
        lambda nachricht, *args: warnungen.append(nachricht % args),
    )

    gelistet = repo.list()

    assert [p.project_id for p in gelistet] == [intakt.project_id]
    # Uebersprungen heisst nicht verschwiegen.
    assert any(kaputt.project_id in eintrag for eintrag in warnungen)


def test_a_direct_get_on_an_unreadable_row_still_raises(repo):
    """``get`` bleibt laut — wer dieses Projekt anfordert, soll den Fehler sehen."""
    kaputt = repo.create('Wird beschaedigt')

    with repo.db.session() as session:
        session.execute(
            text(
                "UPDATE agora.projects SET payload = jsonb_set("
                "payload, '{files}', '42'::jsonb) WHERE id = :id"
            ),
            {'id': kaputt.project_id},
        )

    with pytest.raises(ValueError):
        repo.get(kaputt.project_id)


def test_a_negative_limit_returns_nothing_instead_of_failing(repo):
    """SQL wuerde ein negatives LIMIT ablehnen, ein Python-Slice nicht.

    Beide Adapter liefern jetzt dasselbe: nichts.
    """
    repo.create('Egal')

    assert repo.list(limit=-1) == []


def test_delete_reports_whether_there_was_a_row(repo):
    created = repo.create('Weg damit')

    assert repo.delete(created.project_id) is True
    assert repo.delete(created.project_id) is False
    assert repo.get(created.project_id) is None


def test_an_unknown_status_is_rejected_by_the_database(repo):
    """Der Check-Constraint spiegelt das Vertragsenum.

    Der Vertrag lehnt einen unbekannten Status bereits ab; die Tabelle soll
    sich nicht darauf verlassen müssen.
    """
    created = repo.create('Status')

    with pytest.raises(Exception):  # noqa: B017 — DB-Fehlertyp ist Treibersache
        with repo.db.session() as session:
            session.execute(
                text('UPDATE agora.projects SET status = :s WHERE id = :id'),
                {'s': 'voellig_neuer_status', 'id': created.project_id},
            )


def test_the_migration_can_be_taken_back(postgres_database_url, monkeypatch):
    """Der Rueckweg muss laufen, nicht nur behauptet sein.

    Das Vorbild aus PR 4 hat diesen Test; ohne ihn waere die Zusage im Runbook
    („Das Schema laesst sich zuruecknehmen") ungeprueft.
    """
    from sqlalchemy import create_engine, inspect

    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = Config(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))

    command.upgrade(config, 'head')
    engine = create_engine(postgres_database_url)
    try:
        assert 'projects' in inspect(engine).get_table_names(schema='agora')

        # Ausdruecklich auf die Revision vor den Projekten, nicht ``-1``:
        # seit #1585 liegt ``agora.simulations`` darueber.
        command.downgrade(config, 'b5d2c0a41f7e')
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'projects' not in tabellen
        # Die Revision davor bleibt stehen — sie gehoert einem anderen PR.
        assert 'llm_profiles' in tabellen

        command.upgrade(config, 'head')
        assert 'projects' in inspect(engine).get_table_names(schema='agora')
    finally:
        engine.dispose()


def test_the_table_carries_no_workspace_or_auth_column(repo):
    """Multi-User ist eine eigene, freizugebende Phase."""
    with repo.db.session() as session:
        spalten = {
            row[0]
            for row in session.execute(
                text(
                    'SELECT column_name FROM information_schema.columns '
                    "WHERE table_schema = 'agora' AND table_name = 'projects'"
                )
            )
        }

    assert 'workspace_id' not in spalten
    assert not {s for s in spalten if 'auth' in s or 'user' in s}

    # Und der Primaerschluessel bleibt text, weil er ein Verzeichnisname ist.
    with repo.db.session() as session:
        typ = session.execute(
            text(
                'SELECT data_type FROM information_schema.columns '
                "WHERE table_schema = 'agora' AND table_name = 'projects' "
                "AND column_name = 'id'"
            )
        ).scalar_one()

    assert typ == 'text'
