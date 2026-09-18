"""Contract-Tests fuer ``app.repositories.project_repository`` (PR 6).

Prueft die Invarianten, die der Port in seinen Docstrings festschreibt, gegen
``FileProjectRepository`` — den einen heutigen Adapter. Der PostgreSQL-Adapter
aus dem zweiten Teil von PR 6 muss dieselben Zusagen einhalten; diese Datei ist
die Referenz dafuer.

Ohne sie waere die Reihenfolge von ``list``, die ``None``-Zusage von ``get``
und die ``bool``-Bedeutung von ``delete`` nur Prosa im Docstring: ein zweiter
Adapter mit ``ORDER BY created_at ASC`` ginge durch, ohne dass ein Test
anschlaegt.

Jede Instanz bekommt ihr eigenes ``tmp_path`` als Ablageort, damit kein Test
in das echte Upload-Verzeichnis schreibt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Config
from app.repositories import project_repository as repository_module
from app.repositories.project_repository import (
    ProjectBackendUnavailable,
    ProjectRepository,
    get_project_repository,
)
from app.services import file_project_store as store_module
from app.services.file_project_store import FileProjectRepository


@pytest.fixture
def repo(tmp_path: Path) -> FileProjectRepository:
    """Isolierter Adapter — jeder Test schreibt in sein eigenes ``tmp_path``."""
    return FileProjectRepository(str(tmp_path / 'projects'))


# --- create -----------------------------------------------------------------


def test_create_assigns_the_id_format_the_artifact_paths_depend_on(repo):
    """``proj_`` plus 12 Hexstellen — die Kennung ist ein Verzeichnisname.

    Unter ``uploads/projects/<project_id>/`` liegen die Artefakte. Ein Adapter,
    der hier eine UUID vergibt, macht jeden bestehenden Pfad ungueltig.
    """
    project = repo.create('Mein Projekt')

    assert project.project_id.startswith('proj_')
    assert len(project.project_id) == len('proj_') + 12
    int(project.project_id.removeprefix('proj_'), 16)  # wirft, wenn nicht hex


def test_create_persists_immediately(repo):
    created = repo.create('Mein Projekt')

    assert repo.get(created.project_id) is not None
    assert repo.get(created.project_id).name == 'Mein Projekt'


def test_create_stamps_both_timestamps(repo):
    """``updated_at`` wird beim Speichern neu gesetzt und liegt daher minimal
    hinter ``created_at`` — das war vor dem Port genauso und ist kein Fehler."""
    project = repo.create()

    assert project.created_at
    assert project.updated_at >= project.created_at


# --- get --------------------------------------------------------------------


def test_get_returns_none_for_an_unknown_id_instead_of_raising(repo):
    """Ein fehlendes Projekt ist ein erwarteter Fall, kein Fehler."""
    assert repo.get('proj_gibtesnicht') is None


# --- save -------------------------------------------------------------------


def test_save_advances_updated_at_and_leaves_created_at_alone(repo):
    project = repo.create('Vorher')
    created_at = project.created_at

    project.name = 'Nachher'
    repo.save(project)

    reloaded = repo.get(project.project_id)
    assert reloaded.name == 'Nachher'
    assert reloaded.created_at == created_at
    assert reloaded.updated_at >= created_at


def test_save_does_not_invent_a_project_that_was_never_created(repo):
    """``save`` legt kein Verzeichnis an — sonst entstuende ein Projekt, das
    nie angelegt wurde, als stiller Nebeneffekt eines Schreibvorgangs."""
    from app.contracts import Project

    with pytest.raises(OSError):
        repo.save(Project(project_id='proj_niemalsangelegt'))


# --- list -------------------------------------------------------------------


def test_list_returns_the_newest_first(repo):
    older = repo.create('Aelter')
    newer = repo.create('Neuer')
    # Zeitstempel ausdruecklich setzen: zwei Anlagen in derselben Sekunde
    # duerfen den Test nicht von der Uhr abhaengig machen.
    older.created_at = '2026-01-01T00:00:00'
    newer.created_at = '2026-06-01T00:00:00'
    repo.save(older)
    repo.save(newer)

    listed = repo.list()

    assert [item.project_id for item in listed] == [
        newer.project_id,
        older.project_id,
    ]


def test_list_caps_at_limit_after_sorting_not_before(repo):
    """Erst sortieren, dann kappen — sonst liefert ``limit=1`` irgendeines."""
    for index, stamp in enumerate(['2026-01-01', '2026-06-01', '2026-03-01']):
        project = repo.create(f'Projekt {index}')
        project.created_at = f'{stamp}T00:00:00'
        repo.save(project)

    listed = repo.list(limit=1)

    assert len(listed) == 1
    assert listed[0].created_at.startswith('2026-06-01')


def test_list_is_empty_and_does_not_raise_when_nothing_exists(repo):
    assert repo.list() == []


def test_list_skips_a_directory_without_a_record(repo):
    """Ein halb angelegtes Verzeichnis darf die Liste nicht abbrechen."""
    project = repo.create('Echt')
    (Path(repo.projects_dir) / 'proj_nurverzeichnis').mkdir()

    assert [item.project_id for item in repo.list()] == [project.project_id]


def test_one_unreadable_record_does_not_take_down_the_whole_list(repo, monkeypatch):
    """Ein kaputter Datensatz darf nicht alle Projekte unerreichbar machen.

    Vor dem Vertrag war das kaum zu treffen: die alte ``from_dict`` pruefte
    keine Typen. Pydantic prueft jedes Feld — ohne diese Isolation haette ein
    einziges beschaedigtes Verzeichnis die gesamte Projektuebersicht
    abgeschaltet.
    """
    project = repo.create('Intakt')
    kaputt = Path(repo.projects_dir) / 'proj_kaputt000000'
    kaputt.mkdir()
    (kaputt / 'project.json').write_text('{ das ist kein JSON')

    # Der Projekt-Logger propagiert nicht an die Wurzel, also faengt ``caplog``
    # ihn nicht. Statt die Logging-Konfiguration fuer einen Test umzubiegen,
    # wird der Modul-Logger durch einen Mitschreiber ersetzt.
    warnungen: list[str] = []
    monkeypatch.setattr(
        store_module.logger,
        'warning',
        lambda nachricht, *args: warnungen.append(nachricht % args),
    )

    listed = repo.list()

    assert [item.project_id for item in listed] == [project.project_id]
    # Uebersprungen heisst nicht verschwiegen.
    assert any('proj_kaputt000000' in eintrag for eintrag in warnungen)


def test_a_direct_get_on_an_unreadable_record_still_raises(repo):
    """``get`` bleibt laut — wer dieses Projekt anfordert, soll den Fehler sehen.

    Der Unterschied zu ``list`` ist Absicht: dort waere ein Abbruch
    unverhaeltnismaessig, hier waere ein stilles ``None`` eine Luege ueber ein
    Projekt, das es sehr wohl gibt.
    """
    kaputt = Path(repo.projects_dir)
    kaputt.mkdir(parents=True, exist_ok=True)
    (kaputt / 'proj_kaputt000000').mkdir()
    (kaputt / 'proj_kaputt000000' / 'project.json').write_text('{ kaputt')

    with pytest.raises(ValueError):
        repo.get('proj_kaputt000000')


# --- delete -----------------------------------------------------------------


def test_delete_reports_whether_there_was_a_record(repo):
    project = repo.create('Weg damit')

    assert repo.delete(project.project_id) is True
    assert repo.delete(project.project_id) is False
    assert repo.get(project.project_id) is None


def test_delete_leaves_the_artifacts_to_the_caller(repo):
    """Der Port raeumt nur Metadaten ab — das Verzeichnis gehoert dem Aufrufer.

    Andernfalls haette jeder Adapter eine Meinung zum Dateisystem zu haben,
    und der PostgreSQL-Adapter haette sie faelschlich.
    """
    project = repo.create('Mit Artefakten')
    project_dir = Path(repo.projects_dir) / project.project_id
    (project_dir / 'files').mkdir()
    (project_dir / 'files' / 'quelle.pdf').write_text('Inhalt')

    repo.delete(project.project_id)

    assert (project_dir / 'files' / 'quelle.pdf').exists()


# --- Fabrik -----------------------------------------------------------------


def test_factory_returns_something_satisfying_the_port_protocol(tmp_path):
    repository = get_project_repository(storage_root=str(tmp_path))

    assert isinstance(repository, ProjectRepository)


def test_factory_honours_the_storage_root_it_is_given(tmp_path):
    repository = get_project_repository(storage_root=str(tmp_path / 'woanders'))
    created = repository.create('Anderswo')

    assert (tmp_path / 'woanders' / created.project_id / 'project.json').exists()


def test_factory_rejects_an_unknown_backend_instead_of_falling_back(monkeypatch):
    """Ein Tippfehler darf nicht still den Dateiadapter liefern.

    ``Config.validate()`` faengt das beim Start ab. Wer das Repository ohne
    Validierung erreicht — ein Test, ein Wartungsskript — bekaeme sonst
    klaglos die Vorgabe und glaubte, er haette umgeschaltet.
    """
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'filee')

    with pytest.raises(ProjectBackendUnavailable):
        repository_module.get_project_repository()


def test_factory_raises_for_a_backend_without_an_adapter(monkeypatch):
    """``postgres`` ist gueltige Konfiguration, hat aber noch keinen Adapter.

    Der Fehler sagt das, statt beim ersten Projektzugriff als Importfehler zu
    erscheinen und nach einem Tippfehler aussehen zu lassen.
    """
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')

    with pytest.raises(ProjectBackendUnavailable):
        repository_module.get_project_repository()
