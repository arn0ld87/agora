"""Tests für den Decision-Layer-Use-Case `local-search-relevance` (f005,
Slice `decision-pilot`/`jev-core`, Tasks `shadow-usecase`/`resolve-fn`):
lokale Keyword-Relevanzbewertung.

Kernanforderungen:
- Default-Verhalten (``AGORA_DECISION_LAYER_MODE=disabled``) bleibt
  unverändert, und ein Fehler in der Decision Layer darf nie nach außen
  dringen.
- ``shadow``: unverändertes Verhalten des vormaligen
  ``shadow_relevance_check`` (nur auf ``resolve_relevance``/``rule=``
  migriert).
- ``authoritative``: Jev zuerst, ``RuleProvider`` als Rückfall bei jeder
  Jev-Unverfügbarkeit oder -Ausnahme. In KEINEM Pfad landet Query- oder
  Fakt-Text im Log — auch nicht über eine SDK-Exception, die die Anfrage
  spiegelt.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

import httpx2
import pytest
from typesafe_sdk import (
    TypeSafeAPITimeoutError,
    TypeSafeAuthenticationError,
    TypeSafeRateLimitError,
)

from app.config import Config
from app.contracts.decision_contract import DecisionResult, DecisionState, NoulQuestion
from app.services.decisions.jev_provider import DecisionJevResponseError
from app.services.decisions.local_search_relevance import (
    RELEVANCE_ASSERTION,
    _USE_CASE_ID,
    _relevance_rule,
    _reset_jev_cache_for_tests,
    resolve_relevance,
)
from app.services.decisions.rule_provider import RuleProvider
from app.services.run_budget import RunBudgetEnforcer, reset_call_reservations
from app.services.run_registry import RunRegistry
from app.services.run_usage_ledger import (
    aggregate_usage,
    load_call_events,
    reset_usage_cache,
)

#: Auffällige Marker statt echter Query-/Fakttexte in den Rückfall-Tests —
#: so kann geprüft werden, dass der Text in KEINEM Logpfad landet, auch
#: nicht über die Message einer (fingierten) SDK-Exception, die die
#: Anfrage spiegelt.
_QUERY_MARKER = "MARKER-QUERY-e8f3c1"
_FACT_MARKER = "MARKER-FACT-91ab7d"


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


class _FakeJevProvider:
    """Fake-``DecisionProvider`` für den authoritative-Pfad: liefert entweder
    ein Ergebnis oder wirft die injizierte Ausnahme. Kein Netzwerk, keine
    echte ``typesafe_sdk``-Instanz."""

    def __init__(
        self, *, result: DecisionResult | None = None, exc: Exception | None = None
    ) -> None:
        self._result = result
        self._exc = exc
        self.calls: list[tuple[DecisionState, NoulQuestion]] = []

    def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
        self.calls.append((state, question))
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


def _jev_result(*, probability_yes: float = 0.9) -> DecisionResult:
    return DecisionResult(
        use_case_id=_USE_CASE_ID,
        provider="jev",
        answer=None,
        probability_yes=probability_yes,
        confidence=0.8,
        model_version="jev-1.13.0",
        request_id="req-jev-1",
        cost_micros=120,
        latency_ms=42,
        shadow=False,
    )


@pytest.fixture(autouse=True)
def _default_mode_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")


@pytest.fixture(autouse=True)
def _reset_jev_cache():
    _reset_jev_cache_for_tests()
    yield
    _reset_jev_cache_for_tests()


class TestResolveRelevanceDisabled:
    def test_returns_none_and_calls_nothing_when_mode_is_disabled(self) -> None:
        provider = _RecordingProvider()
        result = resolve_relevance("Bundeskanzleramt", "ein Fakt", 100, rule=provider)

        assert result is None
        assert provider.calls == []

    def test_returns_none_without_a_top_fact_even_in_shadow_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        result = resolve_relevance("Bundeskanzleramt", None, 100, rule=provider)

        assert result is None
        assert provider.calls == []

    def test_returns_none_without_a_top_fact_in_authoritative_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        jev = _FakeJevProvider(result=_jev_result())

        result = resolve_relevance("Bundeskanzleramt", None, 100, jev=jev)

        assert result is None
        assert jev.calls == []


class TestResolveRelevanceShadowMode:
    def test_calls_the_rule_provider_and_returns_a_shadow_result(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # ``get_logger`` setzt ``propagate=False`` (app/utils/logger.py) —
        # caplog haengt am Root-Handler, muss Propagation entlang der
        # Logger-Kette also explizit erlauben (siehe test_transport_security.py).
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(
                "Bundeskanzleramt", "ein Fakt über Berlin", 100, rule=provider
            )

        assert len(provider.calls) == 1
        state, question = provider.calls[0]
        assert isinstance(question, NoulQuestion)
        assert state.use_case_id == _USE_CASE_ID
        assert state.state == {"top_score": 100}
        assert result is not None
        assert result.shadow is True
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
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(
                "Bundeskanzleramt", "ein Fakt", 100, rule=_UnknownCostProvider()
            )

        assert result is not None
        assert "decision_layer_shadow use_case=" in caplog.text
        assert "cost_micros=None" in caplog.text
        assert "decision_layer_shadow failed" not in caplog.text

    def test_provider_failure_is_swallowed_and_logged(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _FailingProvider()

        with caplog.at_level(logging.ERROR, logger="agora.decisions.local_search_relevance"):
            # Wirft nicht — ein Fehler in der Decision Layer darf local_search
            # nie stören.
            result = resolve_relevance("Bundeskanzleramt", "ein Fakt", 100, rule=provider)

        assert result is None
        assert "decision_layer_shadow failed" in caplog.text

    def test_same_query_and_fact_yield_the_same_context_hash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        resolve_relevance("Bundeskanzleramt", "ein Fakt", 100, rule=provider)
        resolve_relevance("Bundeskanzleramt", "ein Fakt", 100, rule=provider)

        first_hash = provider.calls[0][0].context_hash
        second_hash = provider.calls[1][0].context_hash
        assert first_hash == second_hash

    def test_different_facts_yield_different_context_hashes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        provider = _RecordingProvider()

        resolve_relevance("Bundeskanzleramt", "Fakt A", 100, rule=provider)
        resolve_relevance("Bundeskanzleramt", "Fakt B", 100, rule=provider)

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
        from types import SimpleNamespace
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
        jev_client.system_one.return_value = SimpleNamespace(
            model="jev-1.13.0",
            request_id="req-shadow-test",
            usage=SimpleNamespace(input_tokens=10, output_tokens=0),
            choices={},
            scores={},
            nouls={"decision": SimpleNamespace(noul=0.5)},
        )

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
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")

        for expected_provider, provider in self._providers():
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
                resolve_relevance("Bundeskanzleramt", "ein Fakt", 100, rule=provider)

            assert f"provider={expected_provider}" in caplog.text, (
                f"{expected_provider}: keine Shadow-Telemetrie — der Aufruf ist "
                "entweder nicht durchgelaufen oder hat still versagt."
            )
            # Ein stiller Fehlschlag würde sonst als 'bestanden' durchgehen,
            # weil resolve_relevance nie wirft.
            assert "decision_layer_shadow failed" not in caplog.text


class TestDefaultRuleProvider:
    """Der Default-Provider (kein ``rule=`` übergeben) — RuleProvider mit
    der Schwellenwertregel dieses Moduls."""

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

        resolve_relevance("Bundeskanzleramt", "ein Fakt", 100, rule=_Spy())

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

        resolve_relevance("Bundeskanzleramt", "ein Fakt", 0, rule=_Spy())

        assert captured[0].probability_yes == pytest.approx(0.0)


class TestResolveRelevanceAuthoritativeSuccess:
    def test_jev_success_yields_provider_jev_and_the_benchmark_state_form(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        jev = _FakeJevProvider(result=_jev_result())

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance("Bundeskanzleramt", "Ein Fakt über Berlin", 100, jev=jev)

        assert result is not None
        assert result.provider == "jev"
        assert result.shadow is False
        assert result.fallback_chain == ["jev"]

        assert len(jev.calls) == 1
        state, question = jev.calls[0]
        assert isinstance(question, NoulQuestion)
        assert state.state == {
            "assertion": RELEVANCE_ASSERTION,
            "query": "Bundeskanzleramt",
            "fact": "Ein Fakt über Berlin",
        }
        assert "decision_layer_authoritative" in caplog.text
        assert "Bundeskanzleramt" not in caplog.text
        assert "Ein Fakt über Berlin" not in caplog.text


class TestResolveRelevanceAuthoritativeFallback:
    """Jede Ursache eines Jev-Rückfalls landet beim selben Ziel: Rule,
    ``shadow=False``, ``fallback_chain=["jev", "rule"]`` — und in keinem
    Fall taucht Query- oder Fakttext im Log auf, selbst wenn die
    (fingierte) Jev-Ausnahme sie in ihrer Message spiegelt."""

    @staticmethod
    def _auth_error(request_id: str | None = "req-auth-1") -> TypeSafeAuthenticationError:
        headers = httpx2.Headers({"x-typesafe-request-id": request_id} if request_id else {})
        return TypeSafeAuthenticationError(401, {"error": "unauthorized"}, headers)

    @staticmethod
    def _rate_limit_error() -> TypeSafeRateLimitError:
        return TypeSafeRateLimitError(429, {"error": "rate limited"}, httpx2.Headers())

    def _run_fallback_case(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, jev_exc: Exception
    ) -> tuple[DecisionResult | None, str]:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        jev = _FakeJevProvider(exc=jev_exc)

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100, jev=jev)

        return result, caplog.text

    @pytest.mark.parametrize(
        "make_exc",
        [
            pytest.param(lambda: TypeSafeAPITimeoutError(2.0), id="timeout"),
            pytest.param(
                lambda: TestResolveRelevanceAuthoritativeFallback._rate_limit_error(),
                id="rate-limit",
            ),
            pytest.param(
                lambda: DecisionJevResponseError(f"leak-attempt {_FACT_MARKER}"),
                id="response-error",
            ),
            pytest.param(
                lambda: RuntimeError(f"leak-attempt {_QUERY_MARKER} {_FACT_MARKER}"),
                id="generic-runtime-error",
            ),
        ],
    )
    def test_jev_exception_falls_back_to_rule(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        make_exc,
    ) -> None:
        result, log_text = self._run_fallback_case(monkeypatch, caplog, make_exc())

        assert result is not None
        assert result.provider == "rule"
        assert result.shadow is False
        assert result.fallback_chain == ["jev", "rule"]
        assert _QUERY_MARKER not in log_text
        assert _FACT_MARKER not in log_text

    def test_auth_error_falls_back_and_never_leaks_the_request(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        result, log_text = self._run_fallback_case(monkeypatch, caplog, self._auth_error())

        assert result is not None
        assert result.provider == "rule"
        assert result.fallback_chain == ["jev", "rule"]
        assert _QUERY_MARKER not in log_text
        assert _FACT_MARKER not in log_text
        # Request-ID ist unkritisch (keine Anfrageinhalte) und darf im Log
        # zur Korrelation erscheinen.
        assert "req-auth-1" in log_text

    def test_no_key_falls_back_to_rule(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance.resolve_jev_api_key",
            lambda: None,
        )

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100)

        assert result is not None
        assert result.provider == "rule"
        assert result.fallback_chain == ["jev", "rule"]
        assert "fallback_reason=no_key" in caplog.text
        assert _QUERY_MARKER not in caplog.text
        assert _FACT_MARKER not in caplog.text

    def test_auth_block_prevents_a_second_jev_call_until_it_expires(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")

        # Erster Aufruf: injizierter Jev-Provider wirft einen Auth-Fehler —
        # das muss den internen Cache sperren.
        jev = _FakeJevProvider(exc=self._auth_error(request_id=None))
        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            first = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100, jev=jev)
        assert first is not None
        assert first.provider == "rule"

        # Zweiter Aufruf OHNE injizierten Provider: muss die Sperre über
        # ``_jev_provider()`` greifen lassen und darf resolve_jev_api_key/
        # build_jev_client gar nicht erst aufrufen.
        def _fail_if_called(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("Jev-Provider darf waehrend der Sperre nicht gebaut werden")

        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance.resolve_jev_api_key",
            _fail_if_called,
        )
        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance.build_jev_client",
            _fail_if_called,
        )
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            second = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100)

        assert second is not None
        assert second.provider == "rule"
        assert "fallback_reason=auth_blocked" in caplog.text

        # Nach Ablauf der Sperre (300s) greift ``_jev_provider()`` wieder
        # normal durch — hier bewusst auf "kein Key" statt eines echten
        # Aufrufs, um weiterhin ohne Netzwerk zu bleiben.
        monkeypatch.undo()
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance.resolve_jev_api_key",
            lambda: None,
        )
        real_monotonic = time.monotonic()
        monkeypatch.setattr(time, "monotonic", lambda: real_monotonic + 301.0)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            third = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100)

        assert third is not None
        assert third.provider == "rule"
        assert "fallback_reason=no_key" in caplog.text
        assert "auth_blocked" not in caplog.text

    def test_rule_fallback_failure_yields_none_and_logs_only_class_names(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        jev = _FakeJevProvider(exc=RuntimeError(f"leak {_QUERY_MARKER}"))

        class _FailingRule:
            def decide(self, state: DecisionState, question: NoulQuestion) -> DecisionResult:
                raise RuntimeError(f"leak {_FACT_MARKER}")

        with caplog.at_level(logging.ERROR, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(
                _QUERY_MARKER, _FACT_MARKER, 100, jev=jev, rule=_FailingRule()
            )

        assert result is None
        assert "rule_fallback_failed=RuntimeError" in caplog.text
        assert _QUERY_MARKER not in caplog.text
        assert _FACT_MARKER not in caplog.text

    def test_key_store_failure_falls_back_to_rule_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``get_bound_store_api_key`` fängt nur ``RuntimeError`` — jeder
        andere Key-Store-Fehler darf ``local_search`` trotzdem nie abbrechen."""
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")

        def _store_down() -> str | None:
            raise ValueError(f"store down {_QUERY_MARKER}")

        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance.resolve_jev_api_key", _store_down
        )

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100)

        assert result is not None
        assert result.provider == "rule"
        assert result.fallback_chain == ["jev", "rule"]
        assert "fallback_reason=provider_unavailable(ValueError)" in caplog.text
        assert _QUERY_MARKER not in caplog.text

    def test_lone_surrogate_in_query_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Eine JSON-Query kann einen einzelnen Surrogat enthalten; vorher
        warf ``_context_hash`` außerhalb jedes try-Blocks ``UnicodeEncodeError``."""
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance.resolve_jev_api_key", lambda: None
        )

        result = resolve_relevance("abc\ud800", _FACT_MARKER, 100)

        assert result is not None
        assert result.provider == "rule"

    def test_unexpected_error_outside_the_fallback_yields_none(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")

        def _boom(*_args: object) -> str:
            raise ValueError(f"leak {_FACT_MARKER}")

        monkeypatch.setattr(
            "app.services.decisions.local_search_relevance._context_hash", _boom
        )

        with caplog.at_level(logging.ERROR, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100)

        assert result is None
        assert "unexpected_error=ValueError" in caplog.text
        assert _FACT_MARKER not in caplog.text


class TestRealSdkClientPath:
    """Gegen den ECHTEN ``TypeSafeClient`` (kein Fake-Provider): prüft, was
    die Fake-Tests oben nicht prüfen können — dass das SDK selbst keinen
    Klartext loggt und dass ``Config.JEV_TIMEOUT_S`` den heißen Pfad
    tatsächlich begrenzt."""

    def test_sdk_debug_wire_log_never_carries_query_or_fact(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeInternalServerError

        from app.services.decisions.jev_provider import JevDecisionProvider

        client = TypeSafeClient(
            api_key="test-key",
            model="jev-1.13.0",
            retry=RetryPolicy(max_retries=0),
            transport=httpx2.MockTransport(lambda _req: httpx2.Response(500, json={})),
        )
        state = DecisionState(
            use_case_id=_USE_CASE_ID,
            state={"query": _QUERY_MARKER, "fact": _FACT_MARKER},
            context_hash="h",
        )
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("typesafe_sdk").setLevel(logging.DEBUG)
            try:
                with pytest.raises(TypeSafeInternalServerError):
                    JevDecisionProvider(client).decide(state, NoulQuestion())
            finally:
                logging.getLogger("typesafe_sdk").setLevel(logging.NOTSET)

        # Die INFO-Zeile des SDK kommt an (Filter verwirft nicht alles) …
        assert any(r.name == "typesafe_sdk" for r in caplog.records)
        # … der DEBUG-Body mit Query/Fakt nicht.
        assert _QUERY_MARKER not in caplog.text
        assert _FACT_MARKER not in caplog.text

    def test_hanging_jev_is_cut_off_by_the_timeout_and_falls_back_to_rule(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import socket
        import threading

        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        accepted: list[socket.socket] = []
        stop = threading.Event()

        def _accept_and_never_answer() -> None:
            server.settimeout(0.05)
            while not stop.is_set():
                try:
                    conn, _ = server.accept()
                except OSError:
                    continue
                accepted.append(conn)

        worker = threading.Thread(target=_accept_and_never_answer, daemon=True)
        worker.start()
        try:
            monkeypatch.setenv(
                "TYPESAFE_BASE_URL", f"http://127.0.0.1:{server.getsockname()[1]}"
            )
            monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
            monkeypatch.setattr(Config, "JEV_TIMEOUT_S", 0.2)
            monkeypatch.setattr(
                "app.services.decisions.local_search_relevance.resolve_jev_api_key",
                lambda: "test-key",
            )
            monkeypatch.setattr(
                "app.services.decisions.jev_provider.resolve_jev_api_key", lambda: "test-key"
            )
            monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
            monkeypatch.setattr(
                logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
            )

            started = time.monotonic()
            with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
                result = resolve_relevance(_QUERY_MARKER, _FACT_MARKER, 100)
            elapsed = time.monotonic() - started
        finally:
            stop.set()
            worker.join(timeout=1)
            for conn in accepted:
                conn.close()
            server.close()

        assert result is not None
        assert result.provider == "rule"
        assert result.fallback_chain == ["jev", "rule"]
        assert "fallback_reason=TypeSafeAPITimeoutError" in caplog.text
        # Obergrenze (max_retries+1)*timeout + Backoff (<=0.5s) + Puffer.
        # Gemessen ~0.24s: das Retry-Budget (RetryPolicy.timeout = 0.2s) ist
        # nach dem ersten Timeout aufgebraucht, ein zweiter Versuch startet nicht.
        assert elapsed < 1.5, f"authoritative path blocked for {elapsed:.2f}s"
        assert len(accepted) <= 2


class TestResolveRelevanceAuthoritativeBudget:
    """f001 (Slice `jev-budget`): Budget-Gate + Ledger-Verbuchung des
    authoritative-Pfads. Läuft gegen die ECHTEN Ledger-/Registry-Funktionen
    mit einem isolierten ``tmp_path``-Run-Verzeichnis, nicht nur gegen Mocks
    — ``run_env`` spiegelt exakt die Fixture aus
    ``tests/services/test_run_budget.py``."""

    @pytest.fixture()
    def run_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        registry_dir = tmp_path / "run_registry"
        registry_dir.mkdir()
        monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
        RunRegistry._instance = None
        run_dirs = tmp_path / "runs"
        run_dirs.mkdir()
        monkeypatch.setattr(
            "app.services.run_usage_ledger.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(run_dirs / run_id)),
        )
        monkeypatch.setattr(
            "app.services.run_budget.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(run_dirs / run_id)),
        )
        monkeypatch.setattr(
            "app.services.llm_invocation_logger.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(run_dirs / run_id)),
        )
        reset_usage_cache()
        reset_call_reservations()
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        monkeypatch.setattr(
            logging.getLogger("agora.decisions.local_search_relevance"), "propagate", True
        )
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")
        yield run_dirs
        RunRegistry._instance = None
        reset_usage_cache()
        reset_call_reservations()

    @staticmethod
    def _create_run(budget: dict | None = None) -> str:
        manifest = RunRegistry().create_run(
            "simulation_run", "sim_1", metadata={"budget": budget} if budget else None
        )
        return manifest["run_id"]

    @staticmethod
    def _write_events(run_dirs: Path, run_id: str, events: list[dict]) -> None:
        run_dir = run_dirs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "llm_call_events.jsonl", "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
        reset_usage_cache()

    def test_successful_jev_call_with_run_id_is_booked_to_the_ledger(
        self, run_env: Path
    ) -> None:
        run_id = self._create_run()
        jev = _FakeJevProvider(result=_jev_result())

        result = resolve_relevance(
            "Bundeskanzleramt", "Ein Fakt über Berlin", 100, jev=jev, run_id=run_id
        )

        assert result is not None
        assert result.provider == "jev"
        assert result.fallback_chain == ["jev"]

        events = load_call_events(run_id)
        assert len(events) == 1
        event = events[0]
        assert event["provider_id"] == "jev"
        assert event["model"] == "jev-1.13.0"
        assert event["success"] is True
        assert event["remote_request_id"] == "req-jev-1"
        assert event["reported_cost_micros"] == 120

        usage = aggregate_usage(run_id)
        assert usage.totals.llm_calls == 1
        assert usage.totals.cost_micros == 120
        assert usage.by_provider["jev"].cost_micros == 120

    def test_budget_exhausted_blocks_jev_call_and_falls_back_to_rule(
        self, run_env: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        run_id = self._create_run({"max_llm_calls": 1, "enforcement": "hard"})
        # Budget bereits ausgeschoepft: ein frueherer Call liegt schon im Ledger.
        self._write_events(
            run_env,
            run_id,
            [
                {
                    "run_id": run_id,
                    "stage": "report_generation",
                    "provider_id": "openai",
                    "model": "gpt-4o-mini",
                    "base_url_sanitized": "https://api.openai.com",
                    "timestamp": 1_700_000_000.0,
                    "latency_ms": 100.0,
                    "success": True,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                }
            ],
        )

        def _fail_if_called(*_args: object, **_kwargs: object) -> DecisionResult:
            raise AssertionError("Jev darf bei erschoepftem Budget nicht aufgerufen werden")

        jev = _FakeJevProvider(result=_jev_result())
        jev.decide = _fail_if_called  # type: ignore[method-assign]

        with caplog.at_level(logging.INFO, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(
                _QUERY_MARKER, _FACT_MARKER, 100, jev=jev, run_id=run_id
            )

        assert result is not None
        assert result.provider == "rule"
        assert result.fallback_chain == ["jev", "rule"]
        assert "fallback_reason=budget_exhausted" in caplog.text

        # Kein zweites Event: der Jev-Call hat nie stattgefunden.
        events = load_call_events(run_id)
        assert len(events) == 1
        assert events[0]["provider_id"] == "openai"

    def test_without_run_id_skips_budget_check_and_ledger_write(
        self, run_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail_if_called(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("ohne run_id darf kein Budget-Enforcer gebaut werden")

        monkeypatch.setattr(RunBudgetEnforcer, "for_run", staticmethod(_fail_if_called))
        jev = _FakeJevProvider(result=_jev_result())

        result = resolve_relevance("Bundeskanzleramt", "Ein Fakt über Berlin", 100, jev=jev)

        assert result is not None
        assert result.provider == "jev"
        # Keine run_id => kein Run-Verzeichnis, also auch kein Event zu lesen —
        # der eigentliche Beweis ist, dass ``RunBudgetEnforcer.for_run`` oben
        # nie aufgerufen wurde (sonst hätte die Assertion das gesamte
        # authoritative try/except in lauter `unexpected_error` verwandelt,
        # was die Provider-Zuordnung unten sichtbar bräche).

    def test_ledger_write_failure_does_not_affect_the_result(
        self,
        run_env: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        run_id = self._create_run()
        jev = _FakeJevProvider(result=_jev_result())

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(
            "app.services.llm_invocation_logger.LlmInvocationLogger.log_event", _boom
        )

        with caplog.at_level(logging.WARNING, logger="agora.decisions.local_search_relevance"):
            result = resolve_relevance(
                "Bundeskanzleramt", "Ein Fakt über Berlin", 100, jev=jev, run_id=run_id
            )

        assert result is not None
        assert result.provider == "jev"
        assert result.cost_micros == 120
        assert "ledger_write_failed=OSError" in caplog.text


class TestBenchmarkScriptsShareTheAssertionConstant:
    """Beide Jev-Skripte importieren ``RELEVANCE_ASSERTION`` statt die
    Aussage separat zu definieren — sonst könnten Benchmark, Probe und der
    produktive authoritative-Pfad unbemerkt auseinanderlaufen."""

    @staticmethod
    def _load(script_name: str):
        script_path = Path(__file__).resolve().parents[3] / "scripts" / script_name
        spec = importlib.util.spec_from_file_location(script_name, script_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_jev_benchmark_local_search_uses_the_shared_constant(self) -> None:
        module = self._load("jev_benchmark_local_search.py")
        assert module.RELEVANCE_ASSERTION is RELEVANCE_ASSERTION

    def test_jev_rollout_probe_uses_the_shared_constant(self) -> None:
        module = self._load("jev_rollout_probe.py")
        assert module.RELEVANCE_ASSERTION is RELEVANCE_ASSERTION
