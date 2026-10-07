"""Vertragstests fuer ``app.contracts.persona_set_contract`` (Issue #1807).

Sie halten fest, was der Vertrag zusagt: strikte Felder, eindeutige Eintrags-
kennungen, die Sperre als Zustand des Datensatzes, ISO-Zeitstempel und eine
verlustfreie Serialisierung — die Persistenz-Adapter verlassen sich darauf.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.persona_contract import PersonaModel
from app.contracts.persona_set_contract import (
    PERSONA_SET_MAX_ENTRIES,
    PERSONA_SET_NAME_MAX_LENGTH,
    PERSONA_SET_SCHEMA_VERSION,
    PersonaSetCreate,
    PersonaSetDuplicate,
    PersonaSetEntry,
    PersonaSetEntryCreate,
    PersonaSetEntryUpdate,
    PersonaSetProfile,
    PersonaSetRecord,
    PersonaSetSummary,
    PersonaSetUpdate,
)

ORIGINS = ('graph', 'manual', 'ai_draft', 'fallback')


def _profile(**overrides: Any) -> PersonaSetProfile:
    data: dict[str, Any] = {'username': 'maren_hoffmann', 'name': 'Maren Hoffmann'}
    data.update(overrides)
    return PersonaSetProfile(**data)


def _entry(entry_id: str = 'pent_000000000001', origin: str = 'manual') -> PersonaSetEntry:
    return PersonaSetEntry(entry_id=entry_id, origin=origin, profile=_profile())


def _record(**overrides: Any) -> PersonaSetRecord:
    data: dict[str, Any] = {'id': 'pset_000000000001', 'name': 'Betroffene'}
    data.update(overrides)
    return PersonaSetRecord(**data)


# ---------------------------------------------------------------------------
# Gueltig
# ---------------------------------------------------------------------------


def test_minimal_record_is_valid_and_editable():
    record = _record()

    assert record.entries == []
    assert record.locked_at is None
    assert record.used_by_simulation_ids == []
    assert record.description == ''
    assert record.graph_id is None
    assert record.project_id is None
    assert record.schema_version == PERSONA_SET_SCHEMA_VERSION == 1


@pytest.mark.parametrize('origin', ORIGINS)
def test_every_origin_is_accepted(origin: str):
    assert _entry(origin=origin).origin == origin


def test_full_record_roundtrips_losslessly_through_json():
    profile = _profile(
        bio='Pflegekraft aus Leipzig',
        persona='Ausfuehrliche Beschreibung.',
        age=47,
        gender='female',
        mbti='ISFJ',
        country='DE',
        profession='Pflegekraft',
        interested_topics=['Pflege', 'Tarif'],
        source_entity_type='Person',
        persona_kind='individual',
        language='de',
        activity_level=0.4,
        time_zone='Europe/Berlin',
        location='Leipzig',
        verified=True,
    )
    entries = [
        PersonaSetEntry(
            entry_id='pent_000000000001',
            origin='graph',
            profile=profile,
            source_entity_uuid='uuid-1',
            created_at='2026-10-07T10:00:00',
            updated_at='2026-10-07T10:05:00.123456',
        ),
        _entry('pent_000000000002', 'fallback'),
    ]
    record = _record(
        description='Satz fuer den Tarifkonflikt',
        graph_id='graph_001',
        project_id='proj_aabbccddeeff',
        entries=entries,
        locked_at='2026-10-07T11:00:00',
        used_by_simulation_ids=['sim_aaaaaaaaaaaa', 'sim_bbbbbbbbbbbb'],
        created_at='2026-10-07T09:00:00',
        updated_at='2026-10-07T11:00:00',
    )

    restored = PersonaSetRecord.model_validate(
        json.loads(json.dumps(record.model_dump(mode='json')))
    )

    assert restored == record
    assert restored.model_dump(mode='json') == record.model_dump(mode='json')


def test_locked_state_serializes_with_timestamp_and_usage():
    record = _record(
        locked_at='2026-10-07T11:00:00',
        used_by_simulation_ids=['sim_aaaaaaaaaaaa'],
    )

    dumped = record.model_dump(mode='json')

    assert dumped['locked_at'] == '2026-10-07T11:00:00'
    assert dumped['used_by_simulation_ids'] == ['sim_aaaaaaaaaaaa']
    assert dumped['schema_version'] == 1


def test_locked_without_usage_is_valid():
    """Gesperrt ist ein Zustand, den ``mark_used`` setzt; die Liste folgt ihm."""
    assert _record(locked_at='2026-10-07T11:00:00').used_by_simulation_ids == []


def test_name_is_stripped():
    assert _record(name='  Betroffene  ').name == 'Betroffene'


def test_timestamps_default_to_iso_strings():
    from datetime import datetime

    record = _record()
    entry = _entry()

    for value in (record.created_at, record.updated_at, entry.created_at, entry.updated_at):
        assert isinstance(value, str)
        datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# Ungueltig
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('name', ['', '   ', 'x' * (PERSONA_SET_NAME_MAX_LENGTH + 1)])
def test_invalid_name_is_rejected(name: str):
    with pytest.raises(ValidationError):
        _record(name=name)
    with pytest.raises(ValidationError):
        PersonaSetCreate(name=name)
    with pytest.raises(ValidationError):
        PersonaSetDuplicate(name=name)


def test_name_at_the_limit_is_accepted():
    assert _record(name='x' * PERSONA_SET_NAME_MAX_LENGTH)


def test_empty_id_is_rejected():
    with pytest.raises(ValidationError):
        _record(id='')


def test_unknown_origin_is_rejected():
    with pytest.raises(ValidationError):
        PersonaSetEntry(entry_id='pent_1', origin='imported', profile=_profile())


def test_duplicate_entry_ids_are_rejected():
    with pytest.raises(ValidationError, match='entry_id must be unique'):
        _record(entries=[_entry('pent_dup'), _entry('pent_dup', 'graph')])


def test_distinct_entry_ids_with_equal_profiles_are_accepted():
    """Eindeutig ist die Kennung, nicht das Profil: derselbe Name darf zweimal stehen."""
    record = _record(entries=[_entry('pent_a'), _entry('pent_b')])

    assert [e.entry_id for e in record.entries] == ['pent_a', 'pent_b']


def test_too_many_entries_are_rejected():
    entries = [_entry(f'pent_{i:06d}') for i in range(PERSONA_SET_MAX_ENTRIES + 1)]

    with pytest.raises(ValidationError):
        _record(entries=entries)


def test_duplicate_or_empty_used_by_is_rejected():
    locked = '2026-10-07T11:00:00'
    with pytest.raises(ValidationError, match='duplicates'):
        _record(locked_at=locked, used_by_simulation_ids=['sim_a', 'sim_a'])
    with pytest.raises(ValidationError, match='empty ids'):
        _record(locked_at=locked, used_by_simulation_ids=[''])


def test_usage_without_lock_is_rejected():
    with pytest.raises(ValidationError, match='must be locked'):
        _record(used_by_simulation_ids=['sim_aaaaaaaaaaaa'])


@pytest.mark.parametrize('field', ['created_at', 'updated_at', 'locked_at'])
def test_non_iso_timestamp_is_rejected(field: str):
    with pytest.raises(ValidationError, match='ISO-8601'):
        _record(**{field: 'gestern'})


def test_non_iso_entry_timestamp_is_rejected():
    with pytest.raises(ValidationError, match='ISO-8601'):
        PersonaSetEntry(
            entry_id='pent_1', origin='manual', profile=_profile(), created_at='nope'
        )


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        _record(schema_version=2)


@pytest.mark.parametrize(
    'overrides',
    [
        {'age': -1},
        {'age': 121},
        {'gender': 'x'},
        {'mbti': 'ABCD'},
        {'country': 'DEU'},
        {'activity_level': 1.5},
        {'persona_kind': 'group'},
        {'interested_topics': [f't{i}' for i in range(16)]},
        {'username': ''},
        {'name': ''},
    ],
)
def test_invalid_profile_values_are_rejected(overrides: dict[str, Any]):
    with pytest.raises(ValidationError):
        _profile(**overrides)


# ---------------------------------------------------------------------------
# Unbekannte Felder werden abgelehnt (extra="forbid")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'model, payload',
    [
        (PersonaSetRecord, {'id': 'pset_1', 'name': 'A', 'zusatz': 1}),
        (PersonaSetEntry, {'entry_id': 'e', 'origin': 'manual', 'profile': {'username': 'u', 'name': 'n'}, 'zusatz': 1}),
        (PersonaSetProfile, {'username': 'u', 'name': 'n', 'zusatz': 1}),
        (PersonaSetCreate, {'name': 'A', 'zusatz': 1}),
        (PersonaSetUpdate, {'name': 'A', 'zusatz': 1}),
        (PersonaSetDuplicate, {'name': 'A', 'zusatz': 1}),
        (PersonaSetEntryCreate, {'origin': 'manual', 'profile': {'username': 'u', 'name': 'n'}, 'zusatz': 1}),
        (PersonaSetEntryUpdate, {'origin': 'manual', 'zusatz': 1}),
    ],
)
def test_unknown_field_is_rejected(model: type, payload: dict[str, Any]):
    with pytest.raises(ValidationError, match='zusatz'):
        model.model_validate(payload)


def test_origin_is_not_a_profile_field():
    """Die Herkunft steht am Eintrag; ``PersonaModel`` bleibt unveraendert."""
    with pytest.raises(ValidationError):
        _profile(origin='manual')
    assert 'origin' not in PersonaModel.model_fields


# ---------------------------------------------------------------------------
# Summary, Anfragen
# ---------------------------------------------------------------------------


def test_summary_counts_entries_and_usage_without_entries():
    record = _record(
        entries=[_entry('pent_a'), _entry('pent_b')],
        locked_at='2026-10-07T11:00:00',
        used_by_simulation_ids=['sim_aaaaaaaaaaaa'],
    )

    summary = PersonaSetSummary.from_record(record)

    assert (summary.entry_count, summary.locked, summary.usage_count) == (2, True, 1)
    assert summary.locked_at == '2026-10-07T11:00:00'
    assert 'entries' not in summary.model_dump()


def test_summary_of_editable_set_is_not_locked():
    summary = PersonaSetSummary.from_record(_record())

    assert (summary.entry_count, summary.locked, summary.usage_count) == (0, False, 0)


def test_update_requires_at_least_one_field():
    with pytest.raises(ValidationError, match='at least one'):
        PersonaSetUpdate()
    assert PersonaSetUpdate(description='neu').name is None
    assert PersonaSetUpdate(name='neu').description is None


def test_entry_update_requires_at_least_one_field():
    with pytest.raises(ValidationError, match='at least one'):
        PersonaSetEntryUpdate()
    assert PersonaSetEntryUpdate(origin='manual').profile is None


def test_entry_create_carries_no_server_assigned_fields():
    fields = set(PersonaSetEntryCreate.model_fields)

    assert fields == {'origin', 'profile', 'source_entity_uuid'}
