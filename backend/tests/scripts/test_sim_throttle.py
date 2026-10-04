"""Tests für die Drosselung der Simulations-LLM-Aufrufe (Issue #1772)."""
from __future__ import annotations

import ast
import asyncio
import logging
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sim_runtime.budget_guard import SubprocessBudgetGuard  # noqa: E402
from sim_runtime.throttle import (  # noqa: E402
    DEFAULT_INPUT_TOKENS_PER_MINUTE,
    DEFAULT_MAX_CONCURRENCY,
    ENV_INPUT_TOKENS_PER_MINUTE,
    ENV_MAX_CONCURRENCY,
    InputTokenRateLimiter,
    resolve_input_tokens_per_minute,
    resolve_sim_max_concurrency,
)


@pytest.fixture()
def throttle_records():
    """Log-Records des Throttle-Loggers direkt abgreifen (``caplog`` greift nicht:
    die App-Logging-Konfiguration schaltet ``propagate`` ab)."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    target = logging.getLogger("agora.sim_runtime.throttle")
    handler = _Collect(level=logging.DEBUG)
    previous_level = target.level
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(previous_level)


class _FakeClock:
    """Manuelle Uhr; ``sleep`` rückt sie vor, statt zu warten."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _limiter(limit: int, clock: _FakeClock) -> InputTokenRateLimiter:
    return InputTokenRateLimiter(limit, clock=clock, sleep=clock.sleep)


# ---------------------------------------------------------------------------
# Lesefunktion
# ---------------------------------------------------------------------------


class TestResolveSimMaxConcurrency:
    def test_default_is_8_not_30(self):
        assert DEFAULT_MAX_CONCURRENCY == 8
        assert resolve_sim_max_concurrency({}) == 8

    def test_valid_value(self):
        assert resolve_sim_max_concurrency({ENV_MAX_CONCURRENCY: "12"}) == 12
        assert resolve_sim_max_concurrency({ENV_MAX_CONCURRENCY: " 30 "}) == 30

    def test_blank_falls_back_silently(self, throttle_records):
        assert resolve_sim_max_concurrency({ENV_MAX_CONCURRENCY: "  "}) == 8
        assert not throttle_records

    @pytest.mark.parametrize("raw", ["abc", "0", "-3", "1000", "2.5"])
    def test_invalid_value_falls_back_and_logs(self, raw, throttle_records):
        assert resolve_sim_max_concurrency({ENV_MAX_CONCURRENCY: raw}) == 8
        assert any(
            r.levelno == logging.WARNING and ENV_MAX_CONCURRENCY in r.getMessage()
            for r in throttle_records
        )

    def test_reads_process_environment_by_default(self, monkeypatch):
        monkeypatch.setenv(ENV_MAX_CONCURRENCY, "5")
        assert resolve_sim_max_concurrency() == 5


class TestResolveTokensPerMinute:
    def test_default_is_1_5_million(self):
        assert DEFAULT_INPUT_TOKENS_PER_MINUTE == 1_500_000
        assert resolve_input_tokens_per_minute({}) == 1_500_000

    def test_valid_and_zero(self):
        assert resolve_input_tokens_per_minute({ENV_INPUT_TOKENS_PER_MINUTE: "2000000"}) == 2_000_000
        assert resolve_input_tokens_per_minute({ENV_INPUT_TOKENS_PER_MINUTE: "0"}) == 0

    @pytest.mark.parametrize("raw", ["viel", "-1"])
    def test_invalid_falls_back_and_logs(self, raw, throttle_records):
        assert (
            resolve_input_tokens_per_minute({ENV_INPUT_TOKENS_PER_MINUTE: raw})
            == DEFAULT_INPUT_TOKENS_PER_MINUTE
        )
        assert any(
            r.levelno == logging.WARNING and ENV_INPUT_TOKENS_PER_MINUTE in r.getMessage()
            for r in throttle_records
        )


class TestAllSemaphoreSitesUseResolver:
    """Alle ``oasis.make(..., semaphore=...)``-Stellen nutzen die Lesefunktion."""

    FILES = (
        SCRIPTS_DIR / "run_parallel_simulation.py",
        SCRIPTS_DIR / "sim_runtime" / "platform_runner.py",
    )

    @staticmethod
    def _make_calls(path: Path) -> list[ast.Call]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "make"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "oasis"
            ):
                calls.append(node)
        return calls

    def test_three_sites_all_call_resolver(self):
        total = 0
        for path in self.FILES:
            for call in self._make_calls(path):
                total += 1
                kwargs = {kw.arg: kw.value for kw in call.keywords}
                assert "semaphore" in kwargs, f"{path.name}:{call.lineno} ohne semaphore"
                value = kwargs["semaphore"]
                assert isinstance(value, ast.Call), (
                    f"{path.name}:{call.lineno}: semaphore muss die Lesefunktion aufrufen"
                )
                assert isinstance(value.func, ast.Name)
                assert value.func.id == "resolve_sim_max_concurrency"
        assert total == 3  # Twitter + Reddit im Parallel-Runner, 1x Plattform-Runner


# ---------------------------------------------------------------------------
# Limiter
# ---------------------------------------------------------------------------


class TestInputTokenRateLimiter:
    def test_limit_zero_never_waits(self):
        clock = _FakeClock()
        limiter = _limiter(0, clock)

        async def scenario():
            for _ in range(5):
                await limiter.acquire()
                limiter.release(10_000_000)

        asyncio.run(scenario())
        assert not limiter.enabled
        assert clock.sleeps == []

    def test_under_limit_does_not_wait(self):
        clock = _FakeClock()
        limiter = _limiter(100_000, clock)

        async def scenario():
            await limiter.acquire()
            limiter.release(40_000)
            await limiter.acquire()
            limiter.release(40_000)

        asyncio.run(scenario())
        assert clock.sleeps == []

    def test_waits_until_window_frees(self):
        clock = _FakeClock()
        limiter = _limiter(100_000, clock)

        async def scenario():
            await limiter.acquire()
            limiter.release(60_000)  # t = 1000
            clock.now += 10
            await limiter.acquire()
            limiter.release(60_000)  # t = 1010, Summe 120k >= Limit
            start = clock.now
            await limiter.acquire()  # muss warten, bis der erste Eintrag raus ist
            return clock.now - start

        waited = asyncio.run(scenario())
        # erster Eintrag (t=1000) verlässt das Fenster bei t=1060; jetzt t=1010
        assert waited == pytest.approx(50.0)
        assert limiter.throttle_count == 1

    def test_unknown_usage_records_nothing(self):
        clock = _FakeClock()
        limiter = _limiter(1_000, clock)

        async def scenario():
            for _ in range(3):
                await limiter.acquire()
                limiter.release(None)

        asyncio.run(scenario())
        assert clock.sleeps == []

    def test_inflight_calls_are_estimated_from_window_average(self):
        clock = _FakeClock()
        limiter = _limiter(100_000, clock)

        async def scenario():
            await limiter.acquire()
            limiter.release(40_000)  # Fenster: 40k, Mittel 40k
            await limiter.acquire()  # laufend 0 -> 40k < 100k
            await limiter.acquire()  # laufend 1 -> 40k + 40k = 80k < 100k
            assert clock.sleeps == []
            await limiter.acquire()  # laufend 2 -> 40k + 80k = 120k >= 100k -> wartet
            return list(clock.sleeps)

        sleeps = asyncio.run(scenario())
        assert sleeps  # der vierte Aufruf wurde gedrosselt, ohne dass etwas abgeschlossen war

    def test_sixteen_concurrent_calls_start_at_most_five_in_first_window(self):
        """16 gleichzeitige Aufrufe a 20.000 Tokens bei Limit 100.000 (#1772).

        Zwei Plattformen mit Parallelitaet 8 starten 16 Aufrufe im selben
        Eventloop. Bei leerem Fenster gab es keine Reservierung: alle 16
        rutschten durch. Jetzt laeuft zuerst eine Sonde, danach reserviert jeder
        laufende Aufruf das gemessene Mittel -- hoechstens 5 starten, solange
        die Uhr im ersten Fenster steht.
        """
        clock = _FakeClock()

        async def poll_sleep(seconds: float) -> None:
            await asyncio.sleep(0)  # Uhr steht: alles passiert im ersten Fenster

        limiter = InputTokenRateLimiter(100_000, clock=clock, sleep=poll_sleep)
        started: list[int] = []

        async def scenario():
            release_gate = asyncio.Event()

            async def call(index: int) -> None:
                await limiter.acquire()
                started.append(index)
                await release_gate.wait()
                limiter.release(20_000)

            tasks = [asyncio.create_task(call(i)) for i in range(16)]
            for _ in range(50):
                await asyncio.sleep(0)
            assert len(started) == 1  # Kaltstart: nur die Sonde laeuft
            release_gate.set()
            for _ in range(200):
                await asyncio.sleep(0)
            count_in_first_window = len(started)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return count_in_first_window

        assert asyncio.run(scenario()) <= 5

    def test_cold_start_runs_a_single_probe_then_releases_waiters(self):
        clock = _FakeClock()

        async def poll_sleep(seconds: float) -> None:
            await asyncio.sleep(0)

        limiter = InputTokenRateLimiter(1_000_000, clock=clock, sleep=poll_sleep)
        started: list[int] = []

        async def scenario():
            gate = asyncio.Event()

            async def call(index: int) -> None:
                await limiter.acquire()
                started.append(index)
                if index == 0:
                    await gate.wait()
                limiter.release(10_000)

            tasks = [asyncio.create_task(call(i)) for i in range(6)]
            for _ in range(30):
                await asyncio.sleep(0)
            probe_only = len(started)
            gate.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
            return probe_only

        assert asyncio.run(scenario()) == 1
        assert len(started) == 6

    def test_empty_window_after_pause_still_reserves_for_inflight_calls(self):
        """Nach einer Pause (Fenster leer) zaehlen laufende Aufrufe weiter mit."""
        clock = _FakeClock()
        waited: list[float] = []

        class _Waited(Exception):
            pass

        async def sleep_once(seconds: float) -> None:
            waited.append(seconds)
            raise _Waited  # nichts gibt frei: der Aufruf muss tatsaechlich warten

        limiter = InputTokenRateLimiter(100_000, clock=clock, sleep=sleep_once)

        async def scenario():
            await limiter.acquire()
            limiter.release(40_000)
            clock.now += 120  # Fenster verfaellt, Messwert bleibt als Schaetzung
            await limiter.acquire()  # 0 laufend -> frei
            await limiter.acquire()  # 1 laufend -> 40k < 100k
            await limiter.acquire()  # 2 laufend -> 80k < 100k
            assert waited == []
            with pytest.raises(_Waited):
                await limiter.acquire()  # 3 laufend -> 120k >= 100k -> wartet

        asyncio.run(scenario())
        assert len(waited) == 1

    def test_provider_without_usage_does_not_serialize_forever(self, throttle_records):
        clock = _FakeClock()
        limiter = _limiter(100_000, clock)

        async def scenario():
            for _ in range(3):
                await limiter.acquire()
                limiter.release(None)
            # Drei Freigaben ohne Messwert: Anbieter meldet keine Usage.
            for _ in range(5):
                await limiter.acquire()  # alle gleichzeitig laufend, ohne Warten
            return limiter._inflight

        assert asyncio.run(scenario()) == 5
        assert clock.sleeps == []
        assert any(
            r.levelno == logging.WARNING and "keine Token-Usage" in r.getMessage()
            for r in throttle_records
        )

    def test_cancellation_during_wait_is_not_swallowed(self):
        clock = _FakeClock()

        async def never_returning_sleep(seconds: float) -> None:
            await asyncio.sleep(3600)

        limiter = InputTokenRateLimiter(10, clock=clock, sleep=never_returning_sleep)

        async def scenario():
            await limiter.acquire()
            limiter.release(50)  # Fenster voll
            task = asyncio.create_task(limiter.acquire())
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Einhängen im Budget-Guard
# ---------------------------------------------------------------------------


class _Usage:
    def __init__(self, prompt: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = 1


class _Completion:
    def __init__(self, prompt: int) -> None:
        self.usage = _Usage(prompt)


class _AsyncModel:
    model_type = "fake"

    def __init__(self, prompt: int) -> None:
        self._prompt = prompt
        self.calls = 0

    async def arun(self, messages, *args, **kwargs):
        self.calls += 1
        return _Completion(self._prompt)

    async def _arun(self, messages, *args, **kwargs):
        self.calls += 1
        return _Completion(self._prompt)


class TestGuardIntegration:
    @pytest.fixture()
    def ledger(self, tmp_path, monkeypatch):
        run_dirs = tmp_path / "runs"
        run_dirs.mkdir()
        monkeypatch.setattr(
            "app.services.llm_invocation_logger.ArtifactLocator.run_dir",
            staticmethod(lambda run_id: str(run_dirs / run_id)),
        )
        monkeypatch.setenv("AGORA_RUN_ID", "run_sim_throttle")
        return tmp_path

    def test_from_environment_builds_limiter_from_env(self, ledger, monkeypatch):
        monkeypatch.setenv(ENV_INPUT_TOKENS_PER_MINUTE, "123456")
        guard = SubprocessBudgetGuard.from_environment(str(ledger))
        assert guard is not None
        assert guard.rate_limiter is not None
        assert guard.rate_limiter.limit == 123_456

    def test_from_environment_default_has_enabled_limiter(self, ledger, monkeypatch):
        monkeypatch.delenv(ENV_INPUT_TOKENS_PER_MINUTE, raising=False)
        guard = SubprocessBudgetGuard.from_environment(str(ledger))
        assert guard is not None
        assert guard.rate_limiter is not None
        assert guard.rate_limiter.enabled
        assert guard.rate_limiter.limit == 1_500_000

    def test_from_environment_zero_disables_limiter(self, ledger, monkeypatch):
        monkeypatch.setenv(ENV_INPUT_TOKENS_PER_MINUTE, "0")
        guard = SubprocessBudgetGuard.from_environment(str(ledger))
        assert guard is not None
        assert guard.rate_limiter is not None
        assert not guard.rate_limiter.enabled

    @pytest.mark.parametrize("method", ["arun", "_arun"])
    def test_async_calls_are_throttled_across_platforms(self, ledger, method):
        clock = _FakeClock()
        limiter = _limiter(100_000, clock)
        guard = SubprocessBudgetGuard(
            str(ledger), "run_sim_throttle", rate_limiter=limiter
        )
        # Ein Guard, ein Proxy je Plattform -- beide teilen den Limiter.
        twitter = guard.wrap_model(_AsyncModel(80_000))
        reddit = guard.wrap_model(_AsyncModel(80_000))

        async def scenario():
            await getattr(twitter, method)([])
            start = clock.now
            await getattr(reddit, method)([])  # 80k im Fenster < 100k: kein Warten
            assert clock.now == start
            await getattr(twitter, method)([])  # 160k >= 100k: wartet
            return clock.now - start

        waited = asyncio.run(scenario())
        assert waited > 0
        assert limiter.throttle_count == 1

    def test_failed_call_releases_slot(self, ledger):
        clock = _FakeClock()
        limiter = _limiter(100_000, clock)
        guard = SubprocessBudgetGuard(
            str(ledger), "run_sim_throttle", rate_limiter=limiter
        )

        class _Boom(_AsyncModel):
            async def arun(self, messages, *args, **kwargs):
                raise RuntimeError("429")

        proxy = guard.wrap_model(_Boom(1))

        async def scenario():
            for _ in range(3):
                with pytest.raises(RuntimeError):
                    await proxy.arun([])

        asyncio.run(scenario())
        assert limiter._inflight == 0
        assert clock.sleeps == []

    def test_budget_exceeded_is_raised_before_waiting(self, ledger, monkeypatch):
        """``BudgetExceededError`` läuft vor dem Limiter durch (keine Wartezeit)."""
        from app.services.run_budget import BudgetExceededError

        clock = _FakeClock()
        limiter = _limiter(10, clock)
        guard = SubprocessBudgetGuard(
            str(ledger), "run_sim_throttle", rate_limiter=limiter
        )

        async def fill_window():
            await limiter.acquire()
            limiter.release(1_000)

        asyncio.run(fill_window())

        def _raise() -> None:
            raise BudgetExceededError("tokens", 1, 1)

        monkeypatch.setattr(guard, "_enforce_before_physical_call", _raise)
        proxy = guard.wrap_model(_AsyncModel(1))

        async def scenario():
            with pytest.raises(BudgetExceededError):
                await proxy.arun([])

        asyncio.run(scenario())
        assert clock.sleeps == []  # Fenster war voll, trotzdem kein Warten
