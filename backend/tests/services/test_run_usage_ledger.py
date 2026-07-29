"""Tests für den Run Usage Ledger (Issue #764)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.pricing_registry import PricingRegistry
from app.services.run_usage_ledger import aggregate_usage, load_call_events


@pytest.fixture()
def pricing(tmp_path: Path) -> PricingRegistry:
    data = {
        "pricing_version": "2099-01",
        "pricing_source": "test-fixture",
        "providers": {
            "openai": [
                {"match": "gpt-4o-mini", "input": 150000, "output": 600000},
            ],
        },
    }
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return PricingRegistry(data_path=path)


def _event(**overrides) -> dict:
    base = {
        "run_id": "run_x",
        "stage": "report_generation",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "base_url_sanitized": "https://api.openai.com",
        "timestamp": 1_700_000_000.0,
        "latency_ms": 120.0,
        "success": True,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
    }
    base.update(overrides)
    return base


class TestAggregation:
    def test_totals_and_breakdowns(self, pricing):
        events = [
            _event(),
            _event(stage="persona_generation", model="gpt-4o-mini"),
            _event(stage="persona_generation", provider_id="ollama",
                   model="qwen3:8b", base_url_sanitized="http://localhost:11434"),
        ]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)

        assert usage.totals.llm_calls == 3
        assert usage.totals.input_tokens == 3000
        assert usage.totals.output_tokens == 1500
        assert usage.totals.total_tokens == 4500
        assert usage.totals.tokens_status == "measured"
        assert usage.totals.duration_ms == 360

        assert set(usage.by_stage) == {"report_generation", "persona_generation"}
        assert usage.by_stage["persona_generation"].llm_calls == 2
        assert set(usage.by_provider) == {"openai", "ollama"}
        assert usage.by_provider["ollama"].cost_status == "free"
        assert usage.by_provider["ollama"].cost_micros == 0

    def test_cost_only_from_measured_tokens_and_prices(self, pricing):
        # 1 Mio Input * 0.15 + 0.5 Mio Output * 0.60 = 0.15 + 0.30 USD = 450_000 micros
        events = [_event(prompt_tokens=1_000_000, completion_tokens=500_000)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.cost_micros == 450_000
        assert usage.totals.cost_status == "measured"
        assert usage.pricing_version == "2099-01"

    def test_missing_tokens_are_unknown_not_zero(self, pricing):
        events = [_event(prompt_tokens=None, completion_tokens=None)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.total_tokens is None
        assert usage.totals.tokens_status == "unknown"
        assert usage.measurement_status == "partial"
        assert usage.totals.llm_calls == 1

    def test_mixed_tokens_partial(self, pricing):
        events = [_event(), _event(prompt_tokens=None, completion_tokens=None)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "partial"
        assert usage.totals.total_tokens == 1500

    def test_unknown_price_is_not_reported_as_zero(self, pricing):
        events = [_event(provider_id="minimax", model="MiniMax-M9-ultra")]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.cost_status == "unknown"
        assert usage.totals.cost_micros is None

    def test_mixed_priced_and_unknown_is_estimated(self, pricing):
        events = [
            _event(),
            _event(provider_id="minimax", model="MiniMax-M9-ultra"),
        ]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.cost_status == "estimated"
        assert usage.totals.cost_micros is not None  # bekannter Anteil ausgewiesen

    def test_failed_calls_not_counted_as_calls_but_duration_kept(self, pricing):
        events = [_event(success=False, latency_ms=50.0)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.llm_calls == 0
        assert usage.totals.duration_ms == 50

    def test_empty_events_unknown(self, pricing):
        usage = aggregate_usage("run_x", events=[], pricing=pricing)
        assert usage.measurement_status == "unknown"
        assert usage.totals.llm_calls == 0
        assert usage.totals.cost_status == "unknown"

    def test_legacy_events_without_token_fields_readable(self, pricing):
        # Schema v0 (vor #764): Events hatten keine Token-Felder.
        legacy = _event()
        legacy.pop("prompt_tokens")
        legacy.pop("completion_tokens")
        usage = aggregate_usage("run_x", events=[legacy], pricing=pricing)
        assert usage.totals.tokens_status == "unknown"
        assert usage.totals.llm_calls == 1


class TestLoadCallEvents:
    def test_tolerates_corrupt_lines(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run_bad"
        run_dir.mkdir()
        (run_dir / "llm_call_events.jsonl").write_text(
            '{"stage": "a", "success": true}\nNOT-JSON\n{"stage": "b"}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "app.services.run_usage_ledger.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(run_dir)),
        )
        events = load_call_events("run_bad")
        assert len(events) == 2

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.services.run_usage_ledger.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(tmp_path / run_id)),
        )
        assert load_call_events("nope") == []
