"""Regression: ein erschoepftes Hartbudget stoppt wartende Persona-Jobs.

Root Cause (vor dem Fix):

* Thread-Pfad — ``_consume_thread_results`` liess ``BudgetExceededError`` aus
  dem ``with ThreadPoolExecutor(...)``-Block heraus propagieren.
  ``ThreadPoolExecutor.__exit__`` ruft ``shutdown(wait=True)`` ohne
  ``cancel_futures``: jede bereits eingereihte, aber noch nicht gestartete
  Persona lief anschliessend trotzdem los und feuerte ihre LLM-Calls ab.
* Gevent-Pfad — ``_consume_gevent_results`` liess den Fehler aus der
  ``imap_unordered``-Schleife laufen und joinete den Pool im ``finally``.
  ``join()`` wartet auf die restlichen Greenlets, statt sie zu stoppen.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional
from uuid import uuid4

import pytest

from app.services import oasis_profile_batch_results as mod
from app.services import llm_routing_seed
from app.services.embedding_configurations.runtime import ResolvedEmbeddingRoute
from app.services.run_budget import BudgetExceededError
from app.storage.embedding_service import EmbeddingError, EmbeddingService


class _Entity:
    def __init__(self, name: str) -> None:
        self.name = name
        self.uuid = f"uuid-{name}"
        self.summary = "summary"

    def get_entity_type(self) -> str:
        return "Person"


class _Self:
    """Minimaler Generator-Doppelgaenger fuer die beiden Verbrauchsschleifen."""

    run_id: Optional[str] = None

    def _generate_username(self, name: str) -> str:
        return name.lower()

    def _cancel_checkpoint(self, completed: int, total: int, path: str) -> bool:
        return False


TOTAL = 10
BUDGET_AT = 1


def _entities() -> List[_Entity]:
    return [_Entity(f"e{i}") for i in range(TOTAL)]


def test_thread_path_cancels_pending_futures_on_budget_exhaustion() -> None:
    started: List[int] = []
    entities = _entities()

    def generate_single_profile(idx: int, entity: _Entity) -> tuple:
        started.append(idx)
        # Steht fuer die LLM-Latenz: ohne sie rast der einzelne Worker-Thread
        # durch alle zehn Futures, bevor der Hauptthread ueberhaupt das erste
        # Ergebnis sieht — dann gaebe es nichts mehr zu canceln und der Test
        # wuerde die Regression nicht messen.
        time.sleep(0.05)
        if idx == BUDGET_AT:
            raise BudgetExceededError("llm_calls", 5, 5)
        return idx, object(), None

    processed: List[int] = []
    completed_count = [0]

    def process_result(result_idx: int, profile: Any, error: Any) -> None:
        processed.append(result_idx)
        completed_count[0] += 1

    with pytest.raises(BudgetExceededError):
        mod._consume_thread_results(
            _Self(),
            generate_single_profile,
            entities,
            1,  # parallel_count=1 => strikt sequentielle Abarbeitung
            process_result,
            completed_count,
            TOTAL,
        )

    # Ohne Cancel laufen alle zehn Personas trotzdem durch.
    assert len(started) < TOTAL, f"pending personas still ran: {started}"
    # 0 und 1 sind gelaufen; hoechstens der eine Worker-Slot hat noch
    # nachgelegt, bevor der Cancel griff.
    assert started[:2] == [0, BUDGET_AT]
    assert len(started) <= BUDGET_AT + 2


def test_gevent_path_stops_pool_on_budget_exhaustion() -> None:
    gevent_pool = pytest.importorskip("gevent.pool")

    started: List[int] = []
    entities = _entities()
    pool = gevent_pool.Pool(1)

    def worker_wrapper(args: tuple) -> tuple:
        idx, _entity = args
        started.append(idx)
        if idx == BUDGET_AT:
            raise BudgetExceededError("llm_calls", 5, 5)
        return idx, object(), None

    completed_count = [0]

    def process_result(result_idx: int, profile: Any, error: Any) -> None:
        completed_count[0] += 1

    with pytest.raises(BudgetExceededError):
        mod._consume_gevent_results(
            _Self(),
            pool,
            worker_wrapper,
            entities,
            process_result,
            completed_count,
            TOTAL,
        )

    # Ueberlebende Greenlets bekommen bewusst noch Rechenzeit: vor dem Fix
    # lief der imap-Produzent nach dem Funktionsaustritt einfach weiter und
    # feuerte die restlichen Persona-Calls ab (orphaned worker).
    import gevent

    gevent.sleep(0.05)

    assert len(started) < TOTAL, f"pending greenlets still ran: {started}"
    # Kein verwaister Worker, kein Deadlock: der Pool ist nach der Rueckkehr leer.
    assert pool.free_count() == pool.size


def test_thread_path_without_budget_error_processes_every_entity() -> None:
    started: List[int] = []
    entities = _entities()

    def generate_single_profile(idx: int, entity: _Entity) -> tuple:
        started.append(idx)
        return idx, object(), None

    completed_count = [0]
    processed: List[int] = []

    cancel_requested = mod._consume_thread_results(
        _Self(),
        generate_single_profile,
        entities,
        3,
        lambda i, p, e: (processed.append(i), completed_count.__setitem__(0, completed_count[0] + 1)),
        completed_count,
        TOTAL,
    )

    assert cancel_requested is False
    assert sorted(started) == list(range(TOTAL))
    assert sorted(processed) == list(range(TOTAL))


@pytest.mark.parametrize(
    ("workspace_key", "expected"),
    [("workspace-key", "Bearer workspace-key"), (None, "missing-workspace-key")],
)
def test_thread_path_uses_workspace_embedding_credential_or_fails_closed(
    monkeypatch, workspace_key, expected
) -> None:
    workspace_id = uuid4()
    monkeypatch.setattr(
        llm_routing_seed, "_persisted_workspace_for_run",
        lambda run_id: (True, workspace_id) if run_id == "run-test" else (False, None),
    )
    monkeypatch.setattr(
        "app.services.embedding_configurations.runtime.resolve_active_embedding_route",
        lambda *, include_secret=True: ResolvedEmbeddingRoute(
            model="text-embedding-3-small",
            base_url="https://api.openai.com/v1",
            api_key="operator-key" if include_secret else None,
            configuration_id="embedding",
            dimensions=1536,
            provider_id="openai",
        ),
    )
    monkeypatch.setattr(
        "app.services.workspace_provider_credentials_store.WorkspaceProviderCredentialsStore",
        lambda: type(
            "Credentials", (),
            {"get_plaintext": lambda _self, current_id, provider_id: workspace_key
             if current_id == workspace_id and provider_id == "openai" else None},
        )(),
    )

    def generate_single_profile(idx: int, entity: _Entity) -> tuple:
        service = EmbeddingService(
            model="text-embedding-3-small",
            base_url="https://api.openai.com/v1",
            api_key="operator-key",
        )
        try:
            result = service._request_headers()["Authorization"]
        except EmbeddingError:
            result = "missing-workspace-key"
        return idx, result, None

    results: list[str] = []
    with llm_routing_seed.workspace_credential_context_for_run("run-test"):
        mod._consume_thread_results(
            _Self(), generate_single_profile, [_Entity("one"), _Entity("two")], 2,
            lambda _idx, profile, _error: results.append(profile), [0], 2,
        )

    assert results == [expected, expected]
