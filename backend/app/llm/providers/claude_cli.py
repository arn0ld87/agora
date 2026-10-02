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
nennt deshalb den Sentinel zuerst, danach feste, volle Modell-IDs statt
Aliasen (``sonnet``/``opus`` loest die CLI selbst und versionsabhaengig auf —
welche Version lief, war so nicht nachvollziehbar). Volle IDs via ``--model``
live verifiziert am 02.10.2026 (CLI 2.1.287).

Welches Modell tatsaechlich lief, steht im JSON-Result unter ``modelUsage``
(Schluessel = aufgeloeste Modell-ID). ``extract_claude_cli_model`` liest es
aus; der Shim gibt es als ``model`` zurueck und loggt Abweichungen vom
angefragten Modell — insbesondere fuer den Sentinel relevant.

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
    "CLAUDE_CLI_MODEL_DISPLAY_NAMES",
    "build_claude_cli_command",
    "claude_cli_binary",
    "claude_cli_fallback_models",
    "extract_claude_cli_model",
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


CLAUDE_CLI_MODEL_DISPLAY_NAMES: Dict[str, str] = {
    CLAUDE_CLI_DEFAULT_MODEL_ID: "Abo-Default (nicht deterministisch)",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-fable-5-1": "Claude Fable 5.1",
}
"""Anzeigenamen der Modellauswahl, in Auswahl-Reihenfolge (Sentinel zuerst)."""


def claude_cli_fallback_models() -> tuple[str, ...]:
    """Sentinel zuerst, danach feste, volle Modell-IDs der aktuellen Claude-
    Generation. Die CLI kennt keinen Discovery-Befehl analog zu ``codex debug
    models`` — die Liste wird hier gepflegt und muss bei neuen Modellen
    nachgezogen werden. Bewusst volle IDs statt Aliasen: ein Alias wie
    ``sonnet`` wandert mit der CLI-Version mit, ein Lauf waere dann nicht mehr
    reproduzierbar.
    """
    return tuple(CLAUDE_CLI_MODEL_DISPLAY_NAMES)


def extract_claude_cli_model(stdout: Optional[str]) -> Optional[str]:
    """Tatsaechlich genutzte Modell-ID aus einem ``--output-format json``-Result.

    ``modelUsage`` ist ein Dict ``{modell_id: {outputTokens, ...}}``. Mehrere
    Eintraege sind moeglich, wenn die CLI intern ein Hilfsmodell nutzt — dann
    zaehlt das Modell mit den meisten ``outputTokens`` (das hat die Antwort
    geschrieben). ``None`` bei fehlendem/kaputtem JSON — rein informativ, nie
    ein Fehlergrund.
    """
    try:
        payload = json.loads((stdout or "").strip() or "null")
    except ValueError:
        return None
    usage = payload.get("modelUsage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict) or not usage:
        return None

    def _output_tokens(item: tuple[str, Any]) -> int:
        stats = item[1]
        value = stats.get("outputTokens") if isinstance(stats, dict) else None
        return value if isinstance(value, int) else 0

    return max(usage.items(), key=_output_tokens)[0]


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
    return _run_claude_cli_with_model(prompt, model=model, oauth_token=oauth_token)[0]


def _run_claude_cli_with_model(
    prompt: str, *, model: Optional[str], oauth_token: str
) -> tuple[str, Optional[str]]:
    """Wie ``_run_claude_cli``, liefert zusaetzlich die aufgeloeste Modell-ID."""
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
    text = interpret_claude_cli_result(result.returncode, result.stdout, result.stderr)
    resolved = extract_claude_cli_model(result.stdout)
    log_resolved_claude_cli_model(requested=model, resolved=resolved)
    return text, resolved


def log_resolved_claude_cli_model(*, requested: Optional[str], resolved: Optional[str]) -> None:
    """Macht sichtbar, welches Modell die CLI tatsaechlich gefahren hat.

    INFO nur bei Abweichung (Sentinel oder Alias aufgeloest), sonst DEBUG —
    sonst flutet eine Simulation mit Dutzenden Turns das Log.
    """
    if resolved and resolved != requested:
        logger.info("claude_cli: angefragt=%s, gelaufen=%s", requested or "-", resolved)
    else:
        logger.debug("claude_cli: Modell=%s", resolved or requested or "-")


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
    model: Optional[str] = None


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
            text, resolved_model = _run_claude_cli_with_model(
                prompt, model=model, oauth_token=oauth_token
            )
        except ClaudeCliUnavailableError as exc:
            raise LlmProviderError(
                NormalizedLlmError(
                    provider="claude_cli",
                    code="provider_unavailable",
                    message=str(exc),
                    retryable=False,
                )
            ) from exc
        return _ShimChatCompletion(
            choices=[_ShimChoice(message=build_shim_message(text))],
            model=resolved_model or model,
        )


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
