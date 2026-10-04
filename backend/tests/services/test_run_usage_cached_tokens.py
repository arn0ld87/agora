"""Gecachte Eingabe-Tokens in Call-Event-Vertrag und Usage-Zusammenfassung (#1772)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts.llm_call_event_contract import LlmCallEvent
from app.contracts.run_budget_contract import RunUsage, UsageMetrics
from app.services.pricing_registry import PricingRegistry
from app.services.run_usage_ledger import aggregate_usage


@pytest.fixture()
def pricing(tmp_path: Path) -> PricingRegistry:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(
            {
                "pricing_version": "2099-01",
                "pricing_source": "test-fixture",
                "providers": {
                    "openai": [{"match": "gpt-4o-mini", "input": 150000, "output": 600000}]
                },
            }
        ),
        encoding="utf-8",
    )
    return PricingRegistry(data_path=path)


def _event(**overrides) -> dict:
    base = {
        "stage": "simulation_rounds",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "base_url_sanitized": "https://api.openai.com",
        "timestamp": 1_700_000_000.0,
        "latency_ms": 100.0,
        "success": True,
        "prompt_tokens": 1000,
        "completion_tokens": 50,
    }
    base.update(overrides)
    return base


class TestCallEventContract:
    def _required(self) -> dict:
        return {
            "run_id": "run_1",
            "stage": "simulation_rounds",
            "provider_id": "openai",
            "model": "gpt-4o-mini",
            "routing_version": 0,
            "timestamp": 1_700_000_000.0,
            "latency_ms": 12.0,
            "success": True,
        }

    def test_field_is_optional_with_default_none(self):
        event = LlmCallEvent.model_validate(self._required())
        assert event.cached_input_tokens is None

    def test_old_event_line_without_field_still_loads(self):
        old_line = json.dumps({**self._required(), "prompt_tokens": 10, "completion_tokens": 2})
        event = LlmCallEvent.model_validate_json(old_line)
        assert event.prompt_tokens == 10
        assert event.cached_input_tokens is None

    def test_value_roundtrips_and_negative_is_rejected(self):
        event = LlmCallEvent.model_validate({**self._required(), "cached_input_tokens": 7})
        assert json.loads(event.model_dump_json())["cached_input_tokens"] == 7
        with pytest.raises(ValueError):
            LlmCallEvent.model_validate({**self._required(), "cached_input_tokens": -1})


class TestUsageSummary:
    def test_sum_over_events_that_report_the_value(self, pricing):
        usage = aggregate_usage(
            "run_1",
            events=[
                _event(cached_input_tokens=600),
                _event(cached_input_tokens=0),
                _event(cached_input_tokens=300, stage="report_generation"),
            ],
            pricing=pricing,
        )
        assert usage.totals.cached_input_tokens == 900
        assert usage.by_stage["simulation_rounds"].cached_input_tokens == 600
        assert usage.by_stage["report_generation"].cached_input_tokens == 300
        # Eingabe-Tokens bleiben voll gezaehlt (konservativ).
        assert usage.totals.input_tokens == 3000
        assert usage.totals.total_tokens == 3150

    def test_old_events_without_field_give_none_not_zero(self, pricing):
        usage = aggregate_usage("run_1", events=[_event(), _event()], pricing=pricing)
        assert usage.totals.cached_input_tokens is None
        assert usage.totals.input_tokens == 2000

    def test_mixed_events_sum_only_reported_values(self, pricing):
        usage = aggregate_usage(
            "run_1",
            events=[_event(cached_input_tokens=500), _event(), _event(success=False,
                    prompt_tokens=None, completion_tokens=None)],
            pricing=pricing,
        )
        assert usage.totals.cached_input_tokens == 500

    def test_cost_is_unchanged_by_cached_tokens(self, pricing):
        plain = aggregate_usage("run_1", events=[_event()], pricing=pricing)
        cached = aggregate_usage(
            "run_1", events=[_event(cached_input_tokens=900)], pricing=pricing
        )
        assert plain.totals.cost_micros == cached.totals.cost_micros

    def test_old_persisted_summary_without_field_validates(self, pricing):
        usage = aggregate_usage("run_1", events=[_event()], pricing=pricing)
        raw = usage.model_dump(mode="json")
        for metrics in [raw["totals"], *raw["by_stage"].values()]:
            metrics.pop("cached_input_tokens")
        restored = RunUsage.model_validate(raw)
        assert restored.totals.cached_input_tokens is None

    def test_usage_metrics_default(self):
        assert UsageMetrics().cached_input_tokens is None
