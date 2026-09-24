"""Contract-Tests fuer ``app.repositories.simulation_repository`` (Issue #1578).

Prueft die Invarianten, die der Port in seinen Docstrings festschreibt, gegen
``FileSimulationRepository`` — den einen heutigen Adapter. Der PostgreSQL-Adapter
aus #1585 muss dieselben Zusagen einhalten; diese Datei ist die Referenz dafuer.

Ohne sie waere die ``None``-Zusage von ``get``, die Filterbedingung von ``list``
und die Branch-Logik von ``list_branches`` nur Prosa im Docstring: ein zweiter
Adapter mit falschem Verhalten ginge durch, ohne dass ein Test anschlaegt.

Jede Instanz bekommt ihren eigenen ``InMemoryArtifactStore``, damit kein Test
ins Dateisystem schreibt. #1585 ergaenzt den Postgres-Adapter als weiteren
``pytest.mark.parametrize``-Parameter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest

from app.contracts.simulation_record_contract import SimulationRecord
from app.repositories.simulation_repository import (
    SimulationRepository,
    get_simulation_repository,
)
from app.services.artifact_store import InMemoryArtifactStore
from app.services.file_simulation_store import FileSimulationRepository
from app.services.simulation_manager import SimulationState, SimulationStatus


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_record(
    simulation_id: str = 'sim_aabbccdd0011',
    project_id: str = 'proj_112233445566',
    graph_id: str = 'graph_001',
    status: str = 'created',
    source_simulation_id: Optional[str] = None,
    root_simulation_id: Optional[str] = None,
    branch_name: Optional[str] = None,
    branch_depth: int = 0,
) -> SimulationRecord:
    now = datetime.now().isoformat()
    return SimulationRecord(
        simulation_id=simulation_id,
        project_id=project_id,
        graph_id=graph_id,
        status=status,
        created_at=now,
        updated_at=now,
        source_simulation_id=source_simulation_id,
        root_simulation_id=root_simulation_id or simulation_id,
        branch_name=branch_name,
        branch_depth=branch_depth,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_store() -> InMemoryArtifactStore:
    return InMemoryArtifactStore()


@pytest.fixture
def repo(in_memory_store: InMemoryArtifactStore) -> FileSimulationRepository:
    """Isolierter Adapter — jeder Test arbeitet mit einem eigenen In-Memory-Store."""
    return FileSimulationRepository(simulations_dir=None, store=in_memory_store)


# ---------------------------------------------------------------------------
# Roundtrip SimulationState.to_dict() → SimulationRecord → zurueck
# ---------------------------------------------------------------------------


def test_roundtrip_simulation_state_to_dict_is_lossless():
    """Alle Felder von SimulationState.to_dict() landen verlustfrei im Record.

    Das ist das Kernversprechen von Issue #1578: kein Datenverlust beim Umbau.
    """
    state = SimulationState(
        simulation_id='sim_roundtrip0001',
        project_id='proj_aabbccddeeff',
        graph_id='graph_xyz',
        enable_twitter=False,
        enable_reddit=True,
        status=SimulationStatus.READY,
        entities_count=42,
        profiles_count=17,
        entity_types=['Politician', 'Journalist'],
        config_generated=True,
        config_reasoning='LLM sagt so',
        current_round=3,
        twitter_status='running',
        reddit_status='completed',
        created_at='2026-01-15T10:00:00',
        updated_at='2026-01-15T11:00:00',
        error=None,
        source_simulation_id='sim_parent000001',
        root_simulation_id='sim_root0000001',
        branch_name='variant-A',
        branch_depth=2,
        persona_floor=50,
    )

    data = state.to_dict()
    record = SimulationRecord.from_dict(data)

    assert record.simulation_id == state.simulation_id
    assert record.project_id == state.project_id
    assert record.graph_id == state.graph_id
    assert record.enable_twitter == state.enable_twitter
    assert record.enable_reddit == state.enable_reddit
    assert record.status == state.status.value
    assert record.entities_count == state.entities_count
    assert record.profiles_count == state.profiles_count
    assert record.entity_types == state.entity_types
    assert record.config_generated == state.config_generated
    assert record.config_reasoning == state.config_reasoning
    assert record.current_round == state.current_round
    assert record.twitter_status == state.twitter_status
    assert record.reddit_status == state.reddit_status
    assert record.created_at == state.created_at
    assert record.updated_at == state.updated_at
    assert record.error == state.error
    assert record.source_simulation_id == state.source_simulation_id
    assert record.root_simulation_id == state.root_simulation_id
    assert record.branch_name == state.branch_name
    assert record.branch_depth == state.branch_depth
    assert record.persona_floor == state.persona_floor


def test_roundtrip_record_to_dict_preserves_all_keys():
    """``SimulationRecord.to_dict()`` liefert alle Schluessel aus ``SimulationState.to_dict()``."""
    state = SimulationState(
        simulation_id='sim_keychecktest',
        project_id='proj_000000000001',
        graph_id='g1',
    )
    state_keys = set(state.to_dict().keys())
    record = SimulationRecord.from_dict(state.to_dict())
    record_keys = set(record.to_dict().keys())

    assert state_keys == record_keys, (
        f"Schluessel fehlen im Record: {state_keys - record_keys}; "
        f"ueberzaehlig: {record_keys - state_keys}"
    )


# ---------------------------------------------------------------------------
# save / get
# ---------------------------------------------------------------------------


def test_save_persists_a_record(repo):
    record = _make_record()
    repo.save(record)

    loaded = repo.get(record.simulation_id)
    assert loaded is not None
    assert loaded.simulation_id == record.simulation_id
    assert loaded.project_id == record.project_id


def test_save_advances_updated_at(repo):
    record = _make_record()
    record.updated_at = '2026-01-01T00:00:00'
    repo.save(record)

    loaded = repo.get(record.simulation_id)
    assert loaded is not None
    assert loaded.updated_at > '2026-01-01T00:00:00'


def test_get_returns_none_for_unknown_id(repo):
    """Ein fehlendes Datensatz ist ein erwarteter Fall, kein Fehler."""
    assert repo.get('sim_gibtesnicht00') is None


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_all_records_without_filter(repo):
    repo.save(_make_record('sim_aabbccdd0001', project_id='proj_aaaabbbbcccc'))
    repo.save(_make_record('sim_aabbccdd0002', project_id='proj_ddddeeeeffff'))

    result = repo.list()
    assert len(result) == 2


def test_list_filters_by_project_id(repo):
    repo.save(_make_record('sim_aabbccdd0001', project_id='proj_aaaabbbbcccc'))
    repo.save(_make_record('sim_aabbccdd0002', project_id='proj_ddddeeeeffff'))

    result = repo.list(project_id='proj_aaaabbbbcccc')
    assert len(result) == 1
    assert result[0].simulation_id == 'sim_aabbccdd0001'


def test_list_returns_empty_when_nothing_exists(repo):
    assert repo.list() == []


def test_list_returns_empty_for_unknown_project(repo):
    repo.save(_make_record('sim_aabbccdd0001', project_id='proj_aaaabbbbcccc'))
    assert repo.list(project_id='proj_nichtvorhand') == []


# ---------------------------------------------------------------------------
# list_branches
# ---------------------------------------------------------------------------


def test_list_branches_returns_family_by_root_id(repo):
    root = _make_record('sim_root00000001', root_simulation_id='sim_root00000001')
    branch1 = _make_record(
        'sim_branch000001',
        source_simulation_id='sim_root00000001',
        root_simulation_id='sim_root00000001',
    )
    branch2 = _make_record(
        'sim_branch000002',
        source_simulation_id='sim_root00000001',
        root_simulation_id='sim_root00000001',
    )
    unrelated = _make_record('sim_unrelated0001', root_simulation_id='sim_unrelated0001')

    for r in [root, branch1, branch2, unrelated]:
        repo.save(r)

    branches = repo.list_branches('sim_root00000001')
    ids = {r.simulation_id for r in branches}

    assert 'sim_root00000001' in ids
    assert 'sim_branch000001' in ids
    assert 'sim_branch000002' in ids
    assert 'sim_unrelated0001' not in ids


def test_list_branches_returns_empty_for_unknown_simulation(repo):
    assert repo.list_branches('sim_gibtesnicht00') == []


def test_list_branches_returns_only_self_for_unbranched_simulation(repo):
    record = _make_record('sim_solo00000001', root_simulation_id='sim_solo00000001')
    repo.save(record)

    branches = repo.list_branches('sim_solo00000001')
    assert len(branches) == 1
    assert branches[0].simulation_id == 'sim_solo00000001'


# ---------------------------------------------------------------------------
# Fabrik
# ---------------------------------------------------------------------------


def test_factory_returns_something_satisfying_the_port_protocol(in_memory_store):
    repository = get_simulation_repository(store=in_memory_store)

    assert isinstance(repository, SimulationRepository)


def test_factory_without_store_returns_file_repository():
    """Ohne Store liefert die Fabrik trotzdem einen gueltigen Adapter."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repository = get_simulation_repository(simulations_dir=tmp)

    assert isinstance(repository, FileSimulationRepository)


# ---------------------------------------------------------------------------
# Altbestand: der fruehere Ladepfad war nachsichtig, der Port muss es bleiben
# ---------------------------------------------------------------------------


def test_get_tolerates_legacy_state_with_nulls_and_missing_fields(in_memory_store):
    """Ein ``state.json`` mit ``null`` in Feldern mit Vorgabewert und ohne
    ``simulation_id``/Zeitstempel war vor dem Port lesbar und bleibt es."""
    in_memory_store.write_json(
        'sim_legacy',
        'state',
        {
            'project_id': 'proj_1',
            'status': 'ready',
            'branch_depth': None,
            'entity_types': None,
            'current_round': None,
            'error': None,
        },
    )
    repo = FileSimulationRepository(simulations_dir=None, store=in_memory_store)

    record = repo.get('sim_legacy')

    assert record is not None
    assert record.simulation_id == 'sim_legacy'
    assert record.branch_depth == 0
    assert record.entity_types == []
    assert record.current_round == 0
    assert record.error is None
    assert record.created_at and record.updated_at
