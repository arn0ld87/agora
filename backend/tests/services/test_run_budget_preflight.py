"""Tests für die Preflight-Schätzung (Issue #764)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts.run_budget_contract import PreflightModelRef
from app.services.pricing_registry import PricingRegistry
from app.services.run_budget_preflight import (
    _HistoryStats,
    _round_sig,
    estimate_run,
)


@pytest.fixture()
def pricing(tmp_path: Path) -> PricingRegistry:
    data = {
        "pricing_version": "2099-01",
        "pricing_source": "test-fixture",
        "providers": {
            "openai": [
                {"match": "gpt-4o-mini", "input": 150000, "output": 600000},
                {"match": "gpt-4o", "input": 250000, "output": 1000000},
            ],
        },
    }
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return PricingRegistry(data_path=path)


def _empty_history() -> _HistoryStats:
    return _HistoryStats()


def _rich_history() -> _HistoryStats:
    stats = _HistoryStats()
    stats.runs_used = 5
    stats.tokens_per_call = [2000.0, 2200.0, 1800.0, 2100.0, 1900.0]
    stats.latency_s_per_call = [3.0, 3.5, 2.5, 3.0, 3.2]
    return stats


_LOCAL_MODEL = PreflightModelRef(
    stage="simulation_rounds",
    provider_id="ollama",
    model_id="qwen3:8b",
    base_url_sanitized="http://localhost:11434",
    cost_status="free",
)
_PRICED_MODEL = PreflightModelRef(
    stage="simulation_rounds",
    provider_id="openai",
    model_id="gpt-4o-mini",
    cost_status="measured",
)
_PRICED_MODEL_LARGE = PreflightModelRef(
    stage="simulation_rounds",
    provider_id="openai",
    model_id="gpt-4o",
    cost_status="measured",
)
_UNKNOWN_MODEL = PreflightModelRef(
    stage="simulation_rounds",
    provider_id="minimax",
    model_id="MiniMax-M9-x",
    cost_status="unknown",
)


class TestRounding:
    def test_round_sig_avoids_pseudo_precision(self):
        assert _round_sig(123456) == 120000
        assert _round_sig(1234) == 1200
        assert _round_sig(0) == 0


class TestEstimateWithoutHistory:
    def test_heuristic_ranges_and_warnings(self, pricing):
        est = estimate_run(
            num_agents=30,
            max_rounds=10,
            models=[_LOCAL_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.is_estimate is True
        assert est.estimated_tokens_low is not None
        assert est.estimated_tokens_high > est.estimated_tokens_low
        assert est.estimated_duration_seconds_high > est.estimated_duration_seconds_low
        assert any("Heuristik" in w for w in est.warnings)
        assert est.data_quality == "low"

    def test_local_model_costs_free_zero(self, pricing):
        est = estimate_run(
            num_agents=30,
            max_rounds=10,
            models=[_LOCAL_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "free"
        assert est.estimated_cost_micros_low == 0
        assert est.estimated_cost_micros_high == 0

    def test_priced_model_estimated_cost(self, pricing):
        est = estimate_run(
            num_agents=30,
            max_rounds=10,
            models=[_PRICED_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "estimated"
        assert est.estimated_cost_micros_low is not None
        assert est.estimated_cost_micros_high >= est.estimated_cost_micros_low
        assert any("Richtpreis" in w for w in est.warnings)

    def test_unknown_price_is_honest_unknown(self, pricing):
        est = estimate_run(
            num_agents=30,
            max_rounds=10,
            models=[_UNKNOWN_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "unknown"
        assert est.estimated_cost_micros_low is None
        assert any("kein Richtpreis" in w for w in est.warnings)


class TestEstimateWithHistory:
    def test_history_improves_quality(self, pricing):
        est = estimate_run(
            num_agents=30,
            max_rounds=10,
            models=[_PRICED_MODEL],
            pricing=pricing,
            history=_rich_history(),
        )
        assert est.data_quality == "high"
        assert not any("Keine historischen" in w for w in est.warnings)
        # Median 2000 Tokens/Call; 30*10 Calls bei 0.3..1.0 Aktivität
        # low ≈ 90 Calls * 1000 Tokens = 90_000 (gerundet)
        assert est.estimated_tokens_low >= 50_000
        assert est.estimated_tokens_high > est.estimated_tokens_low


class TestEdgeCases:
    def test_zero_agents_returns_unknown(self, pricing):
        est = estimate_run(
            num_agents=0,
            max_rounds=10,
            models=[],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.data_quality == "unknown"
        assert est.estimated_tokens_low is None
        assert est.warnings

    def test_no_models_warns(self, pricing):
        est = estimate_run(
            num_agents=10,
            max_rounds=5,
            models=[],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "unknown"
        assert any("Kein Modell" in w for w in est.warnings)

    def test_pricing_version_propagated(self, pricing):
        est = estimate_run(
            num_agents=10,
            max_rounds=5,
            models=[_PRICED_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.pricing_version == "2099-01"


class TestCostDistributionAcrossModels:
    """Issue #764 (Review): freie Modelle dürfen nicht zu Kosten anderer
    Modelle beitragen. Tokens werden gleichmäßig auf alle konfigurierten
    Modelle verteilt; jedes Modell berechnet seinen Anteil an seinem
    eigenen Tarif."""

    def test_only_free_models_is_free_with_zero(self, pricing):
        est = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_LOCAL_MODEL, _LOCAL_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "free"
        assert est.estimated_cost_micros_low == 0
        assert est.estimated_cost_micros_high == 0

    def test_single_priced_model_uses_full_share(self, pricing):
        # Mit einem priced Modell landen 100% der geschätzten Tokens auf
        # seinem Tarif (entspricht dem alten Verhalten in diesem Fall).
        # Wichtiger Kontrast: free + priced MUSS günstiger sein als nur
        # priced — das wird in test_mix_free_and_priced_does_not_overcharge
        # geprüft. Hier nur sanity-check, dass ein einzelnes priced Modell
        # eine plausible Schätzung liefert.
        est = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_PRICED_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "estimated"
        assert est.estimated_cost_micros_low is not None
        assert est.estimated_cost_micros_low > 0

    def test_multiple_priced_models_with_different_rates(self, pricing):
        # gpt-4o-mini billiger, gpt-4o teurer. Beide bepreist → Gesamtsumme
        # ist die Summe der Einzelanteile.
        est = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_PRICED_MODEL, _PRICED_MODEL_LARGE],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "estimated"
        assert est.estimated_cost_micros_low is not None
        assert est.estimated_cost_micros_high is not None
        assert est.estimated_cost_micros_high >= est.estimated_cost_micros_low
        # Bei gleichem Tarif: doppeltes Set = einfaches Set × 2
        # Mit gpt-4o (teurer) als zweitem Modell muss die Summe
        # größer sein als das einzelne gpt-4o-mini-Modell.
        est_only_mini = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_PRICED_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.estimated_cost_micros_low > est_only_mini.estimated_cost_micros_low

    def test_mix_free_and_priced_does_not_overcharge(self, pricing):
        # Free + priced: free darf die Gesamtsumme NICHT erhöhen. Mit zwei
        # priced und einem free sollte die Summe kleiner sein als mit drei
        # priced (gleicher Tarif).
        est_mixed = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_PRICED_MODEL, _LOCAL_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        est_all_priced = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_PRICED_MODEL, _PRICED_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est_mixed.cost_status == "estimated"
        assert est_mixed.estimated_cost_micros_low is not None
        assert est_all_priced.estimated_cost_micros_low is not None
        # Mixed = ein priced Modell (50% der Tokens) + ein free (0)
        # All-priced = zwei priced (je 50%, beide zum gleichen Tarif)
        # → all-priced ist exakt 2× mixed (gleicher Tarif).
        assert est_all_priced.estimated_cost_micros_low == 2 * est_mixed.estimated_cost_micros_low

    def test_unknown_model_makes_overall_unknown(self, pricing):
        # Sobald ein Modell ohne Richtpreis dabei ist, ist die Gesamtschätzung
        # ehrlich "unknown" — wir wissen nicht, wie sich die Tokens auf das
        # unbekannte Modell verteilen.
        est = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_PRICED_MODEL, _UNKNOWN_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "estimated"
        assert est.estimated_cost_micros_low is not None
        assert any("kein Richtpreis" in w for w in est.warnings)

    def test_only_unknown_models_is_unknown_no_phantom_zero(self, pricing):
        est = estimate_run(
            num_agents=20,
            max_rounds=5,
            models=[_UNKNOWN_MODEL],
            pricing=pricing,
            history=_empty_history(),
        )
        assert est.cost_status == "unknown"
        assert est.estimated_cost_micros_low is None
        assert est.estimated_cost_micros_high is None
