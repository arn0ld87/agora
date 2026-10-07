"""Contract-Tests für den 409-Body der Interview-Endpunkte (#1805, F6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.dump_schemas import CONTRACTS, render_schema
from app.contracts.interview_budget_exceeded_contract import (
    InterviewBudgetExceededResponse,
)
from app.services.run_budget import BudgetExceededError

SCHEMA_FILE = "interview-budget-exceeded.schema.json"


def _body(**overrides):
    base = {
        "error": "Tokenbudget überschritten: 21000000 >= 20000000",
        "termination_reason": "budget_tokens",
        "dimension": "tokens",
        "observed": 21_000_000,
        "threshold": 20_000_000,
    }
    base.update(overrides)
    return base


def test_defaults_are_fixed_envelope_values():
    body = InterviewBudgetExceededResponse.model_validate(_body())

    assert body.success is False
    assert body.code == "budget_exceeded"
    assert body.persisted_count == 0


def test_wire_form_is_flat_and_complete():
    body = InterviewBudgetExceededResponse.model_validate(_body(persisted_count=2))

    assert body.model_dump(mode="json") == {
        "success": False,
        "error": "Tokenbudget überschritten: 21000000 >= 20000000",
        "code": "budget_exceeded",
        "termination_reason": "budget_tokens",
        "dimension": "tokens",
        "observed": 21_000_000,
        "threshold": 20_000_000,
        "persisted_count": 2,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"success": True},
        {"code": "internal_error"},
        {"dimension": "memory"},
        {"termination_reason": "user_stop_please"},
        {"persisted_count": -1},
        {"error": ""},
        {"unexpected": 1},
    ],
)
def test_invalid_bodies_are_rejected(overrides):
    with pytest.raises(ValidationError):
        InterviewBudgetExceededResponse.model_validate(_body(**overrides))


@pytest.mark.parametrize("dimension", ["tokens", "cost", "time", "calls"])
def test_every_budget_exceeded_error_dimension_fits_the_contract(dimension):
    exc = BudgetExceededError(dimension, observed=5, threshold=3)
    exc.persisted_count = 1

    body = InterviewBudgetExceededResponse.model_validate(
        {
            "error": str(exc),
            "termination_reason": exc.termination_reason,
            "dimension": exc.dimension,
            "observed": exc.observed,
            "threshold": exc.threshold,
            "persisted_count": exc.persisted_count,
        }
    )

    assert body.termination_reason == f"budget_{dimension}"


def test_persisted_count_defaults_to_zero_on_the_exception():
    assert BudgetExceededError("calls", 1, 1).persisted_count == 0


def test_schema_is_registered_and_checked_in():
    assert CONTRACTS[SCHEMA_FILE] is InterviewBudgetExceededResponse
    repo_root = Path(__file__).resolve().parents[3]
    on_disk = (repo_root / "schemas" / SCHEMA_FILE).read_text(encoding="utf-8")
    assert on_disk == render_schema(SCHEMA_FILE, InterviewBudgetExceededResponse)
    schema = json.loads(on_disk)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "error",
        "termination_reason",
        "dimension",
        "observed",
        "threshold",
    }
