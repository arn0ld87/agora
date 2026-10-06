"""Tests für den harten Standard-Tokendeckel der Simulation (Issue #1772)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

from app.api import simulation_run as sim_run
from app.contracts.run_budget_contract import RunBudgetConfig
from app.services.run_budget import (
    DEFAULT_SIM_BUDGET_ENFORCEMENT,
    DEFAULT_SIM_MAX_TOKENS,
    DIMENSION_TO_REASON,
    ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT,
    ENV_DEFAULT_SIM_MAX_COST_MICROS,
    ENV_DEFAULT_SIM_MAX_DURATION_SECONDS,
    ENV_DEFAULT_SIM_MAX_LLM_CALLS,
    ENV_DEFAULT_SIM_MAX_TOKENS,
    BudgetExceededError,
    default_simulation_budget,
    resolve_default_run_budget,
    resolve_default_simulation_token_cap,
)

ALL_DEFAULT_KEYS = (
    ENV_DEFAULT_SIM_MAX_TOKENS,
    ENV_DEFAULT_SIM_MAX_COST_MICROS,
    ENV_DEFAULT_SIM_MAX_DURATION_SECONDS,
    ENV_DEFAULT_SIM_MAX_LLM_CALLS,
    ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sim_runtime.budget_guard import SubprocessBudgetGuard  # noqa: E402


@pytest.fixture()
def run_budget_records():
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    target = logging.getLogger("agora.run_budget")
    handler = _Collect(level=logging.WARNING)
    target.addHandler(handler)
    try:
        yield records
    finally:
        target.removeHandler(handler)


class TestDefaultBudget:
    def test_default_is_20_million_hard_tokens(self):
        budget = default_simulation_budget({}.get)
        assert DEFAULT_SIM_MAX_TOKENS == 20_000_000
        assert budget is not None
        assert budget.max_tokens == 20_000_000
        assert budget.enforcement == "hard"
        # Der Standard setzt NUR den Tokendeckel.
        assert budget.max_cost_micros is None
        assert budget.max_duration_seconds is None
        assert budget.max_llm_calls is None

    def test_override_value(self):
        values = {ENV_DEFAULT_SIM_MAX_TOKENS: 5_000_000}
        budget = default_simulation_budget(values.get)
        assert budget is not None and budget.max_tokens == 5_000_000

    def test_string_value_from_env_is_accepted(self):
        values = {ENV_DEFAULT_SIM_MAX_TOKENS: "7500000"}
        assert resolve_default_simulation_token_cap(values.get) == 7_500_000

    def test_zero_disables_the_default(self):
        values = {ENV_DEFAULT_SIM_MAX_TOKENS: 0}
        assert resolve_default_simulation_token_cap(values.get) is None
        assert default_simulation_budget(values.get) is None

    @pytest.mark.parametrize("raw", [-1, "viel", True, -2.5])
    def test_invalid_value_falls_back_to_default_and_logs(self, raw, run_budget_records):
        values = {ENV_DEFAULT_SIM_MAX_TOKENS: raw}
        assert resolve_default_simulation_token_cap(values.get) == DEFAULT_SIM_MAX_TOKENS
        assert any(ENV_DEFAULT_SIM_MAX_TOKENS in r.getMessage() for r in run_budget_records)

    def test_settings_layer_default_and_env_override(self, monkeypatch):
        monkeypatch.delenv(ENV_DEFAULT_SIM_MAX_TOKENS, raising=False)
        assert resolve_default_simulation_token_cap() == DEFAULT_SIM_MAX_TOKENS
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_TOKENS, "0")
        assert resolve_default_simulation_token_cap() is None
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_TOKENS, "123456")
        assert resolve_default_simulation_token_cap() == 123_456

    def test_schema_default_matches_constant(self):
        from app.services.settings_schema import field_by_key

        spec = field_by_key(ENV_DEFAULT_SIM_MAX_TOKENS)
        assert spec is not None
        assert spec.default == DEFAULT_SIM_MAX_TOKENS


class TestResolveDefaultRunBudget:
    """Standardgrenzen fuer Kosten, Zeit und Aufrufe (Issue #1799)."""

    def test_defaults_yield_exactly_todays_budget(self):
        # Regression: ohne weitere Einstellungen bleibt es beim harten 20-Mio-Tokendeckel.
        budget = resolve_default_run_budget({}.get)
        assert budget == RunBudgetConfig.model_validate(
            {"max_tokens": 20_000_000, "enforcement": "hard"}
        )
        assert budget == default_simulation_budget({}.get)

    def test_settings_layer_defaults_yield_todays_budget(self, monkeypatch):
        for key in ALL_DEFAULT_KEYS:
            monkeypatch.delenv(key, raising=False)
        budget = resolve_default_run_budget()
        assert budget is not None
        assert budget == RunBudgetConfig.model_validate(
            {"max_tokens": 20_000_000, "enforcement": "hard"}
        )
        assert budget.model_dump(exclude_none=True, exclude={"schema_version", "currency"}) == {
            "max_tokens": 20_000_000,
            "enforcement": "hard",
        }

    @pytest.mark.parametrize(
        ("key", "field", "value"),
        [
            (ENV_DEFAULT_SIM_MAX_COST_MICROS, "max_cost_micros", 5_000_000),
            (ENV_DEFAULT_SIM_MAX_DURATION_SECONDS, "max_duration_seconds", 3600),
            (ENV_DEFAULT_SIM_MAX_LLM_CALLS, "max_llm_calls", 500),
        ],
    )
    def test_each_new_limit_alone(self, key, field, value):
        budget = resolve_default_run_budget({key: value}.get)
        assert budget is not None
        assert getattr(budget, field) == value
        assert budget.max_tokens == 20_000_000  # Tokendeckel bleibt unberuehrt
        for other in {"max_cost_micros", "max_duration_seconds", "max_llm_calls"} - {field}:
            assert getattr(budget, other) is None

    def test_all_limits_together_from_strings(self):
        values = {
            ENV_DEFAULT_SIM_MAX_TOKENS: "1000",
            ENV_DEFAULT_SIM_MAX_COST_MICROS: "2000000",
            ENV_DEFAULT_SIM_MAX_DURATION_SECONDS: "600",
            ENV_DEFAULT_SIM_MAX_LLM_CALLS: "50",
            ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT: "soft",
        }
        budget = resolve_default_run_budget(values.get)
        assert budget is not None
        assert (
            budget.max_tokens,
            budget.max_cost_micros,
            budget.max_duration_seconds,
            budget.max_llm_calls,
            budget.enforcement,
        ) == (1000, 2_000_000, 600, 50, "soft")

    def test_zero_means_no_limit_per_dimension(self):
        values = {
            ENV_DEFAULT_SIM_MAX_TOKENS: 0,
            ENV_DEFAULT_SIM_MAX_COST_MICROS: 0,
            ENV_DEFAULT_SIM_MAX_DURATION_SECONDS: 120,
            ENV_DEFAULT_SIM_MAX_LLM_CALLS: 0,
        }
        budget = resolve_default_run_budget(values.get)
        assert budget is not None
        assert budget.max_tokens is None
        assert budget.max_cost_micros is None
        assert budget.max_llm_calls is None
        assert budget.max_duration_seconds == 120

    @pytest.mark.parametrize("enforcement", ["soft", "hard"])
    def test_enforcement_is_applied(self, enforcement):
        values = {ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT: enforcement}
        budget = resolve_default_run_budget(values.get)
        assert budget is not None and budget.enforcement == enforcement

    def test_everything_zero_including_tokens_yields_none(self):
        values = {
            ENV_DEFAULT_SIM_MAX_TOKENS: 0,
            ENV_DEFAULT_SIM_MAX_COST_MICROS: 0,
            ENV_DEFAULT_SIM_MAX_DURATION_SECONDS: 0,
            ENV_DEFAULT_SIM_MAX_LLM_CALLS: 0,
            ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT: "soft",
        }
        assert resolve_default_run_budget(values.get) is None
        assert default_simulation_budget(values.get) is None

    @pytest.mark.parametrize(
        "key",
        [
            ENV_DEFAULT_SIM_MAX_COST_MICROS,
            ENV_DEFAULT_SIM_MAX_DURATION_SECONDS,
            ENV_DEFAULT_SIM_MAX_LLM_CALLS,
        ],
    )
    @pytest.mark.parametrize("raw", [-1, "viel", True, -2.5])
    def test_invalid_new_limit_is_ignored_and_logged(self, key, raw, run_budget_records):
        budget = resolve_default_run_budget({key: raw}.get)
        # Wie beim Tokendeckel: Standard (hier: kein Limit) plus Warnung, nichts still verschluckt.
        assert budget == RunBudgetConfig.model_validate(
            {"max_tokens": 20_000_000, "enforcement": "hard"}
        )
        assert any(key in r.getMessage() for r in run_budget_records)

    @pytest.mark.parametrize("raw", ["strict", "", 1, True])
    def test_invalid_enforcement_falls_back_to_hard_and_logs(self, raw, run_budget_records):
        values = {ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT: raw}
        budget = resolve_default_run_budget(values.get)
        assert budget is not None and budget.enforcement == "hard"
        assert any(
            ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT in r.getMessage() for r in run_budget_records
        )

    def test_invalid_token_cap_still_falls_back_to_default(self, run_budget_records):
        values = {ENV_DEFAULT_SIM_MAX_TOKENS: -5, ENV_DEFAULT_SIM_MAX_LLM_CALLS: 10}
        budget = resolve_default_run_budget(values.get)
        assert budget is not None
        assert budget.max_tokens == DEFAULT_SIM_MAX_TOKENS
        assert budget.max_llm_calls == 10
        assert any(ENV_DEFAULT_SIM_MAX_TOKENS in r.getMessage() for r in run_budget_records)

    def test_settings_layer_reads_env_for_new_keys(self, monkeypatch):
        for key in ALL_DEFAULT_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_LLM_CALLS, "42")
        monkeypatch.setenv(ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT, "soft")
        budget = resolve_default_run_budget()
        assert budget is not None
        assert budget.max_llm_calls == 42
        assert budget.enforcement == "soft"

    def test_schema_fields_live_in_budget_section_with_matching_defaults(self):
        from app.services.settings_schema import field_by_key

        for key in ALL_DEFAULT_KEYS:
            spec = field_by_key(key)
            assert spec is not None, key
            assert spec.section == "budget", key
        assert field_by_key(ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT).default == DEFAULT_SIM_BUDGET_ENFORCEMENT
        for key in (
            ENV_DEFAULT_SIM_MAX_COST_MICROS,
            ENV_DEFAULT_SIM_MAX_DURATION_SECONDS,
            ENV_DEFAULT_SIM_MAX_LLM_CALLS,
        ):
            assert field_by_key(key).default == 0

    def test_new_keys_are_not_in_config_or_agora_settings(self):
        # Kein zweiter Wahrheitsort neben dem Settings-Layer.
        from app.config import Config
        from app.settings import AgoraSettings

        aliases = {f.alias or name.upper() for name, f in AgoraSettings.model_fields.items()}
        for key in (
            ENV_DEFAULT_SIM_MAX_COST_MICROS,
            ENV_DEFAULT_SIM_MAX_DURATION_SECONDS,
            ENV_DEFAULT_SIM_MAX_LLM_CALLS,
            ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT,
        ):
            assert not hasattr(Config, key)
            assert key not in aliases


class TestEffectiveStartBudget:
    def test_default_applies_without_user_budget(self, monkeypatch):
        monkeypatch.delenv(ENV_DEFAULT_SIM_MAX_TOKENS, raising=False)
        budget = sim_run._effective_start_budget(None, "run-1")
        assert budget is not None
        assert budget.max_tokens == DEFAULT_SIM_MAX_TOKENS
        assert budget.enforcement == "hard"

    def test_explicit_user_budget_wins_and_is_not_extended(self, monkeypatch):
        monkeypatch.delenv(ENV_DEFAULT_SIM_MAX_TOKENS, raising=False)
        user = RunBudgetConfig(max_llm_calls=50, enforcement="soft")
        effective = sim_run._effective_start_budget(user, "run-1")
        assert effective is user
        assert effective.max_tokens is None  # kein stillschweigend ergaenzter Deckel
        assert effective.enforcement == "soft"

    def test_user_token_limit_wins_over_default(self, monkeypatch):
        monkeypatch.delenv(ENV_DEFAULT_SIM_MAX_TOKENS, raising=False)
        user = RunBudgetConfig(max_tokens=1_000, enforcement="hard")
        assert sim_run._effective_start_budget(user, "run-1").max_tokens == 1_000

    def test_default_can_be_switched_off(self, monkeypatch):
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_TOKENS, "0")
        assert sim_run._effective_start_budget(None, "run-1") is None

    def test_new_limits_apply_without_user_budget(self, monkeypatch):
        monkeypatch.delenv(ENV_DEFAULT_SIM_MAX_TOKENS, raising=False)
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_COST_MICROS, "3000000")
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_DURATION_SECONDS, "900")
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_LLM_CALLS, "250")
        monkeypatch.setenv(ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT, "soft")
        budget = sim_run._effective_start_budget(None, "run-1")
        assert budget is not None
        assert budget.max_tokens == DEFAULT_SIM_MAX_TOKENS
        assert budget.max_cost_micros == 3_000_000
        assert budget.max_duration_seconds == 900
        assert budget.max_llm_calls == 250
        assert budget.enforcement == "soft"

    def test_user_budget_wins_completely_over_new_limits(self, monkeypatch):
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_COST_MICROS, "3000000")
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_LLM_CALLS, "250")
        user = RunBudgetConfig(max_tokens=1_000, enforcement="hard")
        effective = sim_run._effective_start_budget(user, "run-1")
        assert effective is user
        assert effective.max_cost_micros is None
        assert effective.max_llm_calls is None

    def test_only_new_limit_set_with_tokens_off(self, monkeypatch):
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_TOKENS, "0")
        monkeypatch.setenv(ENV_DEFAULT_SIM_MAX_LLM_CALLS, "250")
        monkeypatch.delenv(ENV_DEFAULT_SIM_BUDGET_ENFORCEMENT, raising=False)
        budget = sim_run._effective_start_budget(None, "run-1")
        assert budget is not None
        assert budget.max_tokens is None
        assert budget.max_llm_calls == 250
        assert budget.enforcement == "hard"

    def test_parse_budget_config_stays_none_without_budget(self):
        # Das Parsen der Anfrage bleibt unveraendert; der Standard greift erst beim Anker.
        assert sim_run._parse_budget_config({}) is None


class TestCapEndsRunWithStructuredReason:
    """Ein per Deckel beendeter Lauf traegt den bestehenden Termination-Reason."""

    def test_budget_exceeded_maps_to_budget_tokens(self):
        exc = BudgetExceededError("tokens", 21_000_000, 20_000_000)
        assert exc.termination_reason == "budget_tokens"
        assert DIMENSION_TO_REASON["tokens"] == "budget_tokens"

    def test_default_budget_roundtrip_trips_the_subprocess_guard(self, tmp_path, monkeypatch):
        # Backend schreibt das Standardbudget als budget_config.json, der
        # Subprozess-Guard liest es und bricht an der Rundengrenze hart ab.
        budget = default_simulation_budget({}.get)
        assert budget is not None
        (tmp_path / "budget_config.json").write_text(budget.model_dump_json(), encoding="utf-8")
        monkeypatch.setenv("AGORA_RUN_ID", "run_default_cap")
        guard = SubprocessBudgetGuard.from_environment(str(tmp_path))
        assert guard is not None
        assert guard.enforcement == "hard"
        assert guard.check_round_boundary(1) is None  # nichts verbraucht

        guard._prompt_tokens = 20_000_000  # Deckel erreicht
        abort = guard.check_round_boundary(7)
        assert abort is not None
        assert abort["dimension"] == "tokens"
        assert abort["threshold"] == 20_000_000
        marker = json.loads((tmp_path / "budget_abort.json").read_text(encoding="utf-8"))
        assert marker["dimension"] == "tokens"
        # ... und der Monitor mappt diese Dimension auf budget_tokens.
        assert DIMENSION_TO_REASON[marker["dimension"]] == "budget_tokens"
