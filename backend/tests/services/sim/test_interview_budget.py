"""Regressionstest Slice B4c: ``run_id`` fliesst additiv durch die Interview-Kette.

Vor dem Fix baute ``_default_client_factory`` einen ``LLMClient`` ohne
``run_id`` — Interview-Calls im Direktpfad (Post-Simulation, kein IPC) waren
fuer Budget-Guard und Ledger unsichtbar, weil ``_budget_enforcer``/
``_log_invocation_event`` ohne ``run_id`` No-Ops bleiben.

Kette: ``graph_tools.interview_agents`` -> ``SimulationRunner.interview_agents_batch``
-> ``interview_client.interview_agents_batch`` -> ``interview_agents_batch_direct``
-> ``_default_client_factory`` -> ``LLMClient(run_id=...)``.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.services.sim import interview_client, interview_direct
from app.services.sim.interview_direct import (
    _default_client_factory,
    interview_agents_batch_direct,
)
from app.services.simulation_runner import SimulationRunner


PROFILES: List[Dict[str, Any]] = [
    {
        "user_id": 1,
        "username": "lena_k",
        "name": "Lena Krüger",
        "bio": "Product Ownerin in einem mittelständischen SaaS-Team",
        "persona": "Skeptisch gegenüber neuen Tools.",
        "age": 38,
        "country": "DE",
        "profession": "Product Ownerin",
        "interested_topics": ["SaaS"],
    },
]

SIM_CONFIG: Dict[str, Any] = {
    "simulation_id": "sim_0123456789ab",
    "simulation_requirement": "Wie lässt sich das Onboarding verbessern?",
    "language": "de",
}


def _store_mock(profiles=PROFILES, config=SIM_CONFIG) -> MagicMock:
    """Artifact-Store-Doppel: liefert reddit_profiles und simulation_config."""
    store = MagicMock()

    def read_json(simulation_id, name, default=None):
        if name == "reddit_profiles":
            return profiles
        if name == "simulation_config":
            return config
        return default

    def exists(simulation_id, name):
        if name == "reddit_profiles":
            return profiles is not None
        if name == "simulation_config":
            return config is not None
        return False

    store.read_json.side_effect = read_json
    store.exists.side_effect = exists
    return store


class _FakeLLMClient:
    """Zeichnet die Konstruktor-Kwargs auf, mit denen sie gebaut wurde."""

    instances: List["_FakeLLMClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.run_id = kwargs.get("run_id")
        type(self).instances.append(self)

    def chat(self, messages, **kwargs):
        return "Ich sehe das kritisch."


# ---------------------------------------------------------------------------
# 1. ``_default_client_factory`` reicht ``run_id`` an den gebauten Client durch
# ---------------------------------------------------------------------------


class TestDefaultClientFactoryPassesRunId:
    def test_run_id_reaches_llm_client_without_route(self, monkeypatch) -> None:
        _FakeLLMClient.instances = []
        monkeypatch.setattr("app.llm.client.LLMClient", _FakeLLMClient)

        # Kein llm_model im Kontext -> Fallback-Zweig der Factory
        # (``return LLMClient(timeout=timeout, run_id=run_id)``).
        factory = _default_client_factory(
            60.0, {"llm_model": "", "llm_base_url": ""}, run_id="run-42"
        )
        client = factory()

        assert isinstance(client, _FakeLLMClient)
        assert client.kwargs.get("run_id") == "run-42"

    def test_run_id_defaults_to_none_when_not_given(self, monkeypatch) -> None:
        _FakeLLMClient.instances = []
        monkeypatch.setattr("app.llm.client.LLMClient", _FakeLLMClient)

        factory = _default_client_factory(60.0, {"llm_model": "", "llm_base_url": ""})
        client = factory()

        assert client.kwargs.get("run_id") is None


# ---------------------------------------------------------------------------
# 2. ``interview_agents_batch_direct`` reicht ``run_id`` an die Default-Factory
# ---------------------------------------------------------------------------


class TestBatchDirectPassesRunId:
    def test_run_id_flows_into_default_factory_without_explicit_client_factory(
        self, monkeypatch, tmp_path
    ) -> None:
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        _FakeLLMClient.instances = []
        monkeypatch.setattr("app.llm.client.LLMClient", _FakeLLMClient)

        store = _store_mock()
        with patch.object(interview_direct, "_store", return_value=store):
            result = interview_agents_batch_direct(
                "sim_0123456789ab",
                [{"agent_id": 1, "prompt": "Was hältst du davon?"}],
                run_state_dir=str(tmp_path),
                run_id="run-batch-1",
            )

        assert result["success"] is True
        assert len(_FakeLLMClient.instances) == 1
        assert _FakeLLMClient.instances[0].run_id == "run-batch-1"

    def test_explicit_client_factory_still_wins_over_run_id(
        self, monkeypatch, tmp_path
    ) -> None:
        """Additive Regel: ein uebergebener ``client_factory`` bleibt Vorrang —
        ``run_id`` wird nur genutzt, wenn die Default-Factory selbst baut."""
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        explicit_client = _FakeLLMClient()
        _FakeLLMClient.instances = []  # Konstruktions-Log zuruecksetzen

        store = _store_mock()
        with patch.object(interview_direct, "_store", return_value=store):
            result = interview_agents_batch_direct(
                "sim_0123456789ab",
                [{"agent_id": 1, "prompt": "Was hältst du davon?"}],
                run_state_dir=str(tmp_path),
                client_factory=lambda: explicit_client,
                run_id="run-ignored",
            )

        assert result["success"] is True
        # Die Default-Factory wurde nie aufgerufen -> keine neue Instanz.
        assert _FakeLLMClient.instances == []


# ---------------------------------------------------------------------------
# 3. Kette interview_client -> interview_agents_batch_direct
# ---------------------------------------------------------------------------


class TestInterviewClientForwardsRunId:
    def test_interview_agents_batch_forwards_run_id_to_direct_path(
        self, monkeypatch, tmp_path
    ) -> None:
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        monkeypatch.setattr(
            interview_client, "check_env_alive", lambda *a, **k: False
        )
        captured: Dict[str, Any] = {}

        def _fake_batch_direct(simulation_id, interviews, platform, timeout, **kwargs):
            captured.update(kwargs)
            return {"success": True, "interviews_count": 0, "result": {"results": {}}}

        monkeypatch.setattr(
            interview_client, "interview_agents_batch_direct", _fake_batch_direct
        )

        interview_client.interview_agents_batch(
            "sim_0123456789ab",
            [{"agent_id": 1, "prompt": "x"}],
            run_state_dir=str(tmp_path),
            run_id="run-chain-1",
        )

        assert captured.get("run_id") == "run-chain-1"

    def test_interview_agent_forwards_run_id_to_direct_path(
        self, monkeypatch, tmp_path
    ) -> None:
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        monkeypatch.setattr(
            interview_client, "check_env_alive", lambda *a, **k: False
        )
        captured: Dict[str, Any] = {}

        def _fake_agent_direct(simulation_id, agent_id, prompt, platform, timeout, **kwargs):
            captured.update(kwargs)
            return {"success": True, "agent_id": agent_id, "prompt": prompt}

        monkeypatch.setattr(
            interview_client, "interview_agent_direct", _fake_agent_direct
        )

        interview_client.interview_agent(
            "sim_0123456789ab",
            1,
            "x",
            run_state_dir=str(tmp_path),
            run_id="run-chain-2",
        )

        assert captured.get("run_id") == "run-chain-2"


# ---------------------------------------------------------------------------
# 4. ``SimulationRunner.interview_agents_batch`` reicht ``run_id`` durch
# ---------------------------------------------------------------------------


class TestSimulationRunnerForwardsRunId:
    def test_classmethod_forwards_run_id(self, monkeypatch) -> None:
        captured: Dict[str, Any] = {}

        def _fake(simulation_id, interviews, platform, timeout, **kwargs):
            captured.update(kwargs)
            return {"success": True}

        monkeypatch.setattr(
            "app.services.simulation_runner._interview_agents_batch_fn", _fake
        )

        SimulationRunner.interview_agents_batch(
            simulation_id="sim_0123456789ab",
            interviews=[{"agent_id": 1, "prompt": "x"}],
            run_id="run-runner-1",
        )

        assert captured.get("run_id") == "run-runner-1"


# ---------------------------------------------------------------------------
# 5. Budget-Guard + Ledger sehen den Interview-Call, sobald ``run_id`` gesetzt ist
# ---------------------------------------------------------------------------


class _RecordingEnforcer:
    def __init__(self) -> None:
        self.check_calls = 0
        self.record_calls = 0

    def check_before_call(self) -> None:
        self.check_calls += 1

    def record_after_call(self) -> None:
        self.record_calls += 1


class TestInterviewClientLandsInBudgetGuardAndLedger:
    """Ein ueber die Interview-Kette mit ``run_id`` gebauter ``LLMClient``
    triggert denselben Budget-Guard/Ledger-Pfad wie jeder andere LLM-Call —
    das ist der eigentliche Zweck der ``run_id``-Weitergabe."""

    def test_llm_client_built_with_run_id_engages_budget_guard_and_ledger(
        self, monkeypatch
    ) -> None:
        from types import SimpleNamespace

        from app.llm.client import LLMClient

        enforcer = _RecordingEnforcer()
        monkeypatch.setattr(
            "app.services.run_budget.RunBudgetEnforcer.for_run",
            classmethod(lambda cls, run_id: enforcer),
        )

        logged_events: List[Dict[str, Any]] = []

        class _FakeInvocationLogger:
            def __init__(self, run_id: str) -> None:
                self.run_id = run_id

            def log_event(self, **kwargs: Any) -> None:
                logged_events.append({"run_id": self.run_id, **kwargs})

        monkeypatch.setattr(
            "app.services.llm_invocation_logger.LlmInvocationLogger",
            _FakeInvocationLogger,
        )

        # Client-Bau spiegelt den Fallback-Zweig von ``_default_client_factory``:
        # nur ``timeout`` + ``run_id``, kein Route-Lookup noetig.
        client = LLMClient(
            model="test-model",
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            use_active_config=False,
            run_id="run-e2e-1",
        )
        monkeypatch.setattr(LLMClient, "_publish_model_active", lambda self, *a, **k: None)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )
        object.__setattr__(client, "_is_ollama", lambda: False)

        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Ich sehe das kritisch."),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=42, completion_tokens=9),
        )
        object.__setattr__(
            client,
            "client",
            SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=lambda **kwargs: response)
                )
            ),
        )

        result = client.chat(messages=[{"role": "user", "content": "Interview-Frage"}])

        assert result == "Ich sehe das kritisch."
        # Budget-Guard sieht den Call.
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        # Ledger sieht den Call, mit der richtigen run_id.
        assert len(logged_events) == 1
        assert logged_events[0]["run_id"] == "run-e2e-1"
        assert logged_events[0]["success"] is True


# ---------------------------------------------------------------------------
# 6. IPC-Zweig (lebender Worker) wird gegen das harte Report-Budget gehaertet
#    (#1478 Codex P1, Runde 5) — vorher trug der IPC-Zweig gar keinen
#    Budget-Check; run_id lief ins Leere.
# ---------------------------------------------------------------------------


class _ExhaustedEnforcer:
    """Simuliert ein bereits erschoepftes hartes Budget."""

    def __init__(self) -> None:
        self.record_calls = 0

    def check_before_call(self) -> None:
        from app.services.run_budget import BudgetExceededError

        raise BudgetExceededError("calls", 11, 10)

    def record_after_call(self) -> None:  # pragma: no cover - darf nicht erreicht werden
        self.record_calls += 1
        raise AssertionError(
            "record_after_call darf nach einer Ablehnung in check_before_call "
            "nicht erreicht werden"
        )


class TestInterviewClientIpcPathBlockedByHardBudget:
    def test_ipc_single_interview_blocked_before_ipc_command_is_sent(
        self, monkeypatch, tmp_path
    ) -> None:
        from app.services.run_budget import BudgetExceededError

        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        # Worker lebt -> interview_agent waehlt den IPC-Zweig.
        monkeypatch.setattr(interview_client, "check_env_alive", lambda *a, **k: True)
        monkeypatch.setattr(
            "app.services.run_budget.RunBudgetEnforcer.for_run",
            classmethod(lambda cls, run_id: _ExhaustedEnforcer()),
        )

        def _fail_send_interview(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                "IPC-Command darf bei erschoepftem hartem Budget nicht gesendet werden"
            )

        monkeypatch.setattr(
            interview_client.SimulationIPCClient, "send_interview", _fail_send_interview
        )

        with pytest.raises(BudgetExceededError):
            interview_client.interview_agent(
                "sim_0123456789ab",
                1,
                "Was hältst du davon?",
                run_state_dir=str(tmp_path),
                run_id="run-ipc-1",
            )

    def test_ipc_batch_interview_blocked_before_ipc_command_is_sent(
        self, monkeypatch, tmp_path
    ) -> None:
        from app.services.run_budget import BudgetExceededError

        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        monkeypatch.setattr(interview_client, "check_env_alive", lambda *a, **k: True)
        monkeypatch.setattr(
            "app.services.run_budget.RunBudgetEnforcer.for_run",
            classmethod(lambda cls, run_id: _ExhaustedEnforcer()),
        )

        def _fail_send_batch(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                "IPC-Command darf bei erschoepftem hartem Budget nicht gesendet werden"
            )

        monkeypatch.setattr(
            interview_client.SimulationIPCClient,
            "send_batch_interview",
            _fail_send_batch,
        )

        with pytest.raises(BudgetExceededError):
            interview_client.interview_agents_batch(
                "sim_0123456789ab",
                [{"agent_id": 1, "prompt": "x"}],
                run_state_dir=str(tmp_path),
                run_id="run-ipc-2",
            )

    def test_ipc_path_without_run_id_stays_unguarded(self, monkeypatch, tmp_path) -> None:
        """Kein bestehender Aufrufer ohne ``run_id`` darf Verhalten aendern —
        der Guard bleibt dann ein No-op und das IPC-Command wird gesendet."""
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        monkeypatch.setattr(interview_client, "check_env_alive", lambda *a, **k: True)

        def _boom_if_called(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                "RunBudgetEnforcer.for_run darf ohne run_id nicht aufgerufen werden"
            )

        monkeypatch.setattr(
            "app.services.run_budget.RunBudgetEnforcer.for_run",
            classmethod(_boom_if_called),
        )

        sent: Dict[str, Any] = {}

        class _Response:
            class _Status:
                value = "completed"

            status = _Status()
            result = {"interviews_count": 0, "results": {}}
            timestamp = "2026-09-08T00:00:00"

        def _fake_send_batch(
            self, interviews, platform=None, timeout=120.0, *, report_run_id=None
        ):
            sent["called"] = True
            sent["report_run_id"] = report_run_id
            return _Response()

        monkeypatch.setattr(
            interview_client.SimulationIPCClient,
            "send_batch_interview",
            _fake_send_batch,
        )

        result = interview_client.interview_agents_batch(
            "sim_0123456789ab",
            [{"agent_id": 1, "prompt": "x"}],
            run_state_dir=str(tmp_path),
        )

        assert sent.get("called") is True
        assert result["success"] is True


class _ReservationCountingEnforcer:
    """Zaehlt Reservierungen wie ``RunBudgetEnforcer`` es prozesslokal tut.

    ``check_before_call`` reserviert einen Slot und wirft, sobald mehr Slots
    gleichzeitig gehalten werden als das harte Limit erlaubt — genau die
    Mechanik, an der der Timeout-Fallback scheiterte, solange er noch
    innerhalb des Guards lief.
    """

    def __init__(self, hard_limit: int = 1) -> None:
        self.hard_limit = hard_limit
        self.in_flight = 0
        self.max_in_flight = 0

    def check_before_call(self) -> None:
        from app.services.run_budget import BudgetExceededError

        if self.in_flight + 1 > self.hard_limit:
            raise BudgetExceededError("calls", self.in_flight + 1, self.hard_limit)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)

    def record_after_call(self) -> None:
        self.in_flight = max(0, self.in_flight - 1)


class TestIpcTimeoutFallbackReleasesReservation:
    """#1478 Codex Runde 8.

    Laeuft der Direktpfad-Fallback noch INNERHALB von ``_report_budget_guard``,
    zaehlt sein eigener ``_budget_check()`` die Reservierung des Guards mit.
    Bei genau einem verbleibenden Call warf der Fallback deshalb
    ``BudgetExceededError``, obwohl der Ledger noch gar nichts verbraucht hat —
    und stoppte den Report faelschlich.
    """

    def _install(self, monkeypatch, tmp_path, *, batch: bool):
        enforcer = _ReservationCountingEnforcer(hard_limit=1)
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)

        monkeypatch.setattr(interview_client, "check_env_alive", lambda *a, **k: True)
        monkeypatch.setattr(
            "app.services.run_budget.RunBudgetEnforcer.for_run",
            classmethod(lambda cls, run_id: enforcer),
        )

        def _timeout(*args: Any, **kwargs: Any) -> Any:
            raise TimeoutError("Worker antwortet nicht")

        method = "send_batch_interview" if batch else "send_interview"
        monkeypatch.setattr(interview_client.SimulationIPCClient, method, _timeout)

        seen: dict[str, Any] = {}

        def _direct(*args: Any, **kwargs: Any) -> dict[str, Any]:
            # Der Direktpfad prueft im Produktivcode sein eigenes Budget ueber
            # denselben Enforcer. Genau dieser Aufruf muss gelingen.
            enforcer.check_before_call()
            seen["in_flight_beim_fallback"] = enforcer.in_flight
            enforcer.record_after_call()
            return {"success": True, "result": "direkt beantwortet"}

        target = "interview_agents_batch_direct" if batch else "interview_agent_direct"
        monkeypatch.setattr(interview_client, target, _direct)
        return enforcer, seen

    def test_single_interview_timeout_falls_back_without_budget_error(
        self, monkeypatch, tmp_path
    ) -> None:
        enforcer, seen = self._install(monkeypatch, tmp_path, batch=False)

        result = interview_client.interview_agent(
            "sim_0123456789ab",
            1,
            "Was hältst du davon?",
            run_state_dir=str(tmp_path),
            run_id="run-timeout-1",
        )

        assert result["success"] is True
        assert seen["in_flight_beim_fallback"] == 1, (
            "Der Fallback darf nur seine EIGENE Reservierung halten — die des "
            "Guards muss beim Verlassen des with-Blocks freigegeben sein"
        )
        assert enforcer.max_in_flight == 1
        assert enforcer.in_flight == 0

    def test_batch_interview_timeout_falls_back_without_budget_error(
        self, monkeypatch, tmp_path
    ) -> None:
        enforcer, seen = self._install(monkeypatch, tmp_path, batch=True)

        result = interview_client.interview_agents_batch(
            "sim_0123456789ab",
            [{"agent_id": 1, "prompt": "Was hältst du davon?"}],
            run_state_dir=str(tmp_path),
            run_id="run-timeout-2",
        )

        assert result["success"] is True
        assert seen["in_flight_beim_fallback"] == 1
        assert enforcer.max_in_flight == 1
        assert enforcer.in_flight == 0
