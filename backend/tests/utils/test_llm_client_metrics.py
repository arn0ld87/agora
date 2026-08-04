"""Tests für LLM-Token-Counter-Integration in LLMClient.chat (Slice 2c).

TDD-Spec (RED first):
- chat() inkrementiert llm_token_counter mit direction=in (prompt) + out (completion)
- chat_json() inkrementiert analog (über chat()-Delegation)
- Retry-Pfad zählt nur einmal (finale Response)
- Fehlende Usage-Daten → kein Increment, keine Exception
- provider/model-Labels korrekt gesetzt

Fixture-Strategie: identisch zu test_metrics.py — InMemoryMetricReader + Monkeypatch.
LLMClient wird ohne echten OpenAI-Server gebaut; API-Calls werden via unittest.mock gepatcht.
"""

from __future__ import annotations

import threading
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.observability.metrics as metrics_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_metrics_cache(monkeypatch):
    monkeypatch.setattr(metrics_module, "_provider", None)
    monkeypatch.setattr(metrics_module, "_meter", None)
    monkeypatch.setattr(metrics_module, "_lock", threading.Lock())
    yield
    metrics_module._provider = None
    metrics_module._meter = None


@pytest.fixture()
def in_memory_reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture()
def metrics_provider(
    in_memory_reader: InMemoryMetricReader,
    monkeypatch,
) -> Generator[tuple[MeterProvider, InMemoryMetricReader]]:
    from opentelemetry.sdk.resources import Resource

    views = metrics_module._build_views()
    provider = MeterProvider(
        metric_readers=[in_memory_reader],
        resource=Resource.create({"service.name": "agora-test"}),
        views=views,
    )
    meter = provider.get_meter("agora-test")

    monkeypatch.setattr(metrics_module, "_provider", provider)
    monkeypatch.setattr(metrics_module, "_meter", meter)

    yield provider, in_memory_reader

    provider.force_flush()


def _collect_datapoints(reader: InMemoryMetricReader, instrument_name: str) -> list:
    data = reader.get_metrics_data()
    result = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == instrument_name:
                    result.extend(metric.data.data_points)
    return result


# ---------------------------------------------------------------------------
# Helper: LLMClient mit Mock-OpenAI
# ---------------------------------------------------------------------------


def _make_client(model: str = "test-model", base_url: str = "http://localhost:9999/v1") -> Any:
    """Baut LLMClient ohne echten OpenAI-Server (API-Key=dummy)."""
    from app.utils.llm_client import LLMClient

    with patch("app.llm.client.OpenAI"):
        client = LLMClient(
            api_key="dummy-key",
            base_url=base_url,
            model=model,
        )
    return client


def _make_usage(prompt_tokens: int, completion_tokens: int) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    return usage


def _make_choice(content: str = '{"ok": true}', finish_reason: str = "stop") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason
    return choice


def _make_response(
    content: str = '{"ok": true}',
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    response = MagicMock()
    response.choices = [_make_choice(content)]
    response.usage = _make_usage(prompt_tokens, completion_tokens)
    return response


# ---------------------------------------------------------------------------
# Case 1: chat() inkrementiert Token-Counter (in + out)
# ---------------------------------------------------------------------------


class TestChatIncrementsTokenCounter:
    def test_chat_increments_token_counter_in_and_out(self, metrics_provider, monkeypatch):
        """chat() → llm_token_counter mit direction=in (+42) und direction=out (+17)."""
        provider, reader = metrics_provider

        client = _make_client(model="llama3")
        response = _make_response(content="hello world", prompt_tokens=42, completion_tokens=17)

        # ``chat()`` geht inzwischen über ``_provider_attempt`` (Budget-Gate-Pfad,
        # Issue #764) statt direkt über ``llm_call_with_retry``. Die alte Mock-Stelle
        # wird nicht mehr getroffen, deshalb ValueError "not enough values to unpack".
        # Mock auf der neuen Schicht: ``_provider_attempt`` liefert (response, latency_ms).
        with patch.object(client, "_publish_model_active"):
            with patch.object(
                client, "_provider_attempt", return_value=(response, 12.3)
            ):
                client.chat([{"role": "user", "content": "hi"}])

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.llm.tokens")
        in_dps = [dp for dp in dps if dp.attributes.get("direction") == "in"]
        out_dps = [dp for dp in dps if dp.attributes.get("direction") == "out"]

        assert any(dp.value == 42 for dp in in_dps), f"Kein in-DataPoint=42. DPs: {in_dps}"
        assert any(dp.value == 17 for dp in out_dps), f"Kein out-DataPoint=17. DPs: {out_dps}"


# --------------------------------------------------------------------------
# Case 2: chat_json() inkrementiert Token-Counter (über chat()-Delegation)
# --------------------------------------------------------------------------


class TestChatJsonIncrementsTokenCounter:
    def test_chat_json_increments_token_counter(self, metrics_provider, monkeypatch):
        """chat_json() delegiert an chat() → Token-Counter wird inkrementiert."""
        provider, reader = metrics_provider

        client = _make_client(model="mistral")
        response = _make_response(content='{"result": "ok"}', prompt_tokens=30, completion_tokens=8)

        with patch.object(client, "_publish_model_active"):
            with patch.object(
                client, "_provider_attempt", return_value=(response, 9.1)
            ):
                client.chat_json([{"role": "user", "content": "test"}])

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.llm.tokens")
        in_dps = [dp for dp in dps if dp.attributes.get("direction") == "in"]
        out_dps = [dp for dp in dps if dp.attributes.get("direction") == "out"]

        assert any(dp.value == 30 for dp in in_dps), f"Kein in-DataPoint=30. DPs: {dps}"
        assert any(dp.value == 8 for dp in out_dps), f"Kein out-DataPoint=8. DPs: {dps}"


# ---------------------------------------------------------------------------
# Case 3: Retry → Token-Counter wird nur einmal mit finaler Response gezählt
# ---------------------------------------------------------------------------


class TestRetryDoesNotDoubleCount:
    def test_retry_does_not_double_count(self, metrics_provider, monkeypatch):
        """Retry-Pfad → Counter nur einmal für die finale Response.

        Auch nach dem Refactor auf ``_provider_attempt`` (Issue #764) darf der
        Token-Counter nur einmal pro chat()-Aufruf inkrementiert werden, nicht
        pro Retry-Attempt innerhalb von ``llm_call_with_retry``.

        Der erste ``_provider_attempt`` wirft eine transiente
        ``APIConnectionError`` — genau die Klasse, die
        ``llm_call_with_retry`` als retry-würdig behandelt. Erst der zweite
        Aufruf liefert die finale Response. ``call_count == 2`` beweist, dass
        die Retry-Schleife tatsächlich zweimal durchlaufen wurde und die
        Counter-Zusicherung nicht nur einen Single-Shot-Pfad abdeckt.
        """
        from openai import APIConnectionError

        provider, reader = metrics_provider

        client = _make_client(model="qwen3")
        # Backoff-Sleep aus dem Test rausnehmen — geprüft wird die Zählung,
        # nicht das Timing.
        monkeypatch.setattr(client, "_retry_initial_delay", 0.0)
        final_response = _make_response(content="final", prompt_tokens=20, completion_tokens=10)

        call_count = [0]

        def _fake_attempt(call_kwargs, context):
            call_count[0] += 1
            if call_count[0] == 1:
                raise APIConnectionError(request=MagicMock())
            return final_response, 5.0

        with patch.object(client, "_publish_model_active"):
            with patch.object(client, "_provider_attempt", side_effect=_fake_attempt):
                client.chat([{"role": "user", "content": "hi"}])

        provider.force_flush()

        # Echter Retry: erster Attempt transient gescheitert, zweiter erfolgreich.
        assert call_count[0] == 2, f"Erwartet 2 Provider-Attempts, bekam {call_count[0]}"

        dps = _collect_datapoints(reader, "agora.llm.tokens")
        in_dps = [dp for dp in dps if dp.attributes.get("direction") == "in"]
        out_dps = [dp for dp in dps if dp.attributes.get("direction") == "out"]

        # Genau einmal gezählt — nicht doppelt
        total_in = sum(dp.value for dp in in_dps)
        total_out = sum(dp.value for dp in out_dps)
        assert total_in == 20, f"Erwartet 20 in-Tokens, bekam {total_in}"
        assert total_out == 10, f"Erwartet 10 out-Tokens, bekam {total_out}"


# --------------------------------------------------------------------------
# Case 4: Fehlende Usage → kein Increment, keine Exception
# --------------------------------------------------------------------------


class TestMissingUsageNoIncrement:
    def test_missing_usage_no_increment(self, metrics_provider, monkeypatch):
        """Response ohne .usage → kein Counter-Increment, keine Exception."""
        provider, reader = metrics_provider

        client = _make_client(model="no-usage-model")
        response = MagicMock()
        response.choices = [_make_choice(content="hello")]
        response.usage = None  # Provider liefert kein Usage-Objekt

        with patch.object(client, "_publish_model_active"):
            with patch.object(
                client, "_provider_attempt", return_value=(response, 1.0)
            ):
                result = client.chat([{"role": "user", "content": "hi"}])

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.llm.tokens")
        assert len(dps) == 0, f"Unerwartete Token-DataPoints bei fehlendem Usage: {dps}"
        assert result == "hello"


# --------------------------------------------------------------------------
# Case 5: provider/model-Labels korrekt gesetzt
# --------------------------------------------------------------------------


class TestProviderModelLabels:
    def test_provider_model_labels_set(self, metrics_provider, monkeypatch):
        """Counter-DataPoints enthalten korrekte provider/model-Attribute.

        Nutzt einen Non-Ollama-Provider (kein force_stream), damit der Mock-Response
        sauber durch den Nicht-Streaming-Pfad läuft und Usage-Daten korrekt gelesen werden.
        """
        provider, reader = metrics_provider

        # openai.com → provider="openai", kein Ollama-Stream-Pfad
        client = _make_client(model="gpt-4o-mini", base_url="https://api.openai.com/v1")
        response = _make_response(content="ok", prompt_tokens=5, completion_tokens=3)

        with patch.object(client, "_publish_model_active"):
            with patch.object(
                client, "_provider_attempt", return_value=(response, 2.5)
            ):
                client.chat([{"role": "user", "content": "test"}])

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.llm.tokens")
        assert len(dps) >= 2, f"Zu wenige DataPoints: {dps}"

        for dp in dps:
            assert "model" in dp.attributes, f"model-Label fehlt: {dp.attributes}"
            assert "provider" in dp.attributes, f"provider-Label fehlt: {dp.attributes}"
            assert "direction" in dp.attributes, f"direction-Label fehlt: {dp.attributes}"
            assert dp.attributes["model"] == "gpt-4o-mini"
            assert dp.attributes["provider"] == "openai"  # openai.com in base_url
