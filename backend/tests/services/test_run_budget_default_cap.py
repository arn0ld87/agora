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
    DEFAULT_SIM_MAX_TOKENS,
    DIMENSION_TO_REASON,
    ENV_DEFAULT_SIM_MAX_TOKENS,
    BudgetExceededError,
    default_simulation_budget,
    resolve_default_simulation_token_cap,
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
