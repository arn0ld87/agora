"""CAMEL-Model-Backend fuer den Codex-CLI-Transport (Issue #1423).

Der OASIS-Subprozess baut seine Agenten ueber ``camel.models`` und sprach
bisher ausschliesslich HTTP: ``detect_oasis_platform`` kannte genau drei
Plattformen (GEMINI, OLLAMA, OPENAI), alle mit ``url``+``api_key``. Ein
Provider mit ``transport="cli"`` — ``codex_cli``, seit #1405 — hat weder das
eine noch das andere. Folge vor diesem Modul: ``build_route_subprocess_env``
setzte kein ``LLM_BASE_URL``, der Subprozess erbte ueber ``SAFE_ENV_KEYS``
die ``.env``-URL des Backends und schickte das geroutete Codex-Modell an
einen fremden Endpunkt — beobachtet als ``400 invalid params, unknown model
'gpt-5.6-luna' (2013)`` gegen ``api.minimax.io``.

Dieses Backend schliesst die Luecke, indem es dieselbe ``codex exec``-Bruecke
nutzt, die das Backend in-process schon fuehrt
(``app.llm.providers.codex_cli``). Der Subprozess hat ``app`` im
``PYTHONPATH`` — ``_sim_common`` importiert von dort bereits
``detect_provider`` —, deshalb wird die CLI-Logik importiert statt kopiert.

Zwei Eigenheiten der CLI bestimmen den Aufbau:

1. **Kein natives Function-Calling.** OASIS-Agenten waehlen ihre Aktionen
   ausschliesslich ueber Werkzeugaufrufe; ohne Uebersetzung waeren sie
   handlungsunfaehig. ``build_tool_prompt`` schreibt die Schemas in den
   Prompt, ``parse_tool_calls`` liest die Antwort im ``<tool_call>``-Format
   zurueck — dasselbe Protokoll wie ``scripts/agent_tools.py``.

2. **Ein Subprozess pro Anfrage, ~8-40 s.** ``_arun`` darf deshalb NICHT
   synchron blockieren: OASIS treibt seine Agenten mit ``asyncio`` parallel,
   und ein blockierender Aufruf serialisiert die gesamte Simulation. Der
   Aufruf wandert per ``asyncio.to_thread`` in einen Worker-Thread.
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

from app.llm.providers.codex_cli import (
    CLI_TRANSPORT_VALUE,
    CODEX_CLI_DEFAULT_MODEL_ID,
    TRANSPORT_ENV_KEY,
    CodexCliUnavailableError,
    _flatten_messages,
    _run_codex_cli,
    build_codex_cli_command,
    build_tool_prompt,
    codex_cli_scratch_dir_prefix,
    codex_cli_timeout_seconds,
    interpret_codex_cli_result,
    parse_tool_calls,
    strip_tool_calls,
)

logger = logging.getLogger(__name__)


async def _terminate(proc: "asyncio.subprocess.Process") -> None:
    """Kindprozess beenden und einsammeln, ohne den Abbruchpfad zu stoeren.

    ``kill`` statt ``terminate``: ``codex exec`` startet selbst Kindprozesse,
    und ein sauberes Herunterfahren ist beim Abbruch weder noetig noch
    abwartbar. Fehler werden geschluckt — der Prozess kann zwischen Timeout
    und Kill von selbst geendet sein, und im Abbruchpfad darf nichts
    Zusaetzliches fliegen.
    """
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.kill()
    with contextlib.suppress(Exception):  # noqa: BLE001 — Aufraeumpfad
        await proc.wait()


def cli_transport_active() -> bool:
    """True, wenn dieser Subprozess auf CLI-Transport laufen soll.

    Das Signal setzt ``build_route_subprocess_env`` anhand von
    ``ProviderConnectionDefinition.transport`` — die Entscheidung faellt also
    im Backend anhand der Registry, nicht hier anhand einer Heuristik.
    """
    return os.environ.get(TRANSPORT_ENV_KEY, "").strip().lower() == CLI_TRANSPORT_VALUE


class CodexCliModel(BaseModelBackend):
    """``BaseModelBackend``, das ``codex exec`` statt HTTP spricht.

    Implementiert die drei abstrakten Member von CAMEL 0.2.78 — ``_run``,
    ``_arun`` und ``token_counter``. ``api_key``/``url`` werden von der
    Basisklasse entgegengenommen, aber nie benutzt: die CLI authentifiziert
    ueber die lokale ``codex login``-Session (``auth_mode="session"``).
    """

    def __init__(
        self,
        model_type: str | ModelType = CODEX_CLI_DEFAULT_MODEL_ID,
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

    @property
    def token_counter(self) -> BaseTokenCounter:
        """Token-Zaehler fuer CAMELs Kontextfenster-Verwaltung.

        Die CLI meldet keine Usage-Zahlen, CAMEL braucht aber einen Zaehler,
        um Nachrichten zu kuerzen. ``GPT_4O_MINI`` dient hier nur als
        cl100k-Tokenizer-Auswahl — es sagt nichts darueber aus, welches Modell
        die CLI tatsaechlich faehrt.
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
            # CAMEL nutzt ``response_format`` fuer strukturierte Ausgaben. Die
            # CLI kennt kein ``json_schema``-Feld, also wandert das Schema als
            # Anweisung in den Prompt — dieselbe Degradierung, die
            # ``LLMClient.chat_json`` fuer diesen Provider ohnehin faehrt.
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
        """CLI-Rohtext -> ``ChatCompletion``, wie CAMEL sie von HTTP erwartet.

        ``usage`` bleibt auf Null: ``codex exec`` meldet keine Token-Zahlen.
        Nachgelagerte Kostenrechnung (``sim_runtime/budget_guard.py``) sieht
        damit 0 statt einer erfundenen Schaetzung — beim ChatGPT-Abo faellt
        ohnehin keine Pay-per-Token-Gebuehr an.
        """
        calls = parse_tool_calls(text)
        tool_calls: Optional[List[ChatCompletionMessageToolCall]] = None
        content = text
        finish_reason = "stop"
        if calls:
            tool_calls = [
                ChatCompletionMessageToolCall(
                    id=f"call_codex_{index}",
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
            id=f"codexcli-{uuid.uuid4().hex[:12]}",
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
        model = self._model_slug or None
        try:
            return _run_codex_cli(prompt, model=model)
        except CodexCliUnavailableError as exc:
            # Als RuntimeError weiterreichen: OASIS faengt Modellfehler pro
            # Agent ab. Ein durchgereichter CLI-Fehler wuerde sonst den
            # gesamten Runden-Fan-out kippen, obwohl ein einzelner Agent
            # scheiterte.
            raise RuntimeError(f"codex_cli: {exc}") from exc

    def _run(
        self,
        messages: List[Any],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        prompt = self._build_prompt(messages, tools, response_format)
        return self._to_completion(self._invoke(prompt))

    async def _ainvoke(self, prompt: str) -> str:
        """``codex exec`` als nativer async-Subprozess — abbrechbar.

        Bewusst ``create_subprocess_exec`` statt ``asyncio.to_thread``: ein
        Thread laesst sich nicht abbrechen. Wird ein Agent-Task gecancelt
        (Simulation gestoppt, Runden-Timeout), liefe der CLI-Prozess sonst bis
        zum Timeout von 180 s weiter und haette Worker und Kindprozess
        gebunden — bei 20 Agenten pro Runde blockiert das ein sauberes
        Herunterfahren spuerbar. Hier wird der Kindprozess bei Abbruch und bei
        Zeitueberschreitung terminiert.

        Nebeneffekt: der Event-Loop bleibt ohnehin frei, die parallele
        Ausfuehrung der Runde bleibt also erhalten.
        """
        cmd = build_codex_cli_command(prompt, model=self._model_slug or None)
        timeout = codex_cli_timeout_seconds()
        with tempfile.TemporaryDirectory(prefix=codex_cli_scratch_dir_prefix()) as scratch:
            # Isoliertes CWD wie im synchronen Pfad: ``codex exec`` liest
            # Repo-Kontext aus dem Arbeitsverzeichnis, und das des Runners ist
            # das Agora-Repo.
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=scratch,
                )
            except OSError as exc:
                raise CodexCliUnavailableError(
                    f"codex exec konnte nicht gestartet werden: {exc}"
                ) from exc
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
            except asyncio.TimeoutError as exc:
                await _terminate(proc)
                raise CodexCliUnavailableError(
                    f"codex exec Timeout nach {timeout:.0f}s"
                ) from exc
            except asyncio.CancelledError:
                # Abbruch weiterreichen, aber nicht ohne den Kindprozess zu
                # beenden — sonst ueberlebt er den Task, der ihn gestartet hat.
                await _terminate(proc)
                raise
        return interpret_codex_cli_result(
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
        """Async-Pfad — der einzige, den OASIS im Rundenbetrieb nutzt.

        Der nicht-blockierende Aufruf ist hier tragend, nicht kosmetisch:
        OASIS treibt alle Agenten einer Runde nebenlaeufig. Liefe
        ``codex exec`` direkt im Event-Loop, wuerde jede Anfrage alle anderen
        Agenten blockieren und die Simulation von paralleler auf serielle
        Ausfuehrung fallen — bei ~8-40 s pro Aufruf der Unterschied zwischen
        Minuten und Stunden.
        """
        prompt = self._build_prompt(messages, tools, response_format)
        try:
            text = await self._ainvoke(prompt)
        except CodexCliUnavailableError as exc:
            raise RuntimeError(f"codex_cli: {exc}") from exc
        return self._to_completion(text)

    @property
    def stream(self) -> bool:
        """Die CLI liefert immer die vollstaendige Antwort in einem Zug."""
        return False
