"""Contract-Tests für den Run-Budget-Contract (Issue #764).

Testet ausschließlich den Vertrag (Defaults, Grenzfälle, negative
Validierung, Serialisierung) — keine Service-Logik.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.run_budget_contract import (
    BudgetWarning,
    PreflightEstimate,
    PreflightModelRef,
    RunBudgetConfig,
    RunBudgetStatus,
    RunUsage,
    UsageMetrics,
)


def _config(**overrides) -> dict:
    base = {"max_tokens": 1000, "enforcement": "hard"}
    base.update(overrides)
    return base


class TestRunBudgetConfig:
    def test_defaults_empty_config_valid(self):
        cfg = RunBudgetConfig()
        assert cfg.schema_version == 1
        assert cfg.max_tokens is None
        assert cfg.max_cost_micros is None
        assert cfg.max_duration_seconds is None
        assert cfg.max_llm_calls is None
        assert cfg.enforcement == "soft"
        assert cfg.currency == "USD"

    def test_all_limits_settable(self):
        cfg = RunBudgetConfig(
            max_tokens=100_000,
            max_cost_micros=5_000_000,
            max_duration_seconds=3600,
            max_llm_calls=50,
            enforcement="hard",
            currency="EUR",
        )
        assert cfg.max_tokens == 100_000
        assert cfg.max_cost_micros == 5_000_000
        assert cfg.max_duration_seconds == 3600
        assert cfg.max_llm_calls == 50

    @pytest.mark.parametrize(
        "field",
        ["max_tokens", "max_cost_micros", "max_duration_seconds", "max_llm_calls"],
    )
    def test_zero_limit_rejected(self, field):
        with pytest.raises(ValidationError):
            RunBudgetConfig(**{field: 0})

    @pytest.mark.parametrize(
        "field",
        ["max_tokens", "max_cost_micros", "max_duration_seconds", "max_llm_calls"],
    )
    def test_negative_limit_rejected(self, field):
        with pytest.raises(ValidationError):
            RunBudgetConfig(**{field: -5})

    def test_float_cost_rejected(self):
        with pytest.raises(ValidationError):
            RunBudgetConfig(max_cost_micros=1.5)  # type: ignore[arg-type]

    def test_invalid_enforcement_rejected(self):
        with pytest.raises(ValidationError):
            RunBudgetConfig(enforcement="medium")  # type: ignore[arg-type]

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            RunBudgetConfig(**_config(unknown_field=True))  # type: ignore[arg-type]

    def test_currency_length_enforced(self):
        with pytest.raises(ValidationError):
            RunBudgetConfig(currency="US")


class TestBudgetWarning:
    def test_valid_warning(self):
        w = BudgetWarning(
            dimension="tokens",
            severity="soft",
            threshold=1000,
            observed=1200,
            message="Tokenlimit überschritten",
            ts="2026-07-29T00:00:00Z",
        )
        assert w.dimension == "tokens"

    def test_invalid_dimension_rejected(self):
        with pytest.raises(ValidationError):
            BudgetWarning(
                dimension="memory",  # type: ignore[arg-type]
                severity="soft",
                threshold=1,
                observed=2,
                message="x",
                ts="2026-07-29T00:00:00Z",
            )


class TestUsageMetrics:
    def test_defaults_are_honest_unknown(self):
        m = UsageMetrics()
        assert m.input_tokens is None
        assert m.output_tokens is None
        assert m.total_tokens is None
        assert m.llm_calls == 0
        assert m.cost_micros is None
        assert m.cost_status == "unknown"
        assert m.tokens_status == "unknown"
        assert m.duration_ms == 0

    def test_negative_values_rejected(self):
        with pytest.raises(ValidationError):
            UsageMetrics(llm_calls=-1)

    def test_cost_status_values(self):
        for status in ("measured", "estimated", "free", "unknown"):
            assert UsageMetrics(cost_status=status).cost_status == status  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            UsageMetrics(cost_status="zero")  # type: ignore[arg-type]


class TestRunUsage:
    def test_minimal_usage(self):
        u = RunUsage(totals=UsageMetrics())
        assert u.schema_version == 1
        assert u.by_stage == {}
        assert u.by_provider == {}
        assert u.by_model == {}
        assert u.measurement_status == "unknown"

    def test_breakdowns(self):
        u = RunUsage(
            totals=UsageMetrics(total_tokens=10, tokens_status="measured"),
            by_stage={"simulation_rounds": UsageMetrics(total_tokens=10, tokens_status="measured")},
            by_provider={"ollama": UsageMetrics(cost_status="free")},
            by_model={"qwen3:8b": UsageMetrics(cost_status="free")},
            measurement_status="partial",
        )
        assert u.by_stage["simulation_rounds"].total_tokens == 10
        assert u.measurement_status == "partial"

    def test_roundtrip_json(self):
        u = RunUsage(totals=UsageMetrics(llm_calls=3, cost_micros=42, cost_status="measured"))
        restored = RunUsage.model_validate_json(u.model_dump_json())
        assert restored.totals.cost_micros == 42


class TestRunBudgetStatus:
    def test_status_defaults(self):
        s = RunBudgetStatus(config=RunBudgetConfig(), consumed=UsageMetrics())
        assert s.status == "ok"
        assert s.exceeded_dimension is None
        assert s.warnings == []

    def test_exceeded_state(self):
        s = RunBudgetStatus(
            config=RunBudgetConfig(max_tokens=10, enforcement="hard"),
            consumed=UsageMetrics(total_tokens=11, tokens_status="measured"),
            status="exceeded",
            exceeded_dimension="tokens",
        )
        assert s.exceeded_dimension == "tokens"


class TestPreflightEstimate:
    def test_estimate_flag_is_pinned_true(self):
        with pytest.raises(ValidationError):
            PreflightEstimate(
                is_estimate=False,  # type: ignore[arg-type]
                pricing_version="2026-07",
                pricing_source="model_pricing.json",
            )

    def test_unknown_estimate_has_no_fake_numbers(self):
        e = PreflightEstimate(pricing_version="2026-07", pricing_source="model_pricing.json")
        assert e.is_estimate is True
        assert e.estimated_tokens_low is None
        assert e.estimated_cost_micros_high is None
        assert e.estimated_duration_seconds_low is None
        assert e.cost_status == "unknown"
        assert e.data_quality == "unknown"

    def test_models_list(self):
        e = PreflightEstimate(
            pricing_version="2026-07",
            pricing_source="model_pricing.json",
            models=[
                PreflightModelRef(
                    stage="simulation_rounds",
                    provider_id="ollama-local",
                    model_id="qwen3:8b",
                    cost_status="free",
                )
            ],
            data_quality="low",
        )
        assert e.models[0].cost_status == "free"
