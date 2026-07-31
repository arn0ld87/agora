"""Tests für den Subprozess-Budget-Guard (Issue #764)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

# camel-ai ist harte Dependency (pyproject) — die echte Basisklasse wird für
# den Typ-Transparenz-Test des Proxys gebraucht (PR #975).
from camel.models.base_model import BaseModelBackend as _BaseModelBackend  # type: ignore[import]

# backend/scripts auf sys.path, wie zur Laufzeit des OASIS-Subprozesses
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sim_runtime.budget_guard import (  # noqa: E402
    SubprocessBudgetGuard,
)


@pytest.fixture()
def run_ledger(tmp_path, monkeypatch):
    """Ledger-Verzeichnis isolieren + AGORA_RUN_ID setzen."""
    run_dirs = tmp_path / "runs"
    run_dirs.mkdir()
    monkeypatch.setattr(
        "app.services.llm_invocation_logger.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    monkeypatch.setenv("AGORA_RUN_ID", "run_sim1")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o-mini")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com")
    return run_dirs / "run_sim1"


def _read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "llm_call_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class _FakeUsage:
    def __init__(self, prompt, completion):
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class _FakeCompletion:
    def __init__(self, usage=None):
        self.usage = usage


class _FakeModel:
    def __init__(self, usage=None):
        self.calls = 0
        self._usage = usage
        self.model_type = "fake-model"

    def run(self, messages, *args, **kwargs):
        self.calls += 1
        return _FakeCompletion(self._usage)

    # CAMEL ruft ModelBackends sowohl synchron als auch async auf.
    # Die SubprocessBudgetGuard muss ALLE vier Aufrufpunkte (run/_run/
    # arun/_arun) instrumentieren — daher haben alle dieselbe Semantik.
    def _run(self, messages, *args, **kwargs):
        self.calls += 1
        return _FakeCompletion(self._usage)

    async def arun(self, messages, *args, **kwargs):
        self.calls += 1
        return _FakeCompletion(self._usage)

    async def _arun(self, messages, *args, **kwargs):
        self.calls += 1
        return _FakeCompletion(self._usage)


class _TypedFakeModel(_FakeModel, _BaseModelBackend):  # type: ignore[misc]
    """``_FakeModel`` mit echter CAMEL-Vererbung.

    CAMEL akzeptiert vorinstanziierte Backends nur, wenn sie
    ``isinstance(model, BaseModelBackend)`` erfüllen (siehe
    ``ChatAgent._resolve_models``). Für den Typ-Transparenz-Test des Proxys
    reicht ein struktureller Fake deshalb nicht.
    """

    def __init__(self, usage=None):
        _FakeModel.__init__(self, usage)

    @property
    def token_counter(self):  # pragma: no cover — von CAMEL nie aufgerufen
        raise NotImplementedError

    def check_model_config(self):  # pragma: no cover — s.o.
        pass


class _RaiseModel:
    """Hilfs-Modell, das immer eine Exception wirft."""

    def __init__(self, exc: Exception):
        self._exc = exc

    def run(self, messages, *args, **kwargs):
        raise self._exc

    def _run(self, messages, *args, **kwargs):
        raise self._exc

    async def arun(self, messages, *args, **kwargs):
        raise self._exc

    async def _arun(self, messages, *args, **kwargs):
        raise self._exc


# CAMEL-Protocol-Methoden, die der Proxy instrumentieren muss. Async-Pfade
# werden in den parametrisierten Tests via ``asyncio.run`` aufgerufen, damit
# die Test-Fixtures selbst synchron bleiben.
_PROTOCOL_METHODS = ("run", "_run", "arun", "_arun")


def _invoke(method_name: str, proxy, messages):
    """Sync bzw. async Protocol-Methode auf dem Proxy aufrufen."""
    method = getattr(proxy, method_name)
    if method_name in ("arun", "_arun"):
        return asyncio.run(method(messages))
    return method(messages)


class TestUsageRecording:
    def test_run_records_usage_event(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        model = _FakeModel(_FakeUsage(1000, 500))
        proxy = guard.wrap_model(model)
        result = proxy.run([{"role": "user", "content": "hi"}])

        assert isinstance(result, _FakeCompletion)
        events = _read_events(run_ledger)
        assert len(events) == 1
        assert events[0]["stage"] == "simulation_rounds"
        assert events[0]["prompt_tokens"] == 1000
        assert events[0]["completion_tokens"] == 500
        assert events[0]["success"] is True
        assert guard._calls == 1

    def test_missing_usage_stays_unknown(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_FakeModel(usage=None))
        proxy.run([])
        events = _read_events(run_ledger)
        assert events[0]["prompt_tokens"] is None
        assert events[0]["completion_tokens"] is None
        # Calls zählen auch ohne Token-Usage (ehrlich: Tokens unknown)
        assert guard._calls == 1

    def test_failed_call_recorded_without_count(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")

        class _Boom(_FakeModel):
            def run(self, messages, *a, **k):
                raise RuntimeError("provider down")

        proxy = guard.wrap_model(_Boom())
        with pytest.raises(RuntimeError):
            proxy.run([])
        events = _read_events(run_ledger)
        assert events[0]["success"] is False
        assert events[0]["error_type"] == "RuntimeError"
        assert guard._calls == 0

    def test_attribute_passthrough(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_FakeModel())
        assert proxy.model_type == "fake-model"

    def test_no_secrets_in_events(self, run_ledger, monkeypatch):
        monkeypatch.setenv(
            "LLM_BASE_URL", "https://user:secretpass@api.openai.com/v1?key=abc"
        )
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_FakeModel(_FakeUsage(1, 1)))
        proxy.run([])
        raw = (run_ledger / "llm_call_events.jsonl").read_text()
        assert "secretpass" not in raw
        assert "key=abc" not in raw


class TestRoundBoundaryChecks:
    def test_hard_calls_limit_aborts(self, run_ledger):
        guard = SubprocessBudgetGuard(
            str(run_ledger), "run_sim1",
            {"max_llm_calls": 2, "enforcement": "hard"},
        )
        guard._calls = 2
        abort = guard.check_round_boundary(round_num=3)
        assert abort is not None
        assert abort["dimension"] == "calls"
        marker = json.loads(
            (run_ledger / "budget_abort.json").read_text()
        )
        assert marker["dimension"] == "calls"

    def test_hard_token_limit_aborts(self, run_ledger):
        guard = SubprocessBudgetGuard(
            str(run_ledger), "run_sim1",
            {"max_tokens": 1000, "enforcement": "hard"},
        )
        guard._prompt_tokens = 800
        guard._completion_tokens = 300
        abort = guard.check_round_boundary(round_num=0)
        assert abort["dimension"] == "tokens"

    def test_soft_enforcement_never_aborts(self, run_ledger):
        guard = SubprocessBudgetGuard(
            str(run_ledger), "run_sim1",
            {"max_llm_calls": 1, "enforcement": "soft"},
        )
        guard._calls = 99
        assert guard.check_round_boundary(round_num=0) is None

    def test_under_limit_continues(self, run_ledger):
        guard = SubprocessBudgetGuard(
            str(run_ledger), "run_sim1",
            {"max_llm_calls": 100, "enforcement": "hard"},
        )
        guard._calls = 2
        assert guard.check_round_boundary(round_num=0) is None

    def test_abort_marker_first_writer_wins(self, run_ledger):
        guard = SubprocessBudgetGuard(
            str(run_ledger), "run_sim1",
            {"max_llm_calls": 1, "enforcement": "hard"},
        )
        run_ledger.mkdir(parents=True, exist_ok=True)
        (run_ledger / "budget_abort.json").write_text(
            json.dumps({"dimension": "time", "observed": 10, "threshold": 5})
        )
        guard._calls = 50
        abort = guard.check_round_boundary(round_num=0)
        assert abort["dimension"] == "calls"  # Rückgabe informiert den Runner
        marker = json.loads((run_ledger / "budget_abort.json").read_text())
        assert marker["dimension"] == "time"  # Datei nicht überschrieben


class TestFromEnvironment:
    def test_disabled_without_run_id(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGORA_RUN_ID", raising=False)
        assert SubprocessBudgetGuard.from_environment(str(tmp_path)) is None

    def test_loads_budget_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGORA_RUN_ID", "run_x")
        (tmp_path / "budget_config.json").write_text(
            json.dumps({"max_tokens": 5, "enforcement": "hard"})
        )
        guard = SubprocessBudgetGuard.from_environment(str(tmp_path))
        assert guard is not None
        assert guard.budget_config["max_tokens"] == 5

    def test_usage_recording_also_without_budget(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGORA_RUN_ID", "run_x")
        guard = SubprocessBudgetGuard.from_environment(str(tmp_path))
        assert guard is not None
        assert guard.budget_config == {}


class TestProxyProtocolSurface:
    """Issue #764 (Review): CAMEL ruft ModelBackends ausschließlich über
    run/_run/arun/_arun auf. Der Proxy muss genau diese vier Methoden
    instrumentieren und alles andere transparent an das Target durchreichen.
    """

    @staticmethod
    def _events(run_dir: Path) -> list[dict]:
        return _read_events(run_dir)

    @pytest.mark.parametrize("method_name", _PROTOCOL_METHODS)
    def test_run_path_records_usage(self, run_ledger, method_name):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_FakeModel(_FakeUsage(7, 11)))
        result = _invoke(method_name, proxy, [])
        assert result.usage.prompt_tokens == 7
        assert result.usage.completion_tokens == 11
        events = self._events(run_ledger)
        assert events[-1]["success"] is True
        assert events[-1]["prompt_tokens"] == 7
        assert events[-1]["completion_tokens"] == 11

    @pytest.mark.parametrize("method_name", _PROTOCOL_METHODS)
    def test_run_path_records_failure(self, run_ledger, method_name):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_RaiseModel(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            _invoke(method_name, proxy, [])
        events = self._events(run_ledger)
        assert events[-1]["success"] is False
        assert events[-1]["error_type"] == "RuntimeError"

    def test_attribute_forwarding_writes_back(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        target = _FakeModel(_FakeUsage(1, 1))
        proxy = guard.wrap_model(target)
        # read
        assert proxy.model_type == "fake-model"
        # write (z.B. CAMEL setzt gelegentlich Model-Attribute neu)
        proxy.model_type = "mutated"
        assert target.model_type == "mutated"

    def test_dict_based_usage_extraction(self, run_ledger):
        # Manche provider liefern ``usage`` als dict statt pydantic — der
        # Mapping-Pfad in ``_extract_usage`` muss genauso funktionieren.
        from sim_runtime.budget_guard import _UsageTrackingModelProxy

        class _DictUsageResult:
            usage = {"prompt_tokens": 4, "completion_tokens": 9}

        prompt, completion = _UsageTrackingModelProxy._extract_usage(
            _DictUsageResult()
        )
        assert prompt == 4
        assert completion == 9

    def test_missing_usage_stays_unknown(self, run_ledger):
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_FakeModel(usage=None))
        proxy.run([])
        events = self._events(run_ledger)
        assert events[-1]["success"] is True
        assert events[-1]["prompt_tokens"] is None
        assert events[-1]["completion_tokens"] is None

    def test_proxy_does_not_implement_call(self, run_ledger):
        # Kein ``__call__``: CAMEL ruft das Backend strukturell über
        # ``run`` auf. Falls CAMEL irgendwann ein Callable-Interface
        # erwartet, soll dieser Test fehlschlagen und der Reviewer es
        # merken (Audit-Anker, Issue #764).
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_FakeModel(_FakeUsage(1, 1)))
        with pytest.raises(TypeError):
            proxy([])  # type: ignore[call-arg]

    def test_proxy_stays_isinstance_of_base_model_backend(self, run_ledger):
        # PR #975 (CodeRabbit): CAMEL prüft das übergebene Backend in
        # ``ChatAgent._resolve_models`` per ``isinstance(model,
        # BaseModelBackend)`` und wirft sonst ``TypeError: Unsupported type
        # for model parameter``. Ein Proxy, der nur ``__getattr__``
        # delegiert, fällt durch diesen Check — die Simulation stirbt beim
        # Agent-Graph-Aufbau, sobald AGORA_RUN_ID gesetzt ist.
        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_TypedFakeModel(_FakeUsage(1, 1)))
        assert isinstance(proxy, _BaseModelBackend)

    def test_proxy_resolves_through_camel_chat_agent(self, run_ledger):
        # Regressionsanker am echten CAMEL-Aufrufpfad statt nur am
        # isinstance-Verhalten (PR #975).
        from camel.agents.chat_agent import ChatAgent

        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_TypedFakeModel(_FakeUsage(1, 1)))
        resolved = ChatAgent._resolve_models(object.__new__(ChatAgent), proxy)
        assert resolved is proxy

    def test_proxy_type_stays_distinct_from_target(self, run_ledger):
        # Die ``__class__``-Delegation darf nur den *gemeldeten* Typ
        # angleichen — der reale Typ bleibt der Proxy, sonst wäre die
        # Instrumentierung weg.
        from sim_runtime.budget_guard import _UsageTrackingModelProxy

        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy = guard.wrap_model(_TypedFakeModel(_FakeUsage(1, 1)))
        assert type(proxy) is _UsageTrackingModelProxy
        proxy.run([])
        assert self._events(run_ledger)[-1]["success"] is True

    def test_proxy_has_no_copy_or_reduce_protocol(self, run_ledger):
        # Issue #764 (Review): CAMEL/OASIS pickelt/copied ModelBackends
        # NICHT — der Proxy darf keine eigenen ``__copy__`` / ``__deepcopy__``
        # / ``__reduce__`` definieren. Würde CAMEL eines Tages eines davon
        # speziell erwarten, fällt dieser Test als Audit-Anker.
        import copy

        guard = SubprocessBudgetGuard(str(run_ledger), "run_sim1")
        proxy_cls = type(guard.wrap_model(_FakeModel(_FakeUsage(1, 1))))
        # Eigene (d.h. nicht von object geerbte) Implementierungen?
        assert "__copy__" not in proxy_cls.__dict__
        assert "__deepcopy__" not in proxy_cls.__dict__
        assert "__reduce__" not in proxy_cls.__dict__
        # Default-Semantik reicht: copy.copy/deepcopy funktionieren über
        # ``object.__reduce_ex__`` und sind für den Runtime-Pfad nicht nötig.
        proxy = guard.wrap_model(_FakeModel(_FakeUsage(1, 1)))
        copy.copy(proxy)
        copy.deepcopy(proxy)
