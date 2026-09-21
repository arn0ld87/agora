"""
Contract-Tests für decision_contract.py (f005, Slice `decision-pilot`,
Task `decision-contracts`).

Kein Schema-Dump/Frontend-Spiegel für dieses Modul: keine Form hier geht
über eine HTTP-Grenze — der Decision Layer ist in diesem Pilot ein
interner Service-zu-Service-Vertrag (ADR-0017, Präzisierung 1).
"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.contracts.decision_contract import (
    ChoiceQuestion,
    DecisionQuestion,
    DecisionResult,
    DecisionState,
    NoulQuestion,
    ScoreQuestion,
)

_question_adapter: TypeAdapter[DecisionQuestion] = TypeAdapter(DecisionQuestion)


class TestDecisionState:
    def test_accepts_string_state(self) -> None:
        state = DecisionState(
            use_case_id="persona-eligibility",
            state="Entität: Bundeskanzleramt (Organisation)",
            context_hash="sha256:abc123",
        )
        assert state.use_case_id == "persona-eligibility"

    def test_accepts_dict_and_list_state(self) -> None:
        DecisionState(use_case_id="u", state={"a": 1}, context_hash="h")
        DecisionState(use_case_id="u", state=[1, 2, 3], context_hash="h")

    def test_rejects_empty_use_case_id(self) -> None:
        with pytest.raises(ValidationError):
            DecisionState(use_case_id="", state="x", context_hash="h")


class TestChoiceQuestion:
    def test_accepts_up_to_255_options(self) -> None:
        q = ChoiceQuestion(options=[f"opt-{i}" for i in range(255)])
        assert len(q.options) == 255

    def test_rejects_256_options(self) -> None:
        with pytest.raises(ValidationError):
            ChoiceQuestion(options=[f"opt-{i}" for i in range(256)])

    def test_rejects_empty_options(self) -> None:
        with pytest.raises(ValidationError):
            ChoiceQuestion(options=[])


class TestScoreQuestion:
    def test_accepts_consistent_legend(self) -> None:
        q = ScoreQuestion(min_stage=1, max_stage=3, legend={1: "low", 2: "mid", 3: "high"})
        assert q.max_stage == 3

    def test_rejects_max_not_above_min(self) -> None:
        with pytest.raises(ValidationError):
            ScoreQuestion(min_stage=3, max_stage=3, legend={3: "x"})

    def test_rejects_incomplete_legend(self) -> None:
        with pytest.raises(ValidationError, match="Stufe"):
            ScoreQuestion(min_stage=1, max_stage=3, legend={1: "low", 3: "high"})


class TestNoulQuestion:
    def test_has_no_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            NoulQuestion.model_validate({"kind": "noul", "extra": True})


class TestDecisionQuestionDiscriminator:
    def test_dispatches_on_kind(self) -> None:
        choice = _question_adapter.validate_python({"kind": "choice", "options": ["a", "b"]})
        assert isinstance(choice, ChoiceQuestion)

        noul = _question_adapter.validate_python({"kind": "noul"})
        assert isinstance(noul, NoulQuestion)

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            _question_adapter.validate_python({"kind": "essay"})


class TestDecisionResult:
    def test_accepts_a_noul_answer(self) -> None:
        result = DecisionResult(
            use_case_id="persona-eligibility",
            provider="rule",
            answer=None,
            probability_yes=0.87,
            confidence=0.87,
            fallback_chain=[],
            cost_micros=0,
            latency_ms=1,
            shadow=True,
        )
        assert result.probability_yes == pytest.approx(0.87)

    def test_unresolved_provider_is_a_valid_terminal_state(self) -> None:
        result = DecisionResult(
            use_case_id="u",
            provider="unresolved",
            answer=None,
            confidence=0.0,
            fallback_chain=["jev", "rule", "llm_cheap", "llm_capable"],
            cost_micros=500,
            latency_ms=2000,
            shadow=False,
        )
        assert result.provider == "unresolved"
        assert len(result.fallback_chain) == 4

    def test_rejects_confidence_outside_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            DecisionResult(
                use_case_id="u",
                provider="jev",
                answer="a",
                confidence=1.5,
                cost_micros=0,
                latency_ms=1,
                shadow=True,
            )

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(ValidationError):
            DecisionResult(
                use_case_id="u",
                provider="jev",
                answer="a",
                confidence=0.5,
                cost_micros=-1,
                latency_ms=1,
                shadow=True,
            )
