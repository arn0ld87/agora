"""CAMEL-Model-Backend fuer den Claude-CLI-Transport.

Analog zu ``codex_cli_model.py`` (Issue #1423), aber fuer ``claude_cli``: der
OASIS-Subprozess baut seine Agenten ueber ``camel.models`` und importiert die
bereits im Backend genutzte ``app.llm.providers.claude_cli``-Bruecke, statt
sie zu duplizieren.

Zwei Eigenheiten bestimmen den Aufbau (dieselben wie bei codex_cli_model.py):

1. **Kein natives Function-Calling.** ``build_tool_prompt``/``parse_tool_calls``
   uebernehmen die Prompt-basierte Werkzeug-Uebersetzung — dasselbe Protokoll
   wie codex_cli_model.py, damit OASIS-Agenten provider-unabhaengig
   funktionieren.
2. **Ein Subprozess pro Anfrage, isoliertes HOME.** ``_arun`` blockiert nicht
   synchron (``asyncio.create_subprocess_exec`` statt ``asyncio.to_thread``),
   UND jeder Aufruf bekommt ein frisches, leeres ``$HOME`` — ohne das laedt
   die CLI das interaktive Setup des Hosts in den Prompt-Cache (~64x Kosten,
   siehe ``app.llm.providers.claude_cli``-Modul-Docstring).

Der OAuth-Token kommt aus der Env-Var ``CLAUDE_CODE_OAUTH_TOKEN``, die
``llm_routing_seed.build_route_subprocess_env`` fuer diese Route bereits in
die Subprozess-Umgebung schreibt (generischer ``provider.api_key_ref``-
Mechanismus, kein claude_cli-Sonderfall dort).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Type

from camel.models import BaseModelBackend  # type: ignore[import]
from camel.types import ModelType  # type: ignore[import]
from camel.utils import BaseTokenCounter, OpenAITokenCounter  # type: ignore[import]
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from openai.types.completion_usage import CompletionUsage
from pydantic import BaseModel

from app.llm.providers.claude_cli import (
    CLAUDE_CLI_DEFAULT_MODEL_ID,
    ClaudeCliUnavailableError,
    _flatten_messages,
    _isolated_home,
    build_claude_cli_command,
    build_tool_prompt,
    claude_cli_scratch_dir_prefix,
    claude_cli_timeout_seconds,
    interpret_claude_cli_result,
    parse_tool_calls,
    strip_tool_calls,
)
from app.llm.providers.codex_cli import CLI_PROVIDER_ENV_KEY

logger = logging.getLogger(__name__)

CLAUDE_CLI_PROVIDER_ID = "claude_cli"


async def _terminate(proc: "asyncio.subprocess.Process") -> None:
    """Kindprozess beenden und einsammeln — identisch zu codex_cli_model."""
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.kill()
    with contextlib.suppress(Exception):  # noqa: BLE001 — Aufraeumpfad
        await proc.wait()


def claude_cli_transport_active() -> bool:
    """True, wenn dieser Subprozess speziell auf claude_cli laufen soll.

    ``cli_transport_active()`` (codex_cli_model) sagt nur "irgendein
    CLI-Provider" — dieses Modul prueft zusaetzlich ``CLI_PROVIDER_ENV_KEY``,
    um sich von codex_cli abzugrenzen.
    """
    return os.environ.get(CLI_PROVIDER_ENV_KEY, "").strip() == CLAUDE_CLI_PROVIDER_ID


class ClaudeCliModel(BaseModelBackend):
    """``BaseModelBackend``, das ``claude -p`` statt HTTP spricht.

    Anders als ``CodexCliModel`` wird ``api_key`` tatsaechlich benutzt: es ist
    der ``CLAUDE_CODE_OAUTH_TOKEN``, den der Aufrufer aus der
    Subprozess-Umgebung liest und hier durchreicht (siehe
    ``platform_runner.py``/``run_parallel_simulation.py``).
    """

    def __init__(
        self,
        model_type: str | ModelType = CLAUDE_CLI_DEFAULT_MODEL_ID,
        model_config_dict: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        token_counter: Optional[BaseTokenCounter] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        **_ignored: Any,
    ) -> None:
        super().__init__(
            model_type=model_type,
            model_config_dict=model_config_dict or {},
            api_key=api_key,
            url=url,
            token_counter=token_counter,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._model_slug = str(model_type)
        self._oauth_token = api_key or ""

    @property
    def token_counter(self) -> BaseTokenCounter:
        """cl100k-Tokenizer fuer CAMELs Kontextfenster-Verwaltung.

        ``GPT_4O_MINI`` dient nur der Tokenizer-Auswahl, nicht als Aussage
        darueber, welches Modell die CLI tatsaechlich faehrt.
        """
        if self._token_counter is None:
            self._token_counter = OpenAITokenCounter(ModelType.GPT_4O_MINI)
        return self._token_counter

    def _build_prompt(
        self,
        messages: List[Any],
        tools: Optional[List[Dict[str, Any]]],
        response_format: Optional[Type[BaseModel]],
    ) -> str:
        prompt = _flatten_messages([dict(message) for message in messages])
        if tools:
            prompt += build_tool_prompt(tools)
        if response_format is not None:
            try:
                schema = json.dumps(
                    response_format.model_json_schema(), ensure_ascii=False
                )
                prompt += (
                    "\n\n[ANTWORTFORMAT]\nAntworte ausschliesslich mit JSON, "
                    f"das diesem Schema entspricht:\n{schema}"
                )
            except Exception as exc:  # noqa: BLE001 — Schema ist Komfort, kein Muss
                logger.warning("response_format nicht serialisierbar: %s", exc)
        return prompt

    def _to_completion(self, text: str) -> ChatCompletion:
        """CLI-Rohtext -> ``ChatCompletion``.

        ``usage`` bleibt auf Null wie bei codex_cli_model — das reale
        Token-Usage liegt im ``--output-format json``-Result, wird hier aber
        (noch) nicht durchgereicht, weil CAMELs ``ChatCompletion``-Vertrag pro
        Aufruf und nicht pro Provider variiert. Kostenrechnung fuer ein Abo
        ist ohnehin kein Pay-per-Token-Fall.
        """
        calls = parse_tool_calls(text)
        tool_calls: Optional[List[ChatCompletionMessageToolCall]] = None
        content = text
        finish_reason = "stop"
        if calls:
            tool_calls = [
                ChatCompletionMessageToolCall(
                    id=f"call_claude_{index}",
                    type="function",
                    function=Function(
                        name=call["name"],
                        arguments=json.dumps(call["parameters"], ensure_ascii=False),
                    ),
                )
                for index, call in enumerate(calls)
            ]
            content = strip_tool_calls(text)
            finish_reason = "tool_calls"
        return ChatCompletion(
            id=f"claudecli-{uuid.uuid4().hex[:12]}",
            object="chat.completion",
            created=int(time.time()),
            model=self._model_slug,
            choices=[
                Choice(
                    index=0,
                    finish_reason=finish_reason,  # type: ignore[arg-type]
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=content or None,
                        tool_calls=tool_calls,
                    ),
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=0, completion_tokens=0, total_tokens=0
            ),
        )

    def _invoke(self, prompt: str) -> str:
        """Synchroner Pfad — nur fuer Nicht-Runden-Aufrufer, nicht im
        Rundenbetrieb genutzt (siehe ``_arun``)."""
        from app.llm.providers.claude_cli import _run_claude_cli

        model = self._model_slug or None
        try:
            return _run_claude_cli(prompt, model=model, oauth_token=self._oauth_token)
        except ClaudeCliUnavailableError as exc:
            raise RuntimeError(f"claude_cli: {exc}") from exc

    def _run(
        self,
        messages: List[Any],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        prompt = self._build_prompt(messages, tools, response_format)
        return self._to_completion(self._invoke(prompt))

    async def _ainvoke(self, prompt: str) -> str:
        """``claude -p`` als nativer async-Subprozess — abbrechbar.

        Isoliertes ``HOME`` UND ``cwd`` (siehe Modul-Docstring): ohne das
        haengt die CLI ~190K Tokens des interaktiven Host-Setups an jeden
        Runden-Turn — bei Dutzenden Agenten pro Runde kein Rundungsfehler.
        """
        cmd = build_claude_cli_command(model=self._model_slug or None)
        timeout = claude_cli_timeout_seconds()
        with tempfile.TemporaryDirectory(prefix=claude_cli_scratch_dir_prefix()) as scratch:
            env = _isolated_home(scratch, self._oauth_token)
            work_dir = os.path.join(scratch, "work")
            os.makedirs(work_dir, exist_ok=True)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir,
                    env=env,
                )
            except OSError as exc:
                raise ClaudeCliUnavailableError(
                    f"claude -p konnte nicht gestartet werden: {exc}"
                ) from exc
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode("utf-8")), timeout
                )
            except asyncio.TimeoutError as exc:
                await _terminate(proc)
                raise ClaudeCliUnavailableError(
                    f"claude -p Timeout nach {timeout:.0f}s"
                ) from exc
            except asyncio.CancelledError:
                await _terminate(proc)
                raise
        return interpret_claude_cli_result(
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def _arun(
        self,
        messages: List[Any],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        """Async-Pfad — der einzige, den OASIS im Rundenbetrieb nutzt."""
        prompt = self._build_prompt(messages, tools, response_format)
        try:
            text = await self._ainvoke(prompt)
        except ClaudeCliUnavailableError as exc:
            raise RuntimeError(f"claude_cli: {exc}") from exc
        return self._to_completion(text)

    @property
    def stream(self) -> bool:
        """Die CLI liefert immer die vollstaendige Antwort in einem Zug."""
        return False
