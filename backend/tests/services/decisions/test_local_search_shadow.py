"""Tests für den Shadow-Pilot-Use-Case (f005, Slice `decision-pilot`, Task
`shadow-usecase`): lokale Keyword-Relevanzbewertung.

Kernanforderung: Default-Verhalten (``AGORA_DECISION_LAYER_MODE=disabled``)
bleibt unverändert, und ein Fehler in der Decision Layer darf nie nach
außen dringen.
"""

from __future__ import annotations

import logging

import pytest

from app.config import Config
from app.contracts.decision_contract import DecisionResult, DecisionState, NoulQuestion
from app.services.decisions.local_search_shadow import (
    _USE_CASE_ID,
    _relevance_rule,
    shadow_relevance_check,
)
from app.services.decisions.rule_provider import RuleProvider


class _RecordingProvider:
    """Zeichnet jeden ``decide()``-Aufruf auf, ohne selbst etwas zu prüfen."""

    def __init__(self, *, probability_yes: float = 1.0) -> None:
        self._probability_yes = probability_yes
        self.calls: list[tuple[DecisionState, NoulQuestion]] = []

    def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
        self.calls.append((state, question))
        return DecisionResult(
            use_case_id=state.use_case_id,
            provider="fake",
            answer=None,
            probability_yes=self._probability_yes,
            confidence=1.0,
            cost_micros=0,
            latency_ms=0,
            shadow=False,
        )


class _FailingProvider:
    def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
        raise RuntimeError("boom")


class _UnknownCostProvider:
    """Liefert ``cost_micros=None`` — der reale Fall für einen injizierten
    ``LLMProvider`` ohne ``run_id`` oder eine Jev-Antwort ohne ``usage``."""

    def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
        return DecisionResult(
            use_case_id=state.use_case_id,
            provider="fake",
            answer=None,
            probability_yes=0.5,
            confidence=0.5,
            cost_micros=None,
            latency_ms=0,
            shadow=False,
        )


@pytest.fixture(autouse=True)
def _default_mode_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")


class TestShadowRelevanceCheckDisabled:
    def test_does_nothing_when_mode_is_disabled(self) -> None:
        provider = _RecordingProvider()
        shadow_relevance_check("Bundeskanzleramt", "ein Fakt", 100, provider=provider)

        assert provider.calls == []

    def test_does_nothing_without_a_top_fact_even_in_shadow_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        shadow_relevance_check("Bundeskanzleramt", None, 100, provider=provider)

        assert provider.calls == []


class TestShadowRelevanceCheckShadowMode:
    def test_calls_the_provider_and_logs_a_shadow_result(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # ``get_logger`` setzt ``propagate=False`` (app/utils/logger.py) —
        # caplog haengt am Root-Handler, muss Propagation entlang der
        # Logger-Kette also explizit erlauben (siehe test_transport_security.py).
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_shadow"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_shadow"):
            shadow_relevance_check(
                "Bundeskanzleramt", "ein Fakt über Berlin", 100, provider=provider
            )

        assert len(provider.calls) == 1
        state, question = provider.calls[0]
        assert isinstance(question, NoulQuestion)
        assert state.use_case_id == _USE_CASE_ID
        assert state.state == {"top_score": 100}
        assert "decision_layer_shadow" in caplog.text

    def test_unknown_cost_still_logs_the_successful_result(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Review-Befund (Codex, PR #1547): das Log-Format nutzte `%d` für
        `cost_micros`, das laut Vertrag `int | None` ist. `%d % None` wirft
        einen `TypeError`, den der äußere `try/except` als Fehlschlag
        loggt — der erfolgreiche Shadow-Aufruf hätte in genau den
        Unbekannt-Kosten-Fällen keine Telemetrie erzeugt, die der Vertrag
        bewusst sichtbar machen soll."""
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_shadow"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_shadow"):
            shadow_relevance_check(
                "Bundeskanzleramt", "ein Fakt", 100, provider=_UnknownCostProvider()
            )

        assert "decision_layer_shadow use_case=" in caplog.text
        assert "cost_micros=None" in caplog.text
        assert "decision_layer_shadow failed" not in caplog.text

    def test_provider_failure_is_swallowed_and_logged(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_shadow"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _FailingProvider()

        with caplog.at_level(logging.ERROR, logger="agora.decisions.local_search_shadow"):
            # Wirft nicht — ein Fehler in der Decision Layer darf local_search
            # nie stören.
            shadow_relevance_check("Bundeskanzleramt", "ein Fakt", 100, provider=provider)

        assert "decision_layer_shadow failed" in caplog.text

    def test_same_query_and_fact_yield_the_same_context_hash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        shadow_relevance_check("Bundeskanzleramt", "ein Fakt", 100, provider=provider)
        shadow_relevance_check("Bundeskanzleramt", "ein Fakt", 100, provider=provider)

        first_hash = provider.calls[0][0].context_hash
        second_hash = provider.calls[1][0].context_hash
        assert first_hash == second_hash

    def test_different_facts_yield_different_context_hashes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        shadow_relevance_check("Bundeskanzleramt", "Fakt A", 100, provider=provider)
        shadow_relevance_check("Bundeskanzleramt", "Fakt B", 100, provider=provider)

        first_hash = provider.calls[0][0].context_hash
        second_hash = provider.calls[1][0].context_hash
        assert first_hash != second_hash


class TestRunsOverEveryTypedProvider:
    """Akzeptanzkriterium der Slice: derselbe Shadow-Aufruf läuft über die
    typisierten Rule-, LLM-, Fake- und Jev-Provider. Getestet wird der
    echte Aufrufpfad inklusive ``shadow``-Markierung und Telemetriezeile,
    nicht nur die Konstruierbarkeit der Adapter."""

    @staticmethod
    def _providers() -> list[tuple[str, object]]:
        from unittest.mock import MagicMock

        from app.contracts.decision_contract import DecisionResult
        from app.services.decisions.fake_provider import FakeProvider
        from app.services.decisions.jev_provider import JevDecisionProvider
        from app.services.decisions.llm_provider import LLMProvider

        llm_client = MagicMock(spec=["chat_json", "model", "run_id"])
        llm_client.model = "gpt-test"
        llm_client.run_id = "run-1"
        llm_client.chat_json.return_value = {"probability_yes": 0.5, "confidence": 0.5}

        jev_client = MagicMock(spec=["system_one"])
        jev_client.system_one.return_value = {
            "answers": [{"id": "q1", "probability_yes": 0.5, "confidence": 0.5}],
            "model": "jev-1.13.0",
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }

        scripted = DecisionResult(
            use_case_id=_USE_CASE_ID,
            provider="fake",
            answer=None,
            probability_yes=0.5,
            confidence=0.5,
            cost_micros=0,
            latency_ms=0,
            shadow=False,
        )

        return [
            ("rule", RuleProvider(use_case_id=_USE_CASE_ID, rule_fn=_relevance_rule)),
            ("fake", FakeProvider([scripted])),
            ("llm_cheap", LLMProvider(llm_client)),
            ("jev", JevDecisionProvider(jev_client)),
        ]

    def test_every_typed_provider_answers_the_same_shadow_call(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_shadow"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")

        for expected_provider, provider in self._providers():
            caplog.clear()
            with caplog.at_level(
                logging.INFO, logger="agora.decisions.local_search_shadow"
            ):
                shadow_relevance_check(
                    "Bundeskanzleramt", "ein Fakt", 100, provider=provider
                )

            assert f"provider={expected_provider}" in caplog.text, (
                f"{expected_provider}: keine Shadow-Telemetrie — der Aufruf ist "
                "entweder nicht durchgelaufen oder hat still versagt."
            )
            # Ein stiller Fehlschlag würde sonst als 'bestanden' durchgehen,
            # weil shadow_relevance_check nie wirft.
            assert "decision_layer_shadow failed" not in caplog.text


class TestDefaultRuleProvider:
    """Der Default-Provider (kein ``provider=`` übergeben) — RuleProvider
    mit der Schwellenwertregel dieses Moduls."""

    def test_answers_yes_when_top_score_is_at_or_above_the_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        captured: list[DecisionResult] = []
        real = RuleProvider(use_case_id=_USE_CASE_ID, rule_fn=_relevance_rule)

        class _Spy:
            def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
                result = real.decide(state, question)
                captured.append(result)
                return result

        shadow_relevance_check("Bundeskanzleramt", "ein Fakt", 100, provider=_Spy())

        assert captured[0].probability_yes == pytest.approx(1.0)
        assert captured[0].provider == "rule"
        assert captured[0].cost_micros == 0

    def test_answers_no_when_top_score_is_below_the_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        captured: list[DecisionResult] = []
        real = RuleProvider(use_case_id=_USE_CASE_ID, rule_fn=_relevance_rule)

        class _Spy:
            def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
                result = real.decide(state, question)
                captured.append(result)
                return result

        shadow_relevance_check("Bundeskanzleramt", "ein Fakt", 0, provider=_Spy())

        assert captured[0].probability_yes == pytest.approx(0.0)
