"""Contract-Tests fuer ``app.repositories.persona_set_repository`` (Issue #1807).

Prueft die Zusagen, die der Port in seinen Docstrings festschreibt, gegen
``FilePersonaSetRepository`` — den Dateiadapter. Der PostgreSQL-Adapter muss
dieselben Zusagen einhalten; ``tests/integration/test_postgres_persona_set_repository.py``
zieht sie gegen eine echte Instanz nach.

Jeder Test arbeitet in einem eigenen ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from app.contracts.persona_set_contract import (
    PersonaSetEntry,
    PersonaSetProfile,
    PersonaSetRecord,
)
from app.repositories.persona_set_repository import (
    PersonaSetBackendUnavailable,
    PersonaSetRepository,
    get_persona_set_repository,
    new_persona_set_entry_id,
    new_persona_set_id,
)
from app.config import Config
from app.services.file_persona_set_store import FilePersonaSetRepository


def _record(set_id: str = 'pset_aaaaaaaaaaaa', **overrides) -> PersonaSetRecord:
    data = {
        'id': set_id,
        'name': 'Betroffene',
        'created_at': '2026-10-07T10:00:00',
        'updated_at': '2026-10-07T10:00:00',
    }
    data.update(overrides)
    return PersonaSetRecord(**data)


def _entry(entry_id: str, origin: str = 'manual') -> PersonaSetEntry:
    return PersonaSetEntry(
        entry_id=entry_id,
        origin=origin,
        profile=PersonaSetProfile(username=f'user_{entry_id}', name=f'Name {entry_id}'),
        source_entity_uuid='uuid-1' if origin == 'graph' else None,
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / 'persona_sets'


@pytest.fixture
def repo(root: Path) -> FilePersonaSetRepository:
    return FilePersonaSetRepository(storage_root=str(root))


# ---------------------------------------------------------------------------
# Port-Form
# ---------------------------------------------------------------------------


def test_adapter_satisfies_the_port(repo: FilePersonaSetRepository):
    assert isinstance(repo, PersonaSetRepository)


def test_generated_ids_have_the_documented_form():
    set_id, entry_id = new_persona_set_id(), new_persona_set_entry_id()

    assert set_id.startswith('pset_') and len(set_id) == len('pset_') + 12
    assert entry_id.startswith('pent_') and len(entry_id) == len('pent_') + 12
    assert new_persona_set_id() != set_id


# ---------------------------------------------------------------------------
# get / save
# ---------------------------------------------------------------------------


def test_get_unknown_returns_none_and_does_not_raise(repo: FilePersonaSetRepository):
    assert repo.get('pset_gibtesnicht') is None


def test_save_creates_an_unknown_set_and_get_returns_it(repo: FilePersonaSetRepository):
    record = _record()

    repo.save(record)

    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.id == record.id
    assert loaded.name == 'Betroffene'
    assert loaded.created_at == '2026-10-07T10:00:00'


def test_save_stamps_updated_at_on_record_and_in_storage(repo: FilePersonaSetRepository):
    record = _record()

    repo.save(record)

    assert record.updated_at != '2026-10-07T10:00:00'
    loaded = repo.get(record.id)
    assert loaded is not None and loaded.updated_at == record.updated_at


def test_roundtrip_keeps_entries_with_origin_and_all_fields(repo: FilePersonaSetRepository):
    record = _record(
        description='Satz mit Umlauten äöü',
        graph_id='graph_001',
        project_id='proj_aabbccddeeff',
        entries=[_entry('pent_a', 'graph'), _entry('pent_b', 'ai_draft'), _entry('pent_c', 'fallback')],
    )

    repo.save(record)
    loaded = repo.get(record.id)

    assert loaded is not None
    assert loaded.model_dump(mode='json') == record.model_dump(mode='json')
    assert [(e.entry_id, e.origin) for e in loaded.entries] == [
        ('pent_a', 'graph'),
        ('pent_b', 'ai_draft'),
        ('pent_c', 'fallback'),
    ]
    assert loaded.entries[0].source_entity_uuid == 'uuid-1'


def test_save_overwrites_an_existing_set(repo: FilePersonaSetRepository):
    record = _record()
    repo.save(record)

    record.name = 'Neu benannt'
    record.entries = [_entry('pent_a')]
    repo.save(record)

    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.name == 'Neu benannt'
    assert len(loaded.entries) == 1
    assert len(repo.list()) == 1


# ---------------------------------------------------------------------------
# list / delete
# ---------------------------------------------------------------------------


def test_list_of_empty_storage_is_empty_without_creating_the_directory(
    repo: FilePersonaSetRepository, root: Path
):
    assert repo.list() == []
    assert not root.exists()


def test_list_is_newest_first_with_id_as_tie_break(repo: FilePersonaSetRepository):
    repo.save(_record('pset_old', created_at='2026-10-01T10:00:00'))
    repo.save(_record('pset_new', created_at='2026-10-03T10:00:00'))
    repo.save(_record('pset_mid_a', created_at='2026-10-02T10:00:00'))
    repo.save(_record('pset_mid_b', created_at='2026-10-02T10:00:00'))

    assert [r.id for r in repo.list()] == ['pset_new', 'pset_mid_b', 'pset_mid_a', 'pset_old']


def test_delete_reports_whether_a_set_existed(repo: FilePersonaSetRepository):
    repo.save(_record())

    assert repo.delete('pset_aaaaaaaaaaaa') is True
    assert repo.get('pset_aaaaaaaaaaaa') is None
    assert repo.delete('pset_aaaaaaaaaaaa') is False
    assert repo.list() == []


# ---------------------------------------------------------------------------
# mark_used
# ---------------------------------------------------------------------------


def test_mark_used_locks_on_first_use_and_records_the_simulation(repo: FilePersonaSetRepository):
    repo.save(_record())

    result = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')

    assert result is not None
    assert result.used_by_simulation_ids == ['sim_000000000001']
    assert result.locked_at is not None
    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert stored.used_by_simulation_ids == ['sim_000000000001']
    assert stored.locked_at == result.locked_at


def test_mark_used_twice_with_the_same_simulation_is_idempotent(repo: FilePersonaSetRepository):
    repo.save(_record())
    first = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')
    assert first is not None

    second = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')

    assert second is not None
    assert second.used_by_simulation_ids == ['sim_000000000001']
    assert second.locked_at == first.locked_at
    assert second.updated_at == first.updated_at
    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert stored.used_by_simulation_ids == ['sim_000000000001']


def test_a_second_simulation_is_appended_and_the_lock_time_stays(repo: FilePersonaSetRepository):
    repo.save(_record())
    first = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')
    assert first is not None

    second = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000002')

    assert second is not None
    assert second.used_by_simulation_ids == ['sim_000000000001', 'sim_000000000002']
    assert second.locked_at == first.locked_at


def test_mark_used_on_unknown_set_returns_none_and_creates_nothing(
    repo: FilePersonaSetRepository,
):
    assert repo.mark_used('pset_gibtesnicht', 'sim_000000000001') is None
    assert repo.list() == []


def test_mark_used_rejects_an_empty_simulation_id(repo: FilePersonaSetRepository):
    repo.save(_record())

    with pytest.raises(ValueError):
        repo.mark_used('pset_aaaaaaaaaaaa', '')


def test_save_with_a_stale_record_cannot_lift_the_lock(repo: FilePersonaSetRepository):
    stale = _record()
    repo.save(stale)
    repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')

    stale.name = 'Aenderung auf altem Stand'
    repo.save(stale)

    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert stored.name == 'Aenderung auf altem Stand'
    assert stored.locked_at is not None
    assert stored.used_by_simulation_ids == ['sim_000000000001']
    # Der uebergebene Datensatz wird an den gespeicherten Stand angeglichen.
    assert stale.locked_at == stored.locked_at
    assert stale.used_by_simulation_ids == ['sim_000000000001']


def test_concurrent_mark_used_loses_no_simulation(repo: FilePersonaSetRepository):
    repo.save(_record())
    simulation_ids = [f'sim_{i:012d}' for i in range(16)]
    errors: list[BaseException] = []

    def work(simulation_id: str) -> None:
        try:
            # Eigene Adapterinstanz: die Fabrik baut ebenfalls je Aufruf eine neue.
            FilePersonaSetRepository(repo.storage_root).mark_used(
                'pset_aaaaaaaaaaaa', simulation_id
            )
        except BaseException as exc:  # noqa: BLE001 — wird unten geprueft
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(sid,)) for sid in simulation_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert sorted(stored.used_by_simulation_ids) == simulation_ids


# ---------------------------------------------------------------------------
# Dateiablage
# ---------------------------------------------------------------------------


def test_each_set_is_one_json_file_named_after_its_id(repo: FilePersonaSetRepository, root: Path):
    repo.save(_record())

    assert sorted(p.name for p in root.iterdir()) == ['pset_aaaaaaaaaaaa.json']
    payload = json.loads((root / 'pset_aaaaaaaaaaaa.json').read_text(encoding='utf-8'))
    assert payload['id'] == 'pset_aaaaaaaaaaaa'
    assert payload['schema_version'] == 1


def test_invalid_ids_never_reach_the_file_system(repo: FilePersonaSetRepository, root: Path):
    for bad in ('../escape', 'a/b', '', '.hidden', 'x' * 65, 'pset id'):
        assert repo.get(bad) is None
        assert repo.delete(bad) is False
        assert repo.mark_used(bad, 'sim_1') is None
    with pytest.raises(ValueError):
        repo.save(_record('../escape'))
    assert not root.exists()


def test_corrupt_file_is_an_error_on_get_but_does_not_break_the_list(
    repo: FilePersonaSetRepository, root: Path
):
    repo.save(_record('pset_gut', created_at='2026-10-01T10:00:00'))
    (root / 'pset_kaputt.json').write_text('{kein json', encoding='utf-8')
    (root / 'pset_vertrag.json').write_text('{"id": "pset_vertrag", "name": ""}', encoding='utf-8')

    with pytest.raises(ValueError):
        repo.get('pset_kaputt')
    with pytest.raises(ValueError):
        repo.get('pset_vertrag')
    assert [r.id for r in repo.list()] == ['pset_gut']


def _refuse_writes(monkeypatch) -> None:
    def refuse(path: str, payload: object) -> None:
        raise PermissionError('read-only volume')

    monkeypatch.setattr('app.services.file_persona_set_store.write_json_atomic', refuse)


def test_save_does_not_swallow_storage_errors(repo: FilePersonaSetRepository, monkeypatch):
    _refuse_writes(monkeypatch)

    with pytest.raises(PermissionError):
        repo.save(_record())


def test_mark_used_does_not_swallow_storage_errors(repo: FilePersonaSetRepository, monkeypatch):
    repo.save(_record())
    _refuse_writes(monkeypatch)

    with pytest.raises(PermissionError):
        repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')
    monkeypatch.undo()
    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert stored.used_by_simulation_ids == []
    assert stored.locked_at is None


def test_unreadable_storage_is_not_swallowed_on_list(
    repo: FilePersonaSetRepository, monkeypatch
):
    repo.save(_record())

    def refuse(self: FilePersonaSetRepository, set_id: str):
        raise PermissionError('no access')

    monkeypatch.setattr(FilePersonaSetRepository, 'get', refuse)

    with pytest.raises(PermissionError):
        repo.list()


def test_a_failed_write_leaves_the_previous_version_intact(
    repo: FilePersonaSetRepository, root: Path, monkeypatch
):
    repo.save(_record(name='Vorher'))

    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError('disk full')

    monkeypatch.setattr('app.utils.json_io.os.replace', explode)
    changed = _record(name='Nachher')
    with pytest.raises(OSError):
        repo.save(changed)
    monkeypatch.undo()

    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None and stored.name == 'Vorher'
    assert [p.name for p in root.iterdir()] == ['pset_aaaaaaaaaaaa.json']


# ---------------------------------------------------------------------------
# Fabrik
# ---------------------------------------------------------------------------


def test_factory_default_is_the_file_adapter_at_the_given_root(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'file')

    adapter = get_persona_set_repository(str(tmp_path))

    assert isinstance(adapter, FilePersonaSetRepository)
    assert adapter.storage_root == str(tmp_path)


def test_factory_without_root_uses_the_upload_folder(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'file')
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))

    adapter = get_persona_set_repository()

    assert isinstance(adapter, FilePersonaSetRepository)
    assert adapter.storage_root == os.path.join(str(tmp_path), 'persona_sets')


def test_factory_rejects_unknown_value_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'sqlite')

    with pytest.raises(PersonaSetBackendUnavailable):
        get_persona_set_repository()
