"""Regression-Tests für AGENTS_PER_BATCH (Issue #870).

Vorgabe: Default 8 (vorher 15), über ``AGORA_AGENTS_PER_BATCH`` überschreibbar.
Die Batching-Logik (``math.ceil(len / AGENTS_PER_BATCH)`` und das Slicing
``start_idx = batch_idx * AGENTS_PER_BATCH`` / ``end_idx = min(...)``) bleibt
unverändert — nur die Konstante/der Default ändert sich.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import patch

import pytest

from app.services.entity_reader import EntityNode
from app.services.simulation_config_generator import (
    EventConfig,
    SimulationConfigGenerator,
    TimeSimulationConfig,
    logger as sim_logger,
)


def _assert_agents_per_batch_fallback(
    monkeypatch: pytest.MonkeyPatch, env_value: str
) -> None:
    """ENV auf ``env_value`` setzen, Fallback-Wert + Warnung verifizieren.

    Die Logger-Konfiguration setzt ``propagate=False`` mit eigenen Handlern —
    pytest's ``caplog``-Fixture sieht die Records nur, wenn die Propagation
    temporär eingeschaltet wird. Wir monkey-patchen stattdessen direkt
    ``sim_logger.warning``, damit die Erwartung unabhängig von der
    Logger-Verkabelung ist.
    """
    captured: list[str] = []
    original_warning = sim_logger.warning

    def _spy(msg: str, *args: Any, **kwargs: Any) -> None:
        captured.append(msg % args if args else msg)
        original_warning(msg, *args, **kwargs)

    monkeypatch.setattr(sim_logger, "warning", _spy)
    monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", env_value)
    assert SimulationConfigGenerator._resolve_agents_per_batch() == 8
    assert any("AGORA_AGENTS_PER_BATCH" in w for w in captured)


class TestResolveAgentsPerBatch:
    """ENV-Auflösung ohne Instanziierung (kein LLM-Client nötig)."""

    def test_default_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_default_when_env_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_override_to_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 5

    def test_override_to_8_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "8")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_non_int_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _assert_agents_per_batch_fallback(monkeypatch, "abc")

    def test_zero_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _assert_agents_per_batch_fallback(monkeypatch, "0")

    def test_negative_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _assert_agents_per_batch_fallback(monkeypatch, "-3")


class TestBatchingMath:
    """Sichert die Batching-Logik mit dem neuen Default/Override ab.

    Wir testen nicht ``generate_config`` (das braucht LLM-Mocks), sondern
    rechnen dieselbe Formel nach, die ``generate_config`` verwendet —
    mit dem aufgelösten Wert als Konstante. Das deckt die Edge-Cases
    (len < batch → 1 Batch; genaue Teilbarkeit; Rest-Batch) ab.
    """

    def test_default_8_one_batch_when_below_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Edge-Case: len < AGENTS_PER_BATCH → genau 1 Batch."""
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 8
        num_entities = 5
        num_batches = math.ceil(num_entities / batch)
        assert num_batches == 1

    def test_default_8_exact_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 8
        assert math.ceil(16 / batch) == 2
        assert math.ceil(24 / batch) == 3

    def test_default_8_partial_last_batch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 8
        # 20 / 8 = 2.5 → 3 Batches (8, 8, 4)
        assert math.ceil(20 / batch) == 3

    def test_override_5_changes_batch_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 5
        # 20 / 5 = 4 Batches (exakt), vs. 3 bei batch=8
        assert math.ceil(20 / batch) == 4

    def test_override_5_one_batch_when_below_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 5
        assert math.ceil(3 / batch) == 1

    def test_slicing_uses_resolved_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reale Batching-Schleife in ``generate_config`` mit gemockten LLM-Schritten.

        Wir zeichnen die an ``_generate_agent_configs_batch`` übergebenen
        Entity-Batches auf und verifizieren, dass ``generate_config`` für
        ``len=12, AGENTS_PER_BATCH=5`` exakt ``[0:5]``, ``[5:10]`` und
        ``[10:12]`` weiterreicht. Damit ist das Slicing an die
        Produktionsschleife gekoppelt, nicht an eine lokale Kopie der Formel.
        """
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        # Floor-Check (>=30 Personas) ist hier nicht relevant — wir patchen ihn
        # auf einen No-op, statt ``AGORA_ALLOW_SMALL_SIM`` global zu setzen.
        captured: list[list[EntityNode]] = []

        def fake_batch(self, context, entities, start_idx, simulation_requirement):  # type: ignore[no-untyped-def]  # noqa: ARG001
            captured.append(list(entities))
            return []

        fake_time = TimeSimulationConfig()
        fake_event = EventConfig()

        with (
            patch("app.llm.client.OpenAI"),
            patch.object(
                SimulationConfigGenerator, "_generate_time_config", return_value={}
            ),
            patch.object(
                SimulationConfigGenerator,
                "_parse_time_config",
                return_value=fake_time,
            ),
            patch.object(
                SimulationConfigGenerator, "_generate_event_config", return_value={}
            ),
            patch.object(
                SimulationConfigGenerator,
                "_parse_event_config",
                return_value=fake_event,
            ),
            patch.object(
                SimulationConfigGenerator,
                "_generate_agent_configs_batch",
                autospec=True,
                side_effect=fake_batch,
            ),
            patch.object(
                SimulationConfigGenerator,
                "_validate_persona_quota",
                staticmethod(lambda personas: None),
            ),
            patch.object(
                SimulationConfigGenerator,
                "_ensure_skeptic_quota",
                staticmethod(lambda personas: personas),
            ),
            patch.object(
                SimulationConfigGenerator,
                "_assign_initial_post_agents",
                lambda self, event_config, agent_configs: event_config,
            ),
        ):
            gen = SimulationConfigGenerator(
                api_key="test-key", base_url="http://localhost:11434/v1"
            )
            entities = [
                EntityNode(
                    uuid=f"e-{i}",
                    name=f"Entity {i}",
                    labels=["Person"],
                    summary="",
                    attributes={},
                )
                for i in range(12)
            ]
            gen.generate_config(
                simulation_id="sim-1",
                project_id="proj-1",
                graph_id="graph-1",
                simulation_requirement="test",
                document_text="",
                entities=entities,
            )

        # Drei Batches: [0:5], [5:10], [10:12]
        assert [len(b) for b in captured] == [5, 5, 2]
        assert [e.name for e in captured[0]] == [f"Entity {i}" for i in range(0, 5)]
        assert [e.name for e in captured[1]] == [f"Entity {i}" for i in range(5, 10)]
        assert [e.name for e in captured[2]] == [f"Entity {i}" for i in range(10, 12)]
