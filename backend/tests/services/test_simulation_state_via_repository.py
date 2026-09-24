"""Simulationsstatus läuft über das Repository, nie direkt über state.json.

Mit ``AGORA_SIMULATION_BACKEND=postgres`` gibt es keine ``state.json`` mehr.
Jeder direkte Store-Zugriff auf den Artefakt-Schlüssel ``state`` sähe dort
nichts bzw. schriebe an der Datenbank vorbei (CodeRabbit-Review auf #1598).
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from app.contracts.simulation_record_contract import SimulationRecord
from app.repositories import simulation_repository as port


class _DbOnlyRepository:
    """Steht für den PostgreSQL-Adapter: kennt den Datensatz, es gibt keine Datei."""

    def __init__(self, record: SimulationRecord) -> None:
        self.records = {record.simulation_id: record}
        self.saved: list[SimulationRecord] = []

    def get(self, simulation_id: str) -> Optional[SimulationRecord]:
        return self.records.get(simulation_id)

    def save(self, record: SimulationRecord) -> None:
        self.saved.append(record.model_copy())
        self.records[record.simulation_id] = record


class _EmptyStore:
    """Artefakt-Store ohne state.json, aber mit den übrigen Artefakten."""

    def exists(self, simulation_id: str, artifact: str) -> bool:
        return artifact != 'state'

    def read_json(self, simulation_id: str, artifact: str, default: Any = None) -> Any:
        if artifact == 'state':
            raise AssertionError('state.json darf nicht direkt gelesen werden')
        if artifact == 'reddit_profiles':
            return [{'id': 1}]
        return default

    def write_json(self, simulation_id: str, artifact: str, payload: Any) -> None:
        if artifact == 'state':
            raise AssertionError('state.json darf nicht direkt geschrieben werden')


def _record(status: str) -> SimulationRecord:
    return SimulationRecord(
        simulation_id='sim_0123456789ab',
        project_id='proj_112233445566',
        status=status,
        config_generated=True,
        entities_count=3,
        created_at='2026-09-01T10:00:00',
        updated_at='2026-09-01T10:00:00',
    )


@pytest.fixture
def db_repository(monkeypatch) -> _DbOnlyRepository:
    repository = _DbOnlyRepository(_record('preparing'))
    monkeypatch.setattr(port, 'get_simulation_repository', lambda **_: repository)
    return repository


def test_runner_stop_marks_status_through_the_repository(db_repository, monkeypatch):
    from app.services import simulation_runner

    monkeypatch.setattr(simulation_runner, '_store', lambda: _EmptyStore())

    simulation_runner.SimulationRunner._mark_store_state_stopped('sim_0123456789ab')

    assert db_repository.saved and db_repository.saved[-1].status == 'stopped'


def test_prepared_check_reads_and_promotes_through_the_repository(
    db_repository, monkeypatch, tmp_path
):
    from app.api import simulation_prepare_state as mod

    sim_dir = tmp_path / 'sim_0123456789ab'
    sim_dir.mkdir()
    (sim_dir / 'twitter_profiles.csv').write_text('id\n1\n', encoding='utf-8')
    monkeypatch.setattr(mod.Config, 'OASIS_SIMULATION_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(mod, 'get_artifact_store', lambda: _EmptyStore())
    monkeypatch.setattr(mod, 'get_simulation_repository', port.get_simulation_repository)

    is_prepared, info = mod.check_simulation_prepared('sim_0123456789ab')

    assert is_prepared is True, info
    assert info['status'] == 'ready'
    assert 'state.json' in info['existing_files']
    assert db_repository.saved[-1].status == 'ready'
