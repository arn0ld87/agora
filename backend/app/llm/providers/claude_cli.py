"""Claude-CLI-Bridge: Claude-Abo statt Pay-per-Token-API.

Spricht die lokal installierte ``claude``-CLI (Claude Code) per Subprozess an,
authentifiziert ueber einen mit ``claude setup-token`` erzeugten Langzeit-Token
(Env-Var ``CLAUDE_CODE_OAUTH_TOKEN``, offiziell dokumentiert fuer CI/Headless-
Nutzung) statt eines API-Keys. Anders als ``codex_cli`` (Issue #1405, ambiente
Login-Session unter einem gemounteten ``$CODEX_HOME``) traegt hier jeder
Aufruf seinen Token explizit als Env-Var mit — kein Verzeichnis-Mount, kein
Compose-Override noetig. Der Token liegt wie jeder andere API-Key im
bestehenden Fernet-Secret-Store (``secret_ref="claude_cli"``).

Bewusst KEIN eigener ``ProviderAdapter`` (``llm/providers/base.py``) — analog
zu ``codex_cli``: ``LLMClient._provider_attempt`` ruft ausschliesslich
``self.client.chat.completions.create(**kwargs)``. ``ClaudeCliClient``
imitiert deshalb nur genau diese Teiloberflaeche des OpenAI-SDK-Clients.

Isolation: jeder Aufruf laeuft mit einem LEEREN, temporaeren ``HOME`` UND
``cwd``. Zwei unabhaengige Gruende, beide am 20.09.2026 live gegen dieses
Binary verifiziert:

1. **Sicherheit** — dieselbe Begruendung wie bei ``codex_cli``: ``claude`` ist
   ein agentisches Coding-Tool und darf nicht mit Zugriff auf das Agora-Repo
   (= CWD des Backend-Prozesses) laufen. ``--tools ""`` nimmt zusaetzlich
   JEDES Werkzeug weg (staerker als codex' ``--sandbox read-only`` — hier
   gibt es gar keinen Werkzeugzugriff), ``--permission-prompts none``
   verhindert ein haengendes Terminal bei einer Restanfrage.
2. **Kosten** — ein Aufruf, der das reale ``$HOME`` des Hosts erbt, laedt
   CLAUDE.md, Skills und Plugins der interaktiven Session in den
   Prompt-Cache. Gemessene Differenz fuer denselben Ein-Wort-Prompt:
   189.466 vs. 2.935 ``cache_creation_input_tokens`` (~64x), $0,758 vs.
   $0,030. Ein isoliertes ``HOME`` ist damit nicht nur sauberer, sondern auch
   um Groessenordnungen billiger — bei einer Simulation mit Dutzenden
   Agenten-Turns kein Rundungsfehler.

``--model`` ohne explizite Angabe waehlt die CLI ihr eigenes Default-Modell —
verifiziert NICHT deterministisch (zwei Aufrufe direkt hintereinander lieferten
``claude-sonnet-5`` bzw. ``claude-opus-5[1m]``). ``claude_cli_fallback_models()``
nennt deshalb den Sentinel zuerst, aber auch konkrete, aus ``claude --help``
zitierte Alias-Namen (``sonnet``/``opus``/``fable``) fuer wer feste Routing-
Erwartungen braucht.

``_flatten_messages``/``build_tool_prompt``/``parse_tool_calls``/
``strip_tool_calls`` sind provider-agnostische Prompt-Shims (kein
Codex-spezifisches Verhalten) und werden aus ``codex_cli`` importiert statt
dupliziert, um die dort bereits getestete Logik nicht zweimal zu pflegen.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import LlmProviderError
from ...contracts.llm_request import NormalizedLlmError
from .codex_cli import (
    CLI_TRANSPORT_VALUE,
    TRANSPORT_ENV_KEY,
    _flatten_messages,
    build_tool_prompt,
    parse_tool_calls,
    strip_tool_calls,
)

logger = logging.getLogger(__name__)

CLAUDE_CLI_BINARY_ENV = "AGORA_CLAUDE_CLI_BIN"
CLAUDE_CLI_TIMEOUT_ENV = "AGORA_CLAUDE_CLI_TIMEOUT_SECONDS"

DEFAULT_CLAUDE_CLI_BINARY = "claude"
DEFAULT_CLAUDE_CLI_TIMEOUT_SECONDS = 180

# Wiederverwendet aus codex_cli: dieselbe generische "ist dieser Subprozess
# auf CLI-Transport" Signalisierung an den OASIS-Subprozess (Issue #1423),
# unabhaengig davon, welcher konkrete CLI-Provider gerade geroutet ist.
__all__ = [
    "CLI_TRANSPORT_VALUE",
    "TRANSPORT_ENV_KEY",
    "CLAUDE_CLI_DEFAULT_MODEL_ID",
    "ClaudeCliClient",
    "ClaudeCliUnavailableError",
    "build_claude_cli_command",
    "claude_cli_binary",
    "claude_cli_fallback_models",
    "claude_cli_timeout_seconds",
    "interpret_claude_cli_result",
    "is_claude_cli_available",
]


def claude_cli_binary() -> str:
    return os.environ.get(CLAUDE_CLI_BINARY_ENV, DEFAULT_CLAUDE_CLI_BINARY)


def claude_cli_timeout_seconds() -> float:
    raw = os.environ.get(CLAUDE_CLI_TIMEOUT_ENV)
    if not raw:
        return float(DEFAULT_CLAUDE_CLI_TIMEOUT_SECONDS)
    try:
        return float(raw)
    except ValueError:
        return float(DEFAULT_CLAUDE_CLI_TIMEOUT_SECONDS)


CLAUDE_CLI_DEFAULT_MODEL_ID = "claude-cli-default"
"""Sentinel statt eines geratenen Default-Modells.

``--model`` weglassen ist nicht dasselbe wie "das aktuelle Flaggschiff" — es
ist "was die CLI/das Abo gerade als Default hinterlegt hat", verifiziert
nicht-deterministisch je nach Umgebung. Der Sentinel macht diese Unschaerfe
explizit statt sie hinter einem erratenen Modellnamen zu verstecken.
"""


def claude_cli_fallback_models() -> tuple[str, ...]:
    """Sentinel zuerst, danach die in ``claude --help`` dokumentierten Alias-
    Namen (``--model``-Beispiele: "fable", "opus", "sonnet"). Keine geratenen
    vollen Modellnamen — die CLI kennt keinen Discovery-Befehl analog zu
    ``codex debug models``, und ein hier gepflegter Modellname waere sowohl
    veraltungs- als auch account-anfaellig.
    """
    return (CLAUDE_CLI_DEFAULT_MODEL_ID, "sonnet", "opus", "fable")


def is_claude_cli_available() -> bool:
    """True wenn das ``claude``-Binary im PATH auffindbar ist.

    Prueft NUR Installation, nicht Token-Gueltigkeit — ein fehlender/
    abgelaufener Token zeigt sich erst als Subprozess-Fehler beim ersten
    echten Aufruf (``is_error`` im JSON-Result, siehe
    ``interpret_claude_cli_result``).
    """
    return shutil.which(claude_cli_binary()) is not None


class ClaudeCliUnavailableError(RuntimeError):
    """Claude-CLI fehlt, Token ungueltig/abgelaufen, oder der Aufruf schlug fehl."""


def build_claude_cli_command(*, model: Optional[str]) -> list[str]:
    """Argumentliste fuer einen ``claude -p``-Aufruf.

    Der Prompt geht ueber stdin (kein Positionsargument) — verifiziert, dass
    die CLI das unterstuetzt. Dasselbe ``MAX_ARG_STRLEN``-Problem wie bei
    codex_cli gilt hier ebenso: ein Runden-Prompt mit Persona, Historie und
    Werkzeugschemata reisst leicht die 128-KiB-Grenze eines argv-Elements.

    ``--tools ""`` statt ``--sandbox read-only``: es gibt fuer diesen
    Provider keinen Anwendungsfall, in dem Claude Dateien lesen oder
    Befehle ausfuehren soll — Agora nutzt die CLI ausschliesslich als
    Text-Completion-Backend. ``--permission-prompts none`` verhindert, dass
    eine uebrig gebliebene Restanfrage (z. B. WebFetch) den Subprozess bis
    zum Timeout haengen laesst, statt sofort automatisch abgelehnt zu werden.

    Raises:
        ClaudeCliUnavailableError: wenn das Binary nicht im PATH liegt.
    """
    if not is_claude_cli_available():
        raise ClaudeCliUnavailableError(
            f"claude-CLI nicht gefunden (PATH, Binary={claude_cli_binary()!r}). "
            "Installation pruefen."
        )
    cmd = [
        claude_cli_binary(),
        "-p",
        "--output-format",
        "json",
        "--tools",
        "",
        "--permission-prompts",
        "none",
    ]
    # Sentinel weglassen statt als (nicht existentes) --model an die CLI zu
    # reichen — dann entscheidet das Abo/die lokale Konfiguration selbst.
    if model and model != CLAUDE_CLI_DEFAULT_MODEL_ID:
        cmd += ["--model", model]
    return cmd


def claude_cli_scratch_dir_prefix() -> str:
    """Prefix des isolierten Arbeitsverzeichnisses — von beiden Pfaden genutzt."""
    return "agora-claude-cli-"


def _isolated_home(scratch_dir: str, oauth_token: str) -> Dict[str, str]:
    """Baut das Env-Dict fuer einen isolierten Subprozess-Aufruf.

    ``HOME`` zeigt auf ein leeres Unterverzeichnis von ``scratch_dir`` — ohne
    das wuerde die CLI das reale ``$HOME`` des Backend-Prozesses erben und
    dessen CLAUDE.md/Skills/Plugins in den Prompt-Cache laden (siehe
    Modul-Docstring, ~64x Kostenfaktor). ``CLAUDE_CODE_OAUTH_TOKEN`` ist die
    von Anthropic dokumentierte Env-Var fuer den ``claude setup-token``-
    Langzeit-Token (CI/Headless-Auth, unabhaengig von einer interaktiven
    OAuth-Keychain-Session).
    """
    isolated_home = os.path.join(scratch_dir, "home")
    os.makedirs(isolated_home, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = isolated_home
    env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    return env


def _run_claude_cli(prompt: str, *, model: Optional[str], oauth_token: str) -> str:
    cmd = build_claude_cli_command(model=model)
    timeout = claude_cli_timeout_seconds()
    with tempfile.TemporaryDirectory(prefix=claude_cli_scratch_dir_prefix()) as scratch_dir:
        env = _isolated_home(scratch_dir, oauth_token)
        # Isoliertes CWD wie bei codex_cli: das Backend-Prozess-CWD ist das
        # Agora-Repo selbst — ein Sandbox-Fehlgriff darf dort nichts anfassen.
        work_dir = os.path.join(scratch_dir, "work")
        os.makedirs(work_dir, exist_ok=True)
        try:
            result = subprocess.run(  # noqa: S603 — Binary aus Config, Argumente sind kein Shell-String
                cmd,
                input=prompt,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=work_dir,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCliUnavailableError(
                f"claude -p Timeout nach {timeout:.0f}s"
            ) from exc
        except OSError as exc:
            raise ClaudeCliUnavailableError(f"claude -p konnte nicht gestartet werden: {exc}") from exc
    return interpret_claude_cli_result(result.returncode, result.stdout, result.stderr)


def interpret_claude_cli_result(
    returncode: int, stdout: Optional[str], stderr: Optional[str]
) -> str:
    """Exit-Code und Streams eines ``claude -p --output-format json``-Laufs
    auswerten.

    Anders als codex_cli (Rohtext auf stdout) liefert ``--output-format
    json`` bei Erfolg UND bei den meisten Fehlern (z. B. abgelaufener Token:
    ``is_error=true``, ``api_error_status=401``, ``result="Not logged in ·
    Please run /login"``) ein einziges JSON-Objekt auf stdout — verifiziert
    live am 20.09.2026. Deshalb zuerst versuchen, stdout als JSON zu lesen,
    unabhaengig vom Exit-Code; nur bei kaputtem/leerem JSON (Absturz vor der
    ersten Ausgabe) auf den Exit-Code + stderr-Tail zurueckfallen.
    """
    raw = (stdout or "").strip()
    if raw:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            text = payload.get("result")
            if payload.get("is_error"):
                message = text or f"claude -p meldete einen Fehler (exit={returncode})"
                raise ClaudeCliUnavailableError(str(message))
            if isinstance(text, str) and text:
                return text
            raise ClaudeCliUnavailableError(
                "claude -p lieferte JSON ohne verwertbares 'result'-Feld"
            )
    if returncode != 0:
        stderr_tail = (stderr or "").strip()[-500:]
        raise ClaudeCliUnavailableError(
            f"claude -p fehlgeschlagen (exit={returncode}): {stderr_tail}"
        )
    raise ClaudeCliUnavailableError("claude -p lieferte leere/unlesbare Ausgabe")


# ---------------------------------------------------------------------------
# Minimaler Duck-Type-Shim der OpenAI-SDK-Oberflaeche
# (``client.chat.completions.create(**kwargs) -> .choices[0].message.content``)
# — identisch im Aufbau zu codex_cli._CodexCliCompletions, eigene Klassen
# statt geteilter Instanzen, weil beide Provider parallel mit
# unterschiedlichen Prompts/Tokens laufen koennen.
# ---------------------------------------------------------------------------


@dataclass
class _ShimFunction:
    name: str
    arguments: str


@dataclass
class _ShimToolCall:
    id: str
    function: _ShimFunction
    type: str = "function"


@dataclass
class _ShimMessage:
    content: str
    role: str = "assistant"
    tool_calls: Optional[List[_ShimToolCall]] = None


@dataclass
class _ShimChoice:
    message: _ShimMessage
    finish_reason: str = "stop"
    index: int = 0


@dataclass
class _ShimUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _ShimChatCompletion:
    choices: List[_ShimChoice] = field(default_factory=list)
    usage: _ShimUsage = field(default_factory=_ShimUsage)


class _ClaudeCliCompletions:
    def __init__(self, oauth_token_getter: "Any") -> None:
        self._oauth_token_getter = oauth_token_getter

    def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **_ignored: Any,
    ) -> _ShimChatCompletion:
        """Wire-kompatibel zu ``openai.Client.chat.completions.create``.

        ``**_ignored`` faengt ``temperature``/``max_tokens``/``response_format``/
        ``extra_body``/``stream`` ab — die Claude-CLI kennt keinen dieser
        Parameter im ``-p``-Modus. ``stream=True`` wird NICHT unterstuetzt;
        der Aufrufer bekommt immer die vollstaendige Antwort in einem Zug.

        ``tools`` wird wie bei codex_cli als Prompt-Abschnitt angehaengt und
        die Antwort danach wieder in ``tool_calls`` uebersetzt — mit
        ``--tools ""`` hat die CLI selbst keinerlei Werkzeugzugriff, das
        Protokoll bleibt trotzdem identisch zu codex_cli, damit OASIS-Agenten
        provider-unabhaengig funktionieren.
        """
        prompt = _flatten_messages(messages or [])
        if tools:
            prompt += build_tool_prompt(tools)
        oauth_token = self._oauth_token_getter()
        if not oauth_token:
            raise LlmProviderError(
                NormalizedLlmError(
                    provider="claude_cli",
                    code="invalid_credentials",
                    message=(
                        "Kein CLAUDE_CODE_OAUTH_TOKEN konfiguriert — "
                        "`claude setup-token` ausfuehren und den Token in "
                        "Agora unter der claude_cli-Connection hinterlegen."
                    ),
                    retryable=False,
                )
            )
        try:
            text = _run_claude_cli(prompt, model=model, oauth_token=oauth_token)
        except ClaudeCliUnavailableError as exc:
            raise LlmProviderError(
                NormalizedLlmError(
                    provider="claude_cli",
                    code="provider_unavailable",
                    message=str(exc),
                    retryable=False,
                )
            ) from exc
        return _ShimChatCompletion(choices=[_ShimChoice(message=build_shim_message(text))])


def build_shim_message(text: str) -> _ShimMessage:
    """CLI-Rohtext -> Assistant-Nachricht, ggf. mit ``tool_calls``.

    Identisch zu ``codex_cli.build_shim_message`` — dasselbe
    ``<tool_call>``-Protokoll, dieselbe Uebersetzung. Call-IDs sind
    synthetisch (``call_claude_<n>``), weil die CLI im ``--tools ""``-Modus
    ohnehin keine eigenen vergibt.
    """
    calls = parse_tool_calls(text)
    if not calls:
        return _ShimMessage(content=text)
    tool_calls = [
        _ShimToolCall(
            id=f"call_claude_{index}",
            function=_ShimFunction(
                name=call["name"],
                arguments=json.dumps(call["parameters"], ensure_ascii=False),
            ),
        )
        for index, call in enumerate(calls)
    ]
    return _ShimMessage(content=strip_tool_calls(text), tool_calls=tool_calls)


class _ClaudeCliChatNamespace:
    def __init__(self, oauth_token_getter: "Any") -> None:
        self.completions = _ClaudeCliCompletions(oauth_token_getter)


class ClaudeCliClient:
    """Duck-Type-Ersatz fuer ``openai.OpenAI`` — nur die genutzte Teiloberflaeche.

    ``oauth_token`` wird beim Bau uebergeben statt global gelesen: der Token
    kommt aus Agoras Secret-Store (pro Connection), nicht aus einer
    Prozessumgebungsvariable, die zufaellig schon gesetzt sein koennte.
    """

    def __init__(self, oauth_token: Optional[str] = None) -> None:
        self._oauth_token = oauth_token
        self.chat = _ClaudeCliChatNamespace(lambda: self._oauth_token)
