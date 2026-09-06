"""Regression-Tests für parallele Agent-Config-Batches (Perf-Fix).

Produktionsmessung (armserver): drei sequentielle Agent-Config-Batches
kosteten ~81s (28s + 27s + 26s). Die Batches sind disjunkte Entity-Bereiche
und lesen nur aus dem gemeinsamen, unveränderlichen ``context`` — sie sind
voneinander unabhängig und laufen seit diesem Fix parallel über
``SimulationConfigGenerator._generate_agent_configs_parallel``.

Diese Tests belegen:
- die Batches laufen tatsächlich nebenläufig (max. gleichzeitig aktive
  Aufrufe > 1),
- unter gevent wird der kooperative ``gevent.pool.Pool`` genutzt, ohne
  gevent der ``ThreadPoolExecutor``,
- Ergebnisreihenfolge und Entity-Zuordnung bleiben identisch zur
  sequentiellen Variante,
- ein Fehler in einem Batch propagiert nach außen statt still verschluckt
  zu werden.

Kein echtes LLM, kein echtes Neo4j.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import patch

import pytest

from app.services.entity_reader import EntityNode
from app.services.simulation_config_generator import (
    AgentActivityConfig,
    SimulationConfigGenerator,
)


def _make_entities(n: int) -> list[EntityNode]:
    return [
        EntityNode(
            uuid=f"e-{i}",
            name=f"Entity {i}",
            labels=["Person"],
            summary="",
            attributes={},
        )
        for i in range(n)
    ]


def _make_generator(monkeypatch: pytest.MonkeyPatch) -> SimulationConfigGenerator:
    monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
    with patch("app.llm.client.OpenAI"):
        return SimulationConfigGenerator(
            api_key="test-key", base_url="http://localhost:11434/v1"
        )


class TestAgentConfigBatchesRunConcurrently:
    """Beweist echte Nebenläufigkeit über einen Concurrency-Zähler."""

    def _concurrency_probe(self, monkeypatch: pytest.MonkeyPatch, is_gevent: bool) -> int:
        gen = _make_generator(monkeypatch)

        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_batch(self, context, entities, start_idx, simulation_requirement):  # noqa: ARG001
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            # Kleine, aber deterministische "Arbeit" — genug Zeit, damit
            # sich überlappende Aufrufe im Zähler zeigen können. Unter
            # gevent muss kooperativ (``gevent.sleep``) statt blockierend
            # (``time.sleep``) gewartet werden, sonst laufen die Greenlets
            # mangels eines echten ``monkey.patch_all()`` in diesem
            # Testprozess strikt nacheinander (kein Yield an den Hub).
            if is_gevent:
                import gevent

                gevent.sleep(0.05)
            else:
                time.sleep(0.05)
            with lock:
                active -= 1
            return [
                AgentActivityConfig(
                    agent_id=start_idx + i,
                    entity_uuid=e.uuid,
                    entity_name=e.name,
                    entity_type="Person",
                )
                for i, e in enumerate(entities)
            ]

        entities = _make_entities(15)  # AGENTS_PER_BATCH=5 -> 3 Batches
        batch_ranges = [(0, 5), (5, 10), (10, 15)]

        gevent_patch = patch(
            "gevent.monkey.is_module_patched", return_value=is_gevent
        )
        with (
            gevent_patch,
            patch.object(
                SimulationConfigGenerator,
                "_generate_agent_configs_batch",
                side_effect=fake_batch,
                autospec=True,
            ),
        ):
            gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement="req",
            )

        return max_active

    def test_batches_overlap_under_thread_pool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        max_active = self._concurrency_probe(monkeypatch, is_gevent=False)
        assert max_active > 1, (
            "Batches liefen nacheinander statt parallel "
            f"(max. gleichzeitig aktiv: {max_active})"
        )

    def test_batches_overlap_under_gevent_pool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        max_active = self._concurrency_probe(monkeypatch, is_gevent=True)
        assert max_active > 1, (
            "Batches liefen unter gevent nacheinander statt parallel "
            f"(max. gleichzeitig aktiv: {max_active})"
        )


class TestPoolSelection:
    """Gevent-Erkennung über ``is_module_patched('socket')`` steuert die Pool-Wahl."""

    def test_uses_gevent_pool_when_monkey_patched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(10)
        batch_ranges = [(0, 5), (5, 10)]

        with (
            patch("gevent.monkey.is_module_patched", return_value=True),
            patch.object(
                SimulationConfigGenerator, "_generate_agent_configs_batch", return_value=[]
            ),
            patch("gevent.pool.Pool") as mock_pool_cls,
            patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_cls,
        ):
            mock_pool = mock_pool_cls.return_value
            mock_pool.map.return_value = [[], []]

            gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement="req",
            )

            mock_pool_cls.assert_called_once()
            mock_pool.join.assert_called_once()
            mock_executor_cls.assert_not_called()

    def test_uses_thread_pool_executor_without_gevent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(10)
        batch_ranges = [(0, 5), (5, 10)]

        with (
            patch("gevent.monkey.is_module_patched", return_value=False),
            patch.object(
                SimulationConfigGenerator, "_generate_agent_configs_batch", return_value=[]
            ),
            patch("gevent.pool.Pool") as mock_pool_cls,
            patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_cls,
        ):
            mock_executor = mock_executor_cls.return_value.__enter__.return_value
            mock_executor.map.return_value = [[], []]

            gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement="req",
            )

            mock_executor_cls.assert_called_once()
            mock_pool_cls.assert_not_called()

    def test_gevent_import_error_falls_back_to_thread_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``from gevent import monkey`` schlägt fehl -> enger Fallback auf Thread-Pfad."""
        gen = _make_generator(monkeypatch)
        entities = _make_entities(10)
        batch_ranges = [(0, 5), (5, 10)]

        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any):
            if name == "gevent" or name.startswith("gevent."):
                raise ImportError("gevent not installed (simulated)")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch.object(
                SimulationConfigGenerator, "_generate_agent_configs_batch", return_value=[]
            ),
            patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_cls,
        ):
            mock_executor = mock_executor_cls.return_value.__enter__.return_value
            mock_executor.map.return_value = [[], []]

            gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement="req",
            )

            mock_executor_cls.assert_called_once()


class TestResultOrderMatchesSequentialVariant:
    """Ergebnisreihenfolge und Entity-Zuordnung bleiben deterministisch."""

    def test_order_and_entity_mapping_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(13)  # 5,5,3
        batch_ranges = [(0, 5), (5, 10), (10, 13)]

        def fake_batch(self, context, entities, start_idx, simulation_requirement):  # noqa: ARG001
            # Langsamerer Batch zuerst starten lassen, damit ein evtl.
            # "erste-fertig-zuerst"-Bug (imap_unordered ohne Reordering)
            # sichtbar würde.
            if start_idx == 0:
                time.sleep(0.08)
            elif start_idx == 5:
                time.sleep(0.02)
            return [
                AgentActivityConfig(
                    agent_id=start_idx + i,
                    entity_uuid=e.uuid,
                    entity_name=e.name,
                    entity_type="Person",
                )
                for i, e in enumerate(entities)
            ]

        with (
            patch("gevent.monkey.is_module_patched", return_value=False),
            patch.object(
                SimulationConfigGenerator,
                "_generate_agent_configs_batch",
                autospec=True,
                side_effect=fake_batch,
            ),
        ):
            result = gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement="req",
            )

        # Erwartete sequentielle Referenz: direkt hintereinander aufgerufen.
        expected_agent_ids = list(range(13))
        expected_names = [e.name for e in entities]

        assert [c.agent_id for c in result] == expected_agent_ids
        assert [c.entity_name for c in result] == expected_names
        assert [c.entity_uuid for c in result] == [e.uuid for e in entities]

    def test_single_batch_skips_pool_but_matches_sequential_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(4)

        with patch.object(
            SimulationConfigGenerator,
            "_generate_agent_configs_batch",
            return_value=[
                AgentActivityConfig(
                    agent_id=i, entity_uuid=e.uuid, entity_name=e.name, entity_type="Person"
                )
                for i, e in enumerate(entities)
            ],
        ) as mock_batch:
            result = gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=[(0, 4)],
                simulation_requirement="req",
            )

        mock_batch.assert_called_once_with(
            context="ctx", entities=entities[0:4], start_idx=0, simulation_requirement="req"
        )
        assert len(result) == 4


class TestHardBudgetCapsConcurrentDispatch:
    """Codex-Finding auf PR #1452 (P1).

    Ohne Deckelung prüfen alle Greenlets/Threads
    ``LLMClient._budget_check()`` gegen denselben Vor-Aufruf-Stand, bevor
    irgendeine Antwort ihre Nutzung verbucht — bei einem harten
    ``max_llm_calls``-Budget mit weniger verbleibenden Calls als parallelen
    Batches kann ``Pool.map``/``ThreadPoolExecutor.map`` dadurch mehr
    Requests starten, als das Budget erlaubt. Der Fix deckelt die Anzahl
    gleichzeitig gestarteter Batches auf
    ``LLMClient.remaining_hard_call_budget()`` (hier gemockt) — diese Tests
    belegen per Concurrency-Probe, dass nie mehr Batches gleichzeitig aktiv
    sind als das gemockte Restbudget zulässt.
    """

    def _concurrency_probe_with_budget(
        self,
        monkeypatch: pytest.MonkeyPatch,
        is_gevent: bool,
        remaining_budget: int,
    ) -> int:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(25)  # AGENTS_PER_BATCH=5 -> 5 Batches
        batch_ranges = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25)]

        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_batch(self, context, entities, start_idx, simulation_requirement):  # noqa: ARG001
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            if is_gevent:
                import gevent

                gevent.sleep(0.05)
            else:
                time.sleep(0.05)
            with lock:
                active -= 1
            return []

        with (
            patch("gevent.monkey.is_module_patched", return_value=is_gevent),
            patch.object(
                gen.llm_client,
                "remaining_hard_call_budget",
                return_value=remaining_budget,
            ),
            patch.object(
                SimulationConfigGenerator,
                "_generate_agent_configs_batch",
                side_effect=fake_batch,
                autospec=True,
            ),
        ):
            gen._generate_agent_configs_parallel(
                context="ctx",
                entities=entities,
                batch_ranges=batch_ranges,
                simulation_requirement="req",
            )

        return max_active

    def test_thread_pool_never_exceeds_remaining_hard_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        max_active = self._concurrency_probe_with_budget(
            monkeypatch, is_gevent=False, remaining_budget=2
        )
        assert max_active <= 2, (
            "Mehr Batches liefen gleichzeitig als das harte Restbudget erlaubte "
            f"(max. gleichzeitig aktiv: {max_active}, Budget: 2)"
        )

    def test_gevent_pool_never_exceeds_remaining_hard_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        max_active = self._concurrency_probe_with_budget(
            monkeypatch, is_gevent=True, remaining_budget=2
        )
        assert max_active <= 2, (
            "Mehr Batches liefen unter gevent gleichzeitig als das harte "
            f"Restbudget erlaubte (max. gleichzeitig aktiv: {max_active}, Budget: 2)"
        )

    def test_exhausted_budget_still_dispatches_one_batch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Restbudget 0 darf den Lauf nicht stillschweigend leer durchlaufen lassen.

        Ein Batch muss weiterhin starten, damit ``BudgetExceededError`` beim
        nächsten ``_budget_check()`` regulär durchschlägt statt durch eine
        Pool-Größe 0 verschluckt zu werden.
        """
        max_active = self._concurrency_probe_with_budget(
            monkeypatch, is_gevent=False, remaining_budget=0
        )
        assert max_active == 1


class TestBatchFailurePropagates:
    """Ein Fehler in einem Batch darf nicht still verschluckt werden."""

    def test_exception_in_one_batch_propagates_thread_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(10)
        batch_ranges = [(0, 5), (5, 10)]

        def fake_batch(self, context, entities, start_idx, simulation_requirement):  # noqa: ARG001
            if start_idx == 5:
                raise RuntimeError("boom: batch 2 blew up")
            return []

        with (
            patch("gevent.monkey.is_module_patched", return_value=False),
            patch.object(
                SimulationConfigGenerator,
                "_generate_agent_configs_batch",
                autospec=True,
                side_effect=fake_batch,
            ),
        ):
            with pytest.raises(RuntimeError, match="boom: batch 2 blew up"):
                gen._generate_agent_configs_parallel(
                    context="ctx",
                    entities=entities,
                    batch_ranges=batch_ranges,
                    simulation_requirement="req",
                )

    def test_exception_in_one_batch_propagates_gevent_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gen = _make_generator(monkeypatch)
        entities = _make_entities(10)
        batch_ranges = [(0, 5), (5, 10)]

        def fake_batch(self, context, entities, start_idx, simulation_requirement):  # noqa: ARG001
            if start_idx == 5:
                raise RuntimeError("boom: gevent batch blew up")
            return []

        with (
            patch("gevent.monkey.is_module_patched", return_value=True),
            patch.object(
                SimulationConfigGenerator,
                "_generate_agent_configs_batch",
                autospec=True,
                side_effect=fake_batch,
            ),
        ):
            with pytest.raises(RuntimeError, match="boom: gevent batch blew up"):
                gen._generate_agent_configs_parallel(
                    context="ctx",
                    entities=entities,
                    batch_ranges=batch_ranges,
                    simulation_requirement="req",
                )
