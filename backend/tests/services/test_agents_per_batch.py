"""Regression-Tests für AGENTS_PER_BATCH (Issue #870).

Vorgabe: Default 8 (vorher 15), über ``AGORA_AGENTS_PER_BATCH`` überschreibbar.
Die Batching-Logik (``math.ceil(len / AGENTS_PER_BATCH)`` und das Slicing
``start_idx = batch_idx * AGENTS_PER_BATCH`` / ``end_idx = min(...)``) bleibt
unverändert — nur die Konstante/der Default ändert sich.
"""

from __future__ import annotations

import math

from app.services.simulation_config_generator import SimulationConfigGenerator


class TestResolveAgentsPerBatch:
    """ENV-Auflösung ohne Instanziierung (kein LLM-Client nötig)."""

    def test_default_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_default_when_env_empty(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_override_to_5(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 5

    def test_override_to_8_explicit(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "8")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_non_int_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "abc")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_zero_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "0")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8

    def test_negative_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "-3")
        assert SimulationConfigGenerator._resolve_agents_per_batch() == 8


class TestBatchingMath:
    """Sichert die Batching-Logik mit dem neuen Default/Override ab.

    Wir testen nicht ``generate_config`` (das braucht LLM-Mocks), sondern
    rechnen dieselbe Formel nach, die ``generate_config`` verwendet —
    mit dem aufgelösten Wert als Konstante. Das deckt die Edge-Cases
    (len < batch → 1 Batch; genaue Teilbarkeit; Rest-Batch) ab.
    """

    def test_default_8_one_batch_when_below_threshold(self, monkeypatch) -> None:
        """Edge-Case: len < AGENTS_PER_BATCH → genau 1 Batch."""
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 8
        num_entities = 5
        num_batches = math.ceil(num_entities / batch)
        assert num_batches == 1

    def test_default_8_exact_multiple(self, monkeypatch) -> None:
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 8
        assert math.ceil(16 / batch) == 2
        assert math.ceil(24 / batch) == 3

    def test_default_8_partial_last_batch(self, monkeypatch) -> None:
        monkeypatch.delenv("AGORA_AGENTS_PER_BATCH", raising=False)
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 8
        # 20 / 8 = 2.5 → 3 Batches (8, 8, 4)
        assert math.ceil(20 / batch) == 3

    def test_override_5_changes_batch_count(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 5
        # 20 / 5 = 4 Batches (exakt), vs. 3 bei batch=8
        assert math.ceil(20 / batch) == 4

    def test_override_5_one_batch_when_below_threshold(self, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        assert batch == 5
        assert math.ceil(3 / batch) == 1

    def test_slicing_uses_resolved_value(self, monkeypatch) -> None:
        """Slicing wie in generate_config: start_idx = i*batch, end_idx = min(...)."""
        monkeypatch.setenv("AGORA_AGENTS_PER_BATCH", "5")
        batch = SimulationConfigGenerator._resolve_agents_per_batch()
        num_entities = 12
        num_batches = math.ceil(num_entities / batch)
        # Erwartete Slices: [0:5], [5:10], [10:12]
        slices = []
        for i in range(num_batches):
            start = i * batch
            end = min(start + batch, num_entities)
            slices.append((start, end))
        assert slices == [(0, 5), (5, 10), (10, 12)]
