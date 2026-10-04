"""Gecachte Eingabe-Tokens im Subprozess-Budget-Guard (Issue #1772)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sim_runtime.budget_guard import (  # noqa: E402
    SubprocessBudgetGuard,
    _UsageTrackingModelProxy,
)

extract_cached = _UsageTrackingModelProxy._extract_cached_input_tokens
extract_usage = _UsageTrackingModelProxy._extract_usage


@pytest.fixture()
def run_ledger(tmp_path, monkeypatch):
    run_dirs = tmp_path / "runs"
    run_dirs.mkdir()
    monkeypatch.setattr(
        "app.services.llm_invocation_logger.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    monkeypatch.setenv("AGORA_RUN_ID", "run_sim_cached")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o-mini")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com")
    return run_dirs / "run_sim_cached"


def _events(run_dir: Path) -> list[dict]:
    path = run_dir / "llm_call_events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _completion(prompt=1000, completion=50, details="absent"):
    """OpenAI-aehnliche Antwort; ``details``: 'absent' | Objekt | dict | None."""
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    if details != "absent":
        usage.prompt_tokens_details = details
    return SimpleNamespace(usage=usage)


class TestExtractCachedInputTokens:
    def test_object_details(self):
        result = _completion(details=SimpleNamespace(cached_tokens=640))
        assert extract_cached(result) == 640

    def test_mapping_details(self):
        result = _completion(details={"cached_tokens": 128})
        assert extract_cached(result) == 128

    def test_mapping_usage(self):
        result = SimpleNamespace(
            usage={"prompt_tokens": 10, "completion_tokens": 1,
                   "prompt_tokens_details": {"cached_tokens": 4}}
        )
        assert extract_cached(result) == 4

    def test_zero_is_a_real_measurement(self):
        assert extract_cached(_completion(details=SimpleNamespace(cached_tokens=0))) == 0

    @pytest.mark.parametrize(
        "result",
        [
            _completion(),  # ohne prompt_tokens_details
            _completion(details=None),
            _completion(details=SimpleNamespace(cached_tokens=None)),
            _completion(details=SimpleNamespace()),
            _completion(details={}),
            _completion(details=SimpleNamespace(cached_tokens=-3)),
            _completion(details=SimpleNamespace(cached_tokens="viel")),
            _completion(details=SimpleNamespace(cached_tokens=True)),
            SimpleNamespace(usage=None),
            SimpleNamespace(),
        ],
    )
    def test_missing_or_invalid_is_none_never_zero(self, result):
        assert extract_cached(result) is None

    def test_extract_usage_signature_is_unchanged(self):
        """Bestehende Aufrufer bekommen weiter genau (prompt, completion)."""
        result = _completion(
            prompt=1234, completion=56, details=SimpleNamespace(cached_tokens=1000)
        )
        assert extract_usage(result) == (1234, 56)
        assert extract_usage(SimpleNamespace(usage=None)) == (None, None)


class _Model:
    model_type = "fake"

    def __init__(self, completion):
        self._completion = completion

    def run(self, messages, *a, **k):
        return self._completion

    def _run(self, messages, *a, **k):
        return self._completion

    async def arun(self, messages, *a, **k):
        return self._completion

    async def _arun(self, messages, *a, **k):
        return self._completion


class TestEventAndBudgetCounter:
    @pytest.mark.parametrize("method", ["run", "_run", "arun", "_arun"])
    def test_cached_tokens_written_to_call_event(self, run_ledger, method):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim_cached")
        proxy = guard.wrap_model(
            _Model(_completion(1000, 50, SimpleNamespace(cached_tokens=640)))
        )
        call = getattr(proxy, method)
        if method in ("arun", "_arun"):
            asyncio.run(call([]))
        else:
            call([])
        event = _events(run_ledger)[0]
        assert event["prompt_tokens"] == 1000
        assert event["cached_input_tokens"] == 640

    def test_response_without_details_leaves_field_null(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim_cached")
        guard.wrap_model(_Model(_completion(1000, 50))).run([])
        event = _events(run_ledger)[0]
        assert event["prompt_tokens"] == 1000
        assert event["cached_input_tokens"] is None  # nicht 0

    def test_budget_counter_keeps_full_input_tokens(self, run_ledger):
        """Konservativ: gecachte Tokens mindern den Budgetzaehler NICHT."""
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim_cached")
        proxy = guard.wrap_model(
            _Model(_completion(1000, 50, SimpleNamespace(cached_tokens=900)))
        )
        proxy.run([])
        proxy.run([])
        assert guard._prompt_tokens == 2000
        assert guard._completion_tokens == 100
        assert guard._observed()["tokens"] == 2100

    def test_failed_call_has_no_cached_value(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim_cached")

        class _Boom(_Model):
            def run(self, messages, *a, **k):
                raise RuntimeError("429")

        with pytest.raises(RuntimeError):
            guard.wrap_model(_Boom(None)).run([])
        assert _events(run_ledger)[0]["cached_input_tokens"] is None
