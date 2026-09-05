"""Regression zu Issue #1423 — CLI-Transport erreicht die Simulationsrunden.

Vorher: ``codex_cli`` (transport="cli", #1405) hat weder ``base_url`` noch
``api_key``. ``build_route_subprocess_env`` setzte deshalb kein
``LLM_BASE_URL``, der OASIS-Subprozess erbte ueber ``SAFE_ENV_KEYS`` die
``.env``-URL des Backends und schickte das geroutete Modell dorthin —
beobachtet als ``400 invalid params, unknown model 'gpt-5.6-luna' (2013)``
gegen ``api.minimax.io``, waehrend Ontologie, Graph und Personas seit #1418
korrekt liefen.

Die Tests decken die drei Glieder der Kette ab: Env-Aufbau, Env-Vererbung im
``process_manager`` und das CAMEL-Backend, das die CLI ohne HTTP anspricht.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.llm.providers.codex_cli import (
    CLI_TRANSPORT_VALUE,
    CODEX_CLI_BINARY_ENV,
    TRANSPORT_ENV_KEY,
    build_shim_message,
    build_tool_prompt,
    parse_tool_calls,
    strip_tool_calls,
    _flatten_messages,
)
from app.services.llm_routing_seed import build_route_subprocess_env

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _route(provider_id: str, base_url: str | None) -> ResolvedRoute:
    return ResolvedRoute(
        stage="simulation_rounds",
        provider_id=provider_id,
        model="gpt-5.6-luna",
        base_url_sanitized=base_url,
        routing_version=1,
    )


class TestSubprocessEnvForCliTransport:
    """Erstes Glied: was ``build_route_subprocess_env`` in die Env schreibt."""

    def test_cli_provider_sets_transport_signal_and_no_base_url(self):
        env = build_route_subprocess_env(_route("codex_cli", None), api_key=None)

        assert env[TRANSPORT_ENV_KEY] == CLI_TRANSPORT_VALUE
        # Der Kern des Defekts: stuende hier eine URL — oder fehlte das Signal,
        # das ``process_manager`` zum Loeschen des geerbten Werts bewegt —,
        # ginge das Codex-Modell wieder an einen fremden HTTP-Endpunkt.
        assert "LLM_BASE_URL" not in env
        assert env["LLM_MODEL_NAME"] == "gpt-5.6-luna"

    def test_http_provider_keeps_base_url_and_gets_no_signal(self):
        """Gegenprobe: HTTP-Provider duerfen sich nicht veraendern."""
        env = build_route_subprocess_env(
            _route("openai", "https://api.openai.com/v1"), api_key="sk-test"
        )

        assert TRANSPORT_ENV_KEY not in env
        assert env["LLM_BASE_URL"] == "https://api.openai.com/v1"
        assert env["OPENAI_API_KEY"] == "sk-test"


class TestProcessManagerDropsInheritedBaseUrl:
    """Zweites Glied: ``SAFE_ENV_KEYS`` vererbt ``LLM_BASE_URL`` — ausser bei CLI."""

    def test_llm_base_url_is_in_the_inheritance_whitelist(self):
        """Belegt die Ursache: ohne aktives Loeschen wird geerbt."""
        from app.services.sim.process_manager import SAFE_ENV_KEYS

        assert "LLM_BASE_URL" in SAFE_ENV_KEYS

    def test_codex_cli_binary_env_is_inheritable(self):
        """Der Subprozess muss dieselbe CLI finden wie das Backend."""
        from app.services.sim.process_manager import SAFE_ENV_KEYS

        assert "AGORA_CODEX_CLI_BIN" in SAFE_ENV_KEYS
        assert "AGORA_CODEX_CLI_TIMEOUT_SECONDS" in SAFE_ENV_KEYS

    def test_api_key_is_never_inherited(self):
        """Unveraendert aus dem Code-Review 2026-05-17 §1.6 — hier mitgeprueft,
        weil dieser Fix die Whitelist anfasst."""
        from app.services.sim.process_manager import SAFE_ENV_KEYS

        assert "LLM_API_KEY" not in SAFE_ENV_KEYS
        assert "OPENAI_API_KEY" not in SAFE_ENV_KEYS


class TestToolCallEmulation:
    """``codex exec`` kennt kein Function-Calling — OASIS-Agenten brauchen es."""

    def test_tool_prompt_lists_schemas(self):
        prompt = build_tool_prompt(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "create_post",
                        "description": "Erstellt einen Beitrag",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        )

        assert "create_post" in prompt
        assert "Erstellt einen Beitrag" in prompt
        assert "<tool_call>" in prompt

    def test_tool_prompt_is_empty_without_usable_schemas(self):
        assert build_tool_prompt([]) == ""
        assert build_tool_prompt([{"type": "function"}]) == ""

    def test_parse_extracts_name_and_parameters(self):
        calls = parse_tool_calls(
            'Ich poste.\n<tool_call>\n{"name": "create_post", '
            '"parameters": {"content": "Hallo"}}\n</tool_call>'
        )

        assert calls == [{"name": "create_post", "parameters": {"content": "Hallo"}}]

    def test_parse_accepts_call_without_parameters(self):
        """Parameterlose Werkzeuge wie ``refresh`` duerfen nicht verloren gehen."""
        calls = parse_tool_calls('<tool_call>{"name": "refresh"}</tool_call>')

        assert calls == [{"name": "refresh", "parameters": {}}]

    def test_parse_skips_broken_blocks_instead_of_raising(self):
        """Ein unparsbarer Block darf den Turn nicht kippen — die Antwort ist
        dann eben Prosa statt eines Aufrufs."""
        assert parse_tool_calls("<tool_call>{kaputt</tool_call>") == []
        assert parse_tool_calls("nur prosa") == []

    def test_strip_removes_blocks_but_keeps_prose(self):
        text = 'Denke nach.\n<tool_call>{"name": "x", "parameters": {}}</tool_call>'

        assert strip_tool_calls(text) == "Denke nach."

    def test_shim_message_carries_tool_calls(self):
        message = build_shim_message(
            '<tool_call>{"name": "like_post", "parameters": {"post_id": 7}}</tool_call>'
        )

        assert message.tool_calls is not None
        assert message.tool_calls[0].function.name == "like_post"
        assert '"post_id": 7' in message.tool_calls[0].function.arguments

    def test_shim_message_without_tools_is_plain_text(self):
        message = build_shim_message("Einfach nur Text.")

        assert message.tool_calls is None
        assert message.content == "Einfach nur Text."


class TestInProcessToolRouting:
    """CodeRabbit-Finding zu #1423: die Emulation muss auch in-process greifen.

    ``LLMClient._detect_provider()`` meldet für codex_cli bewusst ``"unknown"``
    (es wird nie aus einer base_url erraten). Der Unknown-Short-Circuit in
    ``chat_with_tools`` fiel deshalb auf ``chat()`` ohne ``tools`` zurück —
    die Werkzeuge erreichten ``_CodexCliCompletions.create`` nie, und der
    Report-Agent blieb dauerhaft im XML-Fallback.
    """

    def test_codex_cli_reaches_the_tool_capable_path(self, monkeypatch):
        from app.contracts.provider_types import PROVIDER_CODEX_CLI
        from app.llm.client import LLMClient

        client = LLMClient(
            model="gpt-5.6-luna",
            provider_type=PROVIDER_CODEX_CLI,
            use_active_config=False,
        )
        # Vorbedingung des Findings: der Provider meldet sich als "unknown".
        assert client._detect_provider() == "unknown"

        seen: dict = {}

        class _Completions:
            def create(self, **kwargs):
                seen.update(kwargs)
                from app.llm.providers.codex_cli import build_shim_message

                return type(
                    "R",
                    (),
                    {
                        "choices": [
                            type(
                                "C",
                                (),
                                {
                                    "message": build_shim_message(
                                        '<tool_call>{"name": "trend", "parameters": {}}</tool_call>'
                                    ),
                                    "finish_reason": "stop",
                                },
                            )()
                        ],
                        "usage": None,
                    },
                )()

        client.client = type("Cl", (), {"chat": type("Ch", (), {"completions": _Completions()})()})()
        client.model = "gpt-5.6-luna"
        client.base_url = None
        client.api_key = "codex-cli-local-session"

        tools = [{"type": "function", "function": {"name": "trend", "parameters": {}}}]
        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "was ist trending?"}], tools=tools
        )

        # Kern: tools sind beim Shim angekommen, nicht im chat()-Fallback verschwunden.
        assert seen.get("tools") == tools
        # ``ToolCallResponse`` ist ein TypedDict, seine Eintraege sind flache
        # ``ToolCallItem``-Dicts (id/name/arguments) — kein OpenAI-function-Wrapper.
        assert [tc["name"] for tc in result["tool_calls"]] == ["trend"]


class TestFlattenMessages:
    """Die CLI kennt keine Chat-Turn-Struktur — die Zuordnung muss im Text bleiben."""

    def test_tool_result_keeps_call_id(self):
        flat = _flatten_messages(
            [{"role": "tool", "tool_call_id": "call_codex_0", "content": "42"}]
        )

        assert "tool_call_id=call_codex_0" in flat
        assert "42" in flat

    def test_tool_call_survives_alongside_assistant_prose(self):
        """CodeRabbit-Finding zu #1423: eine CLI-Antwort darf Prosa UND einen
        Aufruf enthalten, und ``build_shim_message`` behaelt die Prosa als
        ``content``. Eine Bedingung ``if not content`` haette den Aufruf in
        genau diesem — dem haeufigen — Fall verschluckt; der naechste Prompt
        haette nur die synthetische ID gezeigt und das Modell haette dasselbe
        Werkzeug erneut aufgerufen."""
        flat = _flatten_messages(
            [
                {
                    "role": "assistant",
                    "content": "Ich schaue kurz nach.",
                    "tool_calls": [
                        {
                            "id": "call_codex_0",
                            "function": {"name": "trend", "arguments": "{}"},
                        }
                    ],
                }
            ]
        )

        assert "Ich schaue kurz nach." in flat
        assert "trend" in flat
        assert "<tool_call>" in flat

    def test_prior_assistant_tool_call_is_reconstructed(self):
        """Ein Assistant-Turn mit ``tool_calls`` traegt seinen Inhalt nicht in
        ``content``. Ohne Rekonstruktion saehe das Modell eine leere Nachricht
        und riefe dasselbe Werkzeug erneut auf."""
        flat = _flatten_messages(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_codex_0",
                            "function": {
                                "name": "search_posts",
                                "arguments": '{"query": "test"}',
                            },
                        }
                    ],
                }
            ]
        )

        assert "search_posts" in flat
        assert "<tool_call>" in flat


class TestCodexCliModel:
    """Drittes Glied: das CAMEL-Backend selbst."""

    @pytest.fixture()
    def model(self):
        from sim_runtime.codex_cli_model import CodexCliModel

        return CodexCliModel(model_type="gpt-5.6-luna")

    def test_transport_flag_reads_env(self, monkeypatch):
        from sim_runtime.codex_cli_model import cli_transport_active

        monkeypatch.delenv(TRANSPORT_ENV_KEY, raising=False)
        assert cli_transport_active() is False

        monkeypatch.setenv(TRANSPORT_ENV_KEY, CLI_TRANSPORT_VALUE)
        assert cli_transport_active() is True

    def test_token_counter_is_available(self, model):
        """CAMEL braucht ihn zum Kuerzen von Nachrichten; die CLI liefert keine
        Usage-Zahlen, also muss das Backend selbst einen stellen."""
        assert model.token_counter is not None

    def test_completion_with_tool_call_sets_finish_reason(self, model):
        completion = model._to_completion(
            'Ok.\n<tool_call>{"name": "create_post", "parameters": {"content": "hi"}}</tool_call>'
        )
        choice = completion.choices[0]

        assert choice.finish_reason == "tool_calls"
        assert choice.message.tool_calls[0].function.name == "create_post"
        assert choice.message.content == "Ok."

    def test_completion_without_tool_call_is_plain_stop(self, model):
        completion = model._to_completion("Reine Prosa.")
        choice = completion.choices[0]

        assert choice.finish_reason == "stop"
        assert choice.message.tool_calls is None
        assert choice.message.content == "Reine Prosa."

    def test_usage_is_zero_not_invented(self, model):
        """``codex exec`` meldet keine Token. Eine geschaetzte Zahl waere im
        Kosten-Logging (``sim_runtime/budget_guard.py``) schlicht erfunden —
        beim ChatGPT-Abo faellt ohnehin keine Token-Gebuehr an."""
        completion = model._to_completion("x")

        assert completion.usage.total_tokens == 0

    def test_arun_runs_calls_concurrently(self, model, monkeypatch):
        """Tragend fuer die Laufzeit: OASIS treibt alle Agenten einer Runde
        nebenlaeufig. Blockierte ein Aufruf den Event-Loop, fiele die
        Simulation von paralleler auf serielle Ausfuehrung zurueck — bei
        ~8-40 s pro Aufruf der Unterschied zwischen Minuten und Stunden.

        Gemessen statt behauptet: drei Aufrufe mit je 0,3 s muessen zusammen
        deutlich unter der seriellen Summe von 0,9 s bleiben.
        """
        import asyncio
        import time

        async def _slow(_prompt: str) -> str:
            await asyncio.sleep(0.3)
            return "ok"

        monkeypatch.setattr(model, "_ainvoke", _slow)

        async def _drive():
            msgs = [{"role": "user", "content": "ping"}]
            return await asyncio.gather(*(model._arun(msgs) for _ in range(3)))

        t0 = time.monotonic()
        completions = asyncio.run(_drive())
        elapsed = time.monotonic() - t0

        assert [c.choices[0].message.content for c in completions] == ["ok"] * 3
        assert elapsed < 0.7, f"Aufrufe liefen seriell ({elapsed:.2f}s statt ~0.3s)"

    def test_cancellation_kills_the_child_process(self, model, monkeypatch):
        """CodeRabbit-Finding zu #1423: ein Thread laesst sich nicht abbrechen.

        Wird ein Agent-Task gecancelt (Simulation gestoppt, Runden-Timeout),
        liefe der CLI-Prozess sonst bis zum 180-s-Timeout weiter und bliebe
        an Worker und Kindprozess haengen. Der Test startet statt ``codex``
        ein langlaufendes ``sleep`` und prueft, dass der Abbruch es beendet.
        """
        import asyncio

        # ``build_codex_cli_command`` prueft das Binary im PATH, bevor der
        # Spy unten ueberhaupt greift. Auf CI-Runnern ist ``codex`` nicht
        # installiert — ``sleep`` ist es ueberall und erfuellt dasselbe Gate.
        monkeypatch.setenv(CODEX_CLI_BINARY_ENV, "sleep")

        async def _drive():
            # ``sleep 60`` als Platzhalter fuer einen haengenden codex-Aufruf.
            proc_holder = {}
            original = asyncio.create_subprocess_exec

            async def _spy(*_cmd, **kwargs):
                proc = await original("sleep", "60", **kwargs)
                proc_holder["proc"] = proc
                return proc

            asyncio.create_subprocess_exec = _spy  # type: ignore[assignment]
            try:
                task = asyncio.ensure_future(model._ainvoke("prompt"))
                # Aktiv auf den Start warten statt fix zu schlafen: unter
                # CI-Last reichte eine feste Wartezeit nicht und der Test
                # cancelte, bevor es ueberhaupt einen Kindprozess gab.
                deadline = asyncio.get_running_loop().time() + 10.0
                while "proc" not in proc_holder:
                    assert asyncio.get_running_loop().time() < deadline, (
                        "Kindprozess wurde nicht gestartet"
                    )
                    await asyncio.sleep(0.02)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                return proc_holder["proc"]
            finally:
                asyncio.create_subprocess_exec = original  # type: ignore[assignment]

        proc = asyncio.run(_drive())

        # Der Kindprozess hat den abgebrochenen Task nicht ueberlebt.
        assert proc.returncode is not None

    def test_cli_failure_becomes_runtime_error(self, model, monkeypatch):
        """OASIS faengt Modellfehler pro Agent ab. Ein durchgereichter
        CLI-Fehler wuerde sonst den gesamten Runden-Fan-out kippen."""
        from app.llm.providers import codex_cli as codex_module

        def _boom(*_args, **_kwargs):
            raise codex_module.CodexCliUnavailableError("kein Login")

        monkeypatch.setattr(codex_module, "_run_codex_cli", _boom)
        monkeypatch.setattr(
            "sim_runtime.codex_cli_model._run_codex_cli", _boom, raising=False
        )

        with pytest.raises(RuntimeError, match="codex_cli"):
            model._invoke("prompt")
