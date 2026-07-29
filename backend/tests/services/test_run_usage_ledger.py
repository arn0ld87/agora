"""Tests für den Run Usage Ledger (Issue #764)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from app.services import run_usage_ledger
from app.services.pricing_registry import PricingRegistry
from app.services.run_usage_ledger import (
    aggregate_usage,
    load_call_events,
    load_call_events_cached,
    reset_usage_cache,
)


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


class TestCostStatusAggregation:
    """Issue #764 (Review): partial-token Daten dürfen nicht als 'measured'
    ausgewiesen werden. Kostenaussagen folgen der Token-Messqualität."""

    def test_partial_tokens_demote_priced_cost_to_estimated(self, pricing):
        # 2 priced Events, eines ohne Tokens → Tokens partial, Cost nur
        # anteilig bekannt. cost_status MUSS "estimated" sein, NICHT
        # "measured" (sonst wäre die ausgewiesene Summe irreführend).
        events = [_event(), _event(prompt_tokens=None, completion_tokens=None)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "partial"
        assert usage.totals.cost_status == "estimated"
        assert usage.totals.cost_micros is not None

    def test_all_priced_full_tokens_is_measured(self, pricing):
        events = [_event(prompt_tokens=1000, completion_tokens=500)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "measured"
        assert usage.totals.cost_status == "measured"

    def test_all_free_full_tokens_is_free(self, pricing):
        events = [_event(
            provider_id="ollama",
            model="qwen3:8b",
            base_url_sanitized="http://localhost:11434",
        )]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "measured"
        assert usage.totals.cost_status == "free"
        assert usage.totals.cost_micros == 0

    def test_all_free_partial_tokens_is_estimated_not_free(self, pricing):
        # Free-Modell mit fehlenden Tokens: ein "free"-Label wäre irreführend,
        # weil wir nicht wissen, wie viele Tokens tatsächlich angefallen sind.
        events = [_event(
            provider_id="ollama",
            model="qwen3:8b",
            base_url_sanitized="http://localhost:11434",
            prompt_tokens=None,
            completion_tokens=None,
        )]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "unknown"
        assert usage.totals.cost_status == "estimated"
        assert usage.totals.cost_micros == 0

    def test_mix_priced_and_unknown_full_tokens_stays_estimated(self, pricing):
        events = [
            _event(prompt_tokens=1000, completion_tokens=500),
            _event(provider_id="minimax", model="MiniMax-M9-ultra"),
        ]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "measured"
        # Mindestens ein Event hat unbekannten Preis → "estimated",
        # auch wenn die Token-Messung vollständig ist.
        assert usage.totals.cost_status == "estimated"

    def test_mix_priced_and_free_full_tokens_is_measured(self, pricing):
        # Free + priced mit vollen Tokens → Summe exakt, free trägt 0 bei.
        events = [
            _event(prompt_tokens=1000, completion_tokens=500),
            _event(
                provider_id="ollama",
                model="qwen3:8b",
                base_url_sanitized="http://localhost:11434",
            ),
        ]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.tokens_status == "measured"
        assert usage.totals.cost_status == "measured"

    def test_unknown_price_only_events_stay_unknown_no_phantom_zero(self, pricing):
        # Wichtige Ehrlichkeitsregel: kein Event hat einen Preis → keine
        # Summe ausweisen. cost_micros MUSS None bleiben (nie 0).
        events = [_event(provider_id="minimax", model="MiniMax-M9-ultra")]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.cost_status == "unknown"
        assert usage.totals.cost_micros is None

    def test_failed_calls_count_as_calls_and_duration_kept(self, pricing):
        # Issue #764 (Codex P2): ``llm_calls`` zaehlt jeden tatsaechlichen
        # Providerattempt — auch fehlgeschlagene Requests (Netzwerkfehler,
        # HTTP-Fehler, Timeout) und Fallback-Versuche. Reine lokale Fehler
        # (JSON-Parse, Pydantic-Validation) erscheinen NICHT als eigenes
        # Event im Ledger und erzeugen daher auch keinen zusaetzlichen Call.
        # Latenz bleibt erfasst, damit Timeout-Diagnose moeglich bleibt.
        events = [_event(success=False, latency_ms=50.0)]
        usage = aggregate_usage("run_x", events=events, pricing=pricing)
        assert usage.totals.llm_calls == 1
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


class TestUsageCache:
    """Issue #764 (Review Punkt 6): bounded LRU-Cache mit
    (mtime_ns, size)-Invalidierung — robust gegen same-second rewrites."""

    @staticmethod
    def _patch_run_dir(monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            "app.services.run_usage_ledger.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(tmp_path / run_id)),
        )

    def test_cache_hit_returns_same_object(self, tmp_path, monkeypatch):
        self._patch_run_dir(monkeypatch, tmp_path)
        reset_usage_cache()
        run_dir = tmp_path / "run_hit"
        run_dir.mkdir()
        (run_dir / "llm_call_events.jsonl").write_text(
            '{"stage": "a", "success": true}\n', encoding="utf-8"
        )
        first = load_call_events_cached("run_hit")
        second = load_call_events_cached("run_hit")
        assert first is second  # identisches Listen-Objekt → kein Re-Read
        assert "run_hit" in run_usage_ledger._cache

    def test_append_invalidates_via_size(self, tmp_path, monkeypatch):
        self._patch_run_dir(monkeypatch, tmp_path)
        reset_usage_cache()
        run_dir = tmp_path / "run_app"
        run_dir.mkdir()
        path = run_dir / "llm_call_events.jsonl"
        path.write_text('{"stage": "a", "success": true}\n', encoding="utf-8")
        assert len(load_call_events_cached("run_app")) == 1
        # Append verändert size → Cache-Eintrag veraltet.
        with open(path, "a", encoding="utf-8") as handle:
            handle.write('{"stage": "b", "success": true}\n')
        assert len(load_call_events_cached("run_app")) == 2

    def test_mtime_ns_invalidates_within_same_second(self, tmp_path, monkeypatch):
        # Beweist, dass mtime_ns (nicht nur float-mtime) das Invalidierungs-
        # merkmal ist: zwei Writes gleicher Größe in derselben Sekunde, deren
        # mtime_ns sich um 1 ns unterscheidet. Ein float-mtime-Cache würde das
        # nicht merken; (mtime_ns, size) schon.
        self._patch_run_dir(monkeypatch, tmp_path)
        reset_usage_cache()
        run_dir = tmp_path / "run_ns"
        run_dir.mkdir()
        path = run_dir / "llm_call_events.jsonl"
        base_ns = 1_700_000_000_000_000_000  # beliebige Nanosekunden-Marke
        # v1 und v2 sind byteweise gleich lang, unterscheiden sich im Wert.
        path.write_text('{"a":1,"v":1}\n', encoding="utf-8")
        os.utime(path, ns=(base_ns, base_ns))
        v1 = load_call_events_cached("run_ns")
        assert v1[0]["v"] == 1
        path.write_text('{"a":1,"v":2}\n', encoding="utf-8")  # gleiche Größe
        os.utime(path, ns=(base_ns + 1, base_ns + 1))  # +1 ns, gleiche Sekunde
        v2 = load_call_events_cached("run_ns")
        assert v2[0]["v"] == 2, "mtime_ns-Änderung muss Cache invalidieren"

    def test_size_limit_evicts_oldest(self, tmp_path, monkeypatch):
        self._patch_run_dir(monkeypatch, tmp_path)
        reset_usage_cache()
        monkeypatch.setattr(run_usage_ledger, "_CACHE_MAX", 2)
        for i in range(3):
            run_dir = tmp_path / f"run_{i}"
            run_dir.mkdir()
            (run_dir / "llm_call_events.jsonl").write_text(
                f'{{"stage": "s{i}", "success": true}}\n', encoding="utf-8"
            )
            load_call_events_cached(f"run_{i}")
        assert len(run_usage_ledger._cache) == 2
        assert "run_0" not in run_usage_ledger._cache  # ältester evicted
        assert "run_2" in run_usage_ledger._cache

    def test_parallel_access_is_safe(self, tmp_path, monkeypatch):
        self._patch_run_dir(monkeypatch, tmp_path)
        reset_usage_cache()
        run_dir = tmp_path / "run_par"
        run_dir.mkdir()
        (run_dir / "llm_call_events.jsonl").write_text(
            '{"stage": "a", "success": true}\n', encoding="utf-8"
        )
        results: list[list] = []
        errors: list[BaseException] = []
        n = 16
        barrier = threading.Barrier(n)

        def gated() -> None:
            try:
                barrier.wait()
                results.append(load_call_events_cached("run_par"))
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=gated) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(results) == n
        assert all(r == results[0] for r in results)
