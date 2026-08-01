"""Tests für ``app.services.sim.interview_direct``.

Spezifikation des Direktpfads für Post-Simulations-Interviews: kein lebender
OASIS-Worker, kein IPC. Persona-Profile und Simulationskontext sind
persistiert, der LLM-Call läuft im Flask-Prozess über ``LLMClient.chat`` —
eine Interview-Antwort ist Freitext, kein strukturiertes JSON.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.services.sim import interview_direct
from app.services.sim.interview_direct import (
    direct_interviews_available,
    interview_agent_direct,
    interview_agents_batch_direct,
)


PROFILES: List[Dict[str, Any]] = [
    {
        "user_id": 1,
        "username": "lena_k",
        "name": "Lena Krüger",
        "bio": "Product Ownerin in einem mittelständischen SaaS-Team",
        "persona": "Skeptisch gegenüber neuen Tools, achtet auf Datenschutz.",
        "age": 38,
        "country": "DE",
        "profession": "Product Ownerin",
        "interested_topics": ["SaaS", "Datenschutz"],
    },
    {
        "user_id": 2,
        "username": "tom_b",
        "name": "Tom Berger",
        "bio": "Freelancer für Datenanalyse",
        "persona": "Frühadopter, testet gerne neue Werkzeuge.",
        "age": 29,
        "country": "AT",
        "profession": "Datenanalyst",
        "interested_topics": ["Analytics"],
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
    """Zeichnet die chat-Aufrufe auf und liefert eine feste Freitext-Antwort."""

    def __init__(self, response: str = "Ich sehe das kritisch.") -> None:
        self.response = response
        self.calls: List[Dict[str, Any]] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self.response


# ---------------------------------------------------------------------------
# direct_interviews_available
# ---------------------------------------------------------------------------


class TestDirectInterviewsAvailable:
    def test_false_without_profiles(self, tmp_path) -> None:
        store = _store_mock(profiles=[])
        with patch.object(interview_direct, "_store", return_value=store):
            assert (
                direct_interviews_available("sim_0123456789ab", run_state_dir=str(tmp_path))
                is False
            )

    def test_true_with_reddit_profiles(self, tmp_path) -> None:
        store = _store_mock()
        with patch.object(interview_direct, "_store", return_value=store):
            assert (
                direct_interviews_available("sim_0123456789ab", run_state_dir=str(tmp_path))
                is True
            )

    def test_false_when_store_raises(self, tmp_path) -> None:
        store = MagicMock()
        store.read_json.side_effect = OSError("store kaputt")
        with patch.object(interview_direct, "_store", return_value=store):
            assert (
                direct_interviews_available("sim_0123456789ab", run_state_dir=str(tmp_path))
                is False
            )


# ---------------------------------------------------------------------------
# interview_agents_batch_direct
# ---------------------------------------------------------------------------


class TestBatchDirect:
    def _run(self, tmp_path, interviews, client=None, **kwargs):
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)
        client = client or _FakeLLMClient()
        store = _store_mock()
        with patch.object(interview_direct, "_store", return_value=store):
            result = interview_agents_batch_direct(
                "sim_0123456789ab",
                interviews,
                run_state_dir=str(tmp_path),
                client_factory=lambda: client,
                **kwargs,
            )
        return result, client

    def test_returns_ipc_compatible_shape(self, tmp_path) -> None:
        result, _ = self._run(tmp_path, [{"agent_id": 0, "prompt": "Was hältst du davon?"}])

        assert result["success"] is True
        assert result["interviews_count"] == 1
        assert result["mode"] == "direct"
        entry = result["result"]["results"]["reddit_0"]
        assert entry["agent_id"] == 0
        assert entry["platform"] == "reddit"
        assert entry["response"] == "Ich sehe das kritisch."
        assert entry["simulated"] is True
        assert result["result"]["interviews_count"] == 1

    def test_uses_persona_and_context_in_system_prompt(self, tmp_path) -> None:
        _, client = self._run(tmp_path, [{"agent_id": 0, "prompt": "Frage?"}])

        assert len(client.calls) == 1
        messages = client.calls[0]["messages"]
        system = messages[0]["content"]
        assert messages[0]["role"] == "system"
        assert "Lena Krüger" in system
        assert "Product Ownerin" in system
        assert "Skeptisch gegenüber neuen Tools" in system
        assert "Wie lässt sich das Onboarding verbessern?" in system
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Frage?"

    def test_uses_freetext_chat_not_json_mode(self, tmp_path) -> None:
        """Interview-Antworten sind Prosa — kein JSON-Schema-Wrapper."""
        _, client = self._run(tmp_path, [{"agent_id": 1, "prompt": "Frage?"}])

        assert "schema" not in client.calls[0]
        assert client.calls[0]["context"] == "chat"

    def test_multiple_agents_are_keyed_per_agent(self, tmp_path) -> None:
        result, client = self._run(
            tmp_path,
            [
                {"agent_id": 0, "prompt": "Frage A"},
                {"agent_id": 1, "prompt": "Frage B"},
            ],
        )

        assert set(result["result"]["results"]) == {"reddit_0", "reddit_1"}
        assert len(client.calls) == 2

    def test_unknown_agent_id_fails_only_that_item(self, tmp_path) -> None:
        result, _ = self._run(
            tmp_path,
            [
                {"agent_id": 0, "prompt": "Frage A"},
                {"agent_id": 99, "prompt": "Frage B"},
            ],
        )

        assert result["success"] is True
        assert result["result"]["results"]["reddit_0"]["response"]
        failed = result["result"]["results"]["reddit_99"]
        assert failed["response"] is None
        assert "error" in failed

    def test_all_items_failing_yields_success_false(self, tmp_path) -> None:
        result, _ = self._run(tmp_path, [{"agent_id": 99, "prompt": "Frage"}])

        assert result["success"] is False

    def test_llm_error_is_captured_per_item(self, tmp_path) -> None:
        client = _FakeLLMClient()
        client.chat = MagicMock(side_effect=RuntimeError("provider weg"))

        result, _ = self._run(tmp_path, [{"agent_id": 0, "prompt": "Frage"}], client=client)

        assert result["success"] is False
        assert "provider weg" in result["result"]["results"]["reddit_0"]["error"]

    def test_persists_interview_into_trace_db(self, tmp_path) -> None:
        self._run(tmp_path, [{"agent_id": 0, "prompt": "Was hältst du davon?"}])

        db_path = tmp_path / "sim_0123456789ab" / "reddit_simulation.db"
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT user_id, action, info FROM trace WHERE action = 'interview'"
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        user_id, _action, info_json = rows[0]
        assert user_id == 0
        info = json.loads(info_json)
        assert info["response"] == "Ich sehe das kritisch."
        assert info["prompt"] == "Was hältst du davon?"
        assert info["source"] == "direct"

    def test_empty_interviews_returns_failure_without_llm_call(self, tmp_path) -> None:
        result, client = self._run(tmp_path, [])

        assert result["success"] is False
        assert client.calls == []

    def test_raises_when_no_personas_available(self, tmp_path) -> None:
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)
        store = _store_mock(profiles=[])
        with patch.object(interview_direct, "_store", return_value=store):
            with pytest.raises(ValueError, match="Persona"):
                interview_agents_batch_direct(
                    "sim_0123456789ab",
                    [{"agent_id": 0, "prompt": "Frage"}],
                    run_state_dir=str(tmp_path),
                    client_factory=lambda: _FakeLLMClient(),
                )


# ---------------------------------------------------------------------------
# interview_agent_direct
# ---------------------------------------------------------------------------


class TestPlatformResolution:
    """Ein platform-Override je Item muss die Personas dieser Plattform treffen."""

    TWITTER_PROFILES = [
        {"user_id": 0, "name": "Nina Twitter", "user_char": "Kurzform-Persona"},
    ]

    def _store_with_both(self) -> MagicMock:
        store = MagicMock()

        def read_json(simulation_id, name, default=None):
            if name == "reddit_profiles":
                return PROFILES
            if name == "simulation_config":
                return SIM_CONFIG
            return default

        store.read_json.side_effect = read_json
        return store

    def test_item_platform_override_uses_that_platform_personas(self, tmp_path) -> None:
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir()
        (sim_dir / "twitter_profiles.csv").write_text(
            "user_id,name,username,user_char,description\n"
            "0,Nina Twitter,nina,Kurzform-Persona,Bio\n",
            encoding="utf-8",
        )
        client = _FakeLLMClient()

        with patch.object(interview_direct, "_store", return_value=self._store_with_both()):
            result = interview_agents_batch_direct(
                "sim_0123456789ab",
                [{"agent_id": 0, "prompt": "Frage", "platform": "twitter"}],
                run_state_dir=str(tmp_path),
                client_factory=lambda: client,
            )

        entry = result["result"]["results"]["twitter_0"]
        assert entry["platform"] == "twitter"
        assert "Nina Twitter" in client.calls[0]["messages"][0]["content"]

    def test_twitter_only_run_is_answerable(self, tmp_path) -> None:
        """Ein Lauf ohne reddit_profiles darf nicht am Default scheitern."""
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir()
        (sim_dir / "twitter_profiles.csv").write_text(
            "user_id,name,username,user_char,description\n"
            "0,Nina Twitter,nina,Kurzform-Persona,Bio\n",
            encoding="utf-8",
        )
        store = _store_mock(profiles=[])
        client = _FakeLLMClient()

        with patch.object(interview_direct, "_store", return_value=store):
            result = interview_agents_batch_direct(
                "sim_0123456789ab",
                [{"agent_id": 0, "prompt": "Frage"}],
                run_state_dir=str(tmp_path),
                client_factory=lambda: client,
            )

        assert result["success"] is True
        assert result["result"]["results"]["twitter_0"]["response"]


class TestBatchDeadline:
    def test_items_after_the_deadline_are_marked_not_started(self, tmp_path) -> None:
        """`timeout` ist eine Deadline fuer den Batch, nicht pro Item."""
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir()
        store = _store_mock()
        clock = iter([0.0, 0.0, 999.0, 999.0, 999.0, 999.0])
        client = _FakeLLMClient()

        with patch.object(interview_direct, "_store", return_value=store), patch.object(
            interview_direct.time, "monotonic", side_effect=lambda: next(clock)
        ):
            result = interview_agents_batch_direct(
                "sim_0123456789ab",
                [
                    {"agent_id": 0, "prompt": "Frage A"},
                    {"agent_id": 1, "prompt": "Frage B"},
                ],
                timeout=30.0,
                run_state_dir=str(tmp_path),
                client_factory=lambda: client,
                # Sequentiell, damit die Uhr deterministisch abgefragt wird.
                max_workers=1,
            )

        entries = result["result"]["results"]
        assert entries["reddit_0"]["response"]
        assert "Deadline" in entries["reddit_1"]["error"]
        assert len(client.calls) == 1


class TestClientFactory:
    def test_prefers_the_route_persisted_with_the_run(self, tmp_path) -> None:
        """Die aktive Workspace-Auswahl darf das Interview-Modell nicht verschieben."""
        captured: List[Dict[str, Any]] = []

        class _Client:
            def __init__(self, **kwargs):
                captured.append(kwargs)

            def chat(self, messages, **_kwargs):
                return "Antwort"

        context = {
            "requirement": "",
            "language": "de",
            "llm_model": "MiniMax-M3",
            "llm_base_url": "https://api.example.test/v1",
        }
        with patch.dict("sys.modules"):
            import app.llm.client as llm_client_module

            with patch.object(llm_client_module, "LLMClient", _Client):
                factory = interview_direct._default_client_factory(90.0, context)
                factory()

        assert captured[0]["model"] == "MiniMax-M3"
        assert captured[0]["base_url"] == "https://api.example.test/v1"
        assert captured[0]["timeout"] == 90.0

    def test_falls_back_to_active_config_when_route_unusable(self, tmp_path) -> None:
        attempts: List[Dict[str, Any]] = []

        class _Client:
            def __init__(self, **kwargs):
                attempts.append(kwargs)
                if kwargs.get("model"):
                    raise ValueError("LLM_API_KEY not configured")

        context = {"llm_model": "tot", "llm_base_url": ""}
        import app.llm.client as llm_client_module

        with patch.object(llm_client_module, "LLMClient", _Client):
            interview_direct._default_client_factory(60.0, context)()

        assert len(attempts) == 2
        assert attempts[1] == {"timeout": 60.0}


class TestInterviewClientRouting:
    """``interview_client`` muss auf den Direktpfad routen, wenn kein Poller lebt."""

    def _sim_dir(self, tmp_path):
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)
        return sim_dir

    def test_batch_falls_back_to_direct_when_env_not_alive(self, tmp_path) -> None:
        from app.services.sim import interview_client

        self._sim_dir(tmp_path)
        ipc = MagicMock()
        ipc.check_env_alive.return_value = False

        with patch.object(interview_client, "SimulationIPCClient", return_value=ipc), patch.object(
            interview_client, "interview_agents_batch_direct", return_value={"success": True}
        ) as direct:
            result = interview_client.interview_agents_batch(
                "sim_0123456789ab",
                [{"agent_id": 0, "prompt": "Frage"}],
                run_state_dir=str(tmp_path),
            )

        assert result == {"success": True}
        direct.assert_called_once()
        ipc.send_batch_interview.assert_not_called()

    def test_single_falls_back_to_direct_when_env_not_alive(self, tmp_path) -> None:
        from app.services.sim import interview_client

        self._sim_dir(tmp_path)
        ipc = MagicMock()
        ipc.check_env_alive.return_value = False

        with patch.object(interview_client, "SimulationIPCClient", return_value=ipc), patch.object(
            interview_client, "interview_agent_direct", return_value={"success": True}
        ) as direct:
            result = interview_client.interview_agent(
                "sim_0123456789ab",
                agent_id=0,
                prompt="Frage",
                run_state_dir=str(tmp_path),
            )

        assert result == {"success": True}
        direct.assert_called_once()
        ipc.send_interview.assert_not_called()

    def test_env_counts_as_dead_when_run_state_is_terminal(self, tmp_path) -> None:
        """``env_status.json`` bleibt nach dem Lauf auf ``alive`` — Run-State schlägt das."""
        from app.services.sim import interview_client

        self._sim_dir(tmp_path)
        ipc = MagicMock()
        ipc.check_env_alive.return_value = True
        run_state = MagicMock()
        run_state.runner_status = "completed"

        with patch.object(interview_client, "SimulationIPCClient", return_value=ipc), patch.object(
            interview_client, "load_run_state", return_value=run_state
        ):
            assert (
                interview_client.check_env_alive(
                    "sim_0123456789ab", run_state_dir=str(tmp_path)
                )
                is False
            )
        ipc.check_env_alive.assert_not_called()

    def test_ipc_timeout_falls_back_to_direct(self, tmp_path) -> None:
        """Ein als lebendig geltender Poller, der nicht antwortet, darf nicht haengen."""
        from app.services.sim import interview_client

        self._sim_dir(tmp_path)
        ipc = MagicMock()
        ipc.check_env_alive.return_value = True
        ipc.send_batch_interview.side_effect = TimeoutError("keine Antwort")

        with patch.object(interview_client, "SimulationIPCClient", return_value=ipc), patch.object(
            interview_client, "load_run_state", return_value=None
        ), patch.object(
            interview_client, "interview_agents_batch_direct", return_value={"success": True}
        ) as direct:
            result = interview_client.interview_agents_batch(
                "sim_0123456789ab",
                [{"agent_id": 0, "prompt": "Frage"}],
                run_state_dir=str(tmp_path),
            )

        assert result == {"success": True}
        direct.assert_called_once()

    def test_ipc_path_still_used_when_env_alive(self, tmp_path) -> None:
        from app.services.sim import interview_client

        self._sim_dir(tmp_path)
        ipc = MagicMock()
        ipc.check_env_alive.return_value = True
        response = MagicMock()
        response.status.value = "completed"
        response.result = {"results": {}}
        response.timestamp = "2026-08-01T12:00:00"
        ipc.send_batch_interview.return_value = response

        with patch.object(interview_client, "SimulationIPCClient", return_value=ipc), patch.object(
            interview_client, "interview_agents_batch_direct"
        ) as direct:
            result = interview_client.interview_agents_batch(
                "sim_0123456789ab",
                [{"agent_id": 0, "prompt": "Frage"}],
                run_state_dir=str(tmp_path),
            )

        assert result["success"] is True
        direct.assert_not_called()
        ipc.send_batch_interview.assert_called_once()


class TestSingleDirect:
    def test_single_interview_shape(self, tmp_path) -> None:
        sim_dir = tmp_path / "sim_0123456789ab"
        sim_dir.mkdir(exist_ok=True)
        client = _FakeLLMClient("Passt für mich.")
        store = _store_mock()
        with patch.object(interview_direct, "_store", return_value=store):
            result = interview_agent_direct(
                "sim_0123456789ab",
                agent_id=1,
                prompt="Und du?",
                run_state_dir=str(tmp_path),
                client_factory=lambda: client,
            )

        assert result["success"] is True
        assert result["agent_id"] == 1
        assert result["prompt"] == "Und du?"
        assert result["mode"] == "direct"
        assert result["result"]["response"] == "Passt für mich."
        assert result["result"]["platform"] == "reddit"
