"""Codex-CLI-Bridge (Issue #1405): ChatGPT-Abo statt Pay-per-Token-API.

Spricht den lokal installierten, per ``codex login`` bereits authentifizierten
``codex``-Subprozess an, statt einen ``OPENAI_API_KEY`` zu verlangen. Bewusst
KEIN eigener ``ProviderAdapter`` (``llm/providers/base.py``) — dieser
Adapter-Hierarchie folgt der aktuelle ``LLMClient.chat``/``chat_json``-Pfad
nicht (verifiziert: ``get_adapter()`` hat ausserhalb der eigenen Definition
keine Aufrufer). Der tatsaechliche Einstiegspunkt ist
``LLMClient._provider_attempt``, der ausschliesslich
``self.client.chat.completions.create(**kwargs)`` ruft. ``CodexCliClient``
imitiert deshalb nur genau diese Teiloberflaeche des OpenAI-SDK-Clients.

Sicherheit: ``codex exec`` ist ein agentisches Coding-Tool und darf NICHT im
CWD des Agora-Backend-Prozesses (= dieses Repo!) mit Schreibrechten laufen.
Jeder Aufruf bekommt ein isoliertes, leeres ``cwd`` und ``--sandbox
read-only``.

Kein Streaming, kein natives ``response_format`` — ``chat_json`` faellt fuer
diesen Provider auf die bestehende Legacy-JSON-Extraktion/-Repair-Pipeline
zurueck (wie bei jedem anderen Provider ohne strict-Schema-Support).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import LlmProviderError
from ...contracts.llm_request import NormalizedLlmError

logger = logging.getLogger(__name__)

CODEX_CLI_BINARY_ENV = "AGORA_CODEX_CLI_BIN"
CODEX_CLI_TIMEOUT_ENV = "AGORA_CODEX_CLI_TIMEOUT_SECONDS"

TRANSPORT_ENV_KEY = "AGORA_LLM_TRANSPORT"
"""Explizites Transport-Signal an den OASIS-Subprozess (Issue #1423).

Die Provider-Erkennung des Subprozesses laeuft ueber ``base_url`` und
Modellname (``registry._detect_oasis``). Fuer einen CLI-Provider gibt es keine
URL, aus der sich etwas ableiten liesse, und der Modellname (``gpt-5.6-luna``)
sieht aus wie ein gewoehnliches OpenAI-Modell. Statt die URL-Heuristik zu
verbiegen — AGENTS.md verbietet Detection-Heuristiken neben ``registry.py`` —
traegt die Env den Transport ausdruecklich.

Gesetzt von ``llm_routing_seed.build_route_subprocess_env``, ausgewertet von
``scripts/sim_runtime/codex_cli_model.cli_transport_active``. ``process_manager``
entfernt bei gesetztem Signal das geerbte ``LLM_BASE_URL``.
"""

CLI_TRANSPORT_VALUE = "cli"
DEFAULT_CODEX_CLI_BINARY = "codex"
DEFAULT_CODEX_CLI_TIMEOUT_SECONDS = 180
DEFAULT_CODEX_CLI_CATALOG_TIMEOUT_SECONDS = 30


def codex_cli_binary() -> str:
    return os.environ.get(CODEX_CLI_BINARY_ENV, DEFAULT_CODEX_CLI_BINARY)


def codex_cli_timeout_seconds() -> float:
    raw = os.environ.get(CODEX_CLI_TIMEOUT_ENV)
    if not raw:
        return float(DEFAULT_CODEX_CLI_TIMEOUT_SECONDS)
    try:
        return float(raw)
    except ValueError:
        return float(DEFAULT_CODEX_CLI_TIMEOUT_SECONDS)


CODEX_CLI_DEFAULT_MODEL_ID = "codex-cli-default"
"""Sentinel-Modell-ID statt eines geratenen echten Modellnamens.

Issue #1405 Follow-up (Codex-Review-Finding): ``_verify_selected_model``
(``app/services/llm_routing_seed.py``) akzeptiert nur Modelle, die der
Provider-Probe zurueckgibt — ohne einen Eintrag hier kann codex_cli zwar als
Connection verbunden, aber nie als Modell ausgewaehlt werden. Ein erfundener
"echter" Codex-Modellname waere veraltungsanfaellig und koennte an der
tatsaechlichen CLI vorbeizeigen. Der Sentinel bedeutet stattdessen explizit
"nutze das von der lokalen `codex`-CLI/-Konfiguration selbst aufgeloeste
Default-Modell" — ``_run_codex_cli`` laesst dafuer ``--model`` bewusst weg.
"""


def codex_cli_fallback_models() -> tuple[str, ...]:
    return (CODEX_CLI_DEFAULT_MODEL_ID,)


def discover_codex_cli_models() -> tuple[str, ...]:
    """Auswaehlbare Modell-Slugs aus ``codex debug models``.

    Der Katalog ist account- und planabhaengig: Das Binary kennt intern mehr
    Slugs, als ein konkretes Abo freischaltet (verifiziert — ``gpt-5.6`` und
    ``gpt-5.6-pro`` stehen im Binary, fehlen aber im Katalog eines
    Plus-Accounts). Eine im Repo gepflegte Liste waere damit nicht nur
    veraltungsanfaellig, sondern fuer jeden zweiten Nutzer schlicht falsch —
    deshalb wird der Katalog zur Laufzeit abgefragt statt fest verdrahtet.

    ``visibility == "list"`` ist der Filter, den die CLI selbst fuer ihr
    ``/model``-Menue verwendet; ``hide`` markiert interne Eintraege
    (``gpt-reserve``, ``codex-auto-review``), die keine Nutzerauswahl sind.

    Gibt bei jedem Fehlschlag ein leeres Tupel zurueck — der Aufrufer faellt
    dann auf den Sentinel zurueck. Discovery ist eine Komfortfunktion; sie
    darf eine funktionierende Verbindung nie kaputtmachen.
    """
    if not is_codex_cli_available():
        return ()
    cmd = [codex_cli_binary(), "debug", "models"]
    with tempfile.TemporaryDirectory(prefix="agora-codex-catalog-") as scratch_dir:
        try:
            result = subprocess.run(  # noqa: S603 — Binary aus Config, Argumente sind kein Shell-String
                cmd,
                capture_output=True,
                text=True,
                timeout=DEFAULT_CODEX_CLI_CATALOG_TIMEOUT_SECONDS,
                cwd=scratch_dir,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("codex debug models nicht ausfuehrbar: %s", exc)
            return ()
    if result.returncode != 0:
        logger.warning(
            "codex debug models fehlgeschlagen (exit=%s): %s",
            result.returncode,
            (result.stderr or "").strip()[-200:],
        )
        return ()
    payload: object
    try:
        payload = json.loads(result.stdout or "")
    except ValueError as exc:
        logger.warning("codex debug models lieferte kein gueltiges JSON: %s", exc)
        return ()
    if not isinstance(payload, dict):
        logger.warning("codex debug models: unerwartete Katalogform")
        return ()
    entries: object = payload.get("models")
    if not isinstance(entries, list):
        logger.warning("codex debug models: unerwartete Katalogform")
        return ()
    slugs: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("visibility") != "list":
            continue
        slug: object = entry.get("slug")
        if isinstance(slug, str) and slug:
            slugs.append(slug)
    return tuple(dict.fromkeys(slugs))


def is_codex_cli_available() -> bool:
    """True wenn das ``codex``-Binary im PATH auffindbar ist.

    Prueft NUR Installation, nicht Login-Status — ein fehlender Login zeigt
    sich erst als Subprozess-Fehler beim ersten echten Aufruf.
    """
    return shutil.which(codex_cli_binary()) is not None


class CodexCliUnavailableError(RuntimeError):
    """Codex-CLI fehlt, ist nicht eingeloggt, oder der Aufruf ist fehlgeschlagen."""


def _flatten_messages(messages: List[Dict[str, Any]]) -> str:
    """OpenAI-Chat-Messages -> ein Prompt-String fuer ``codex exec``.

    Die CLI kennt keine Chat-Turn-Struktur — nur ein Freitext-Prompt. Rollen
    bleiben als Marker erhalten, damit System-/Few-Shot-Anteile im Prompt
    erkennbar bleiben statt stillschweigend zu verschmelzen.

    ``tool``-Rollen tragen zusaetzlich die ``tool_call_id`` im Marker: eine
    ReACT-Schleife schickt Werkzeugergebnisse als eigene Nachrichten zurueck,
    und ohne die Zuordnung waere im flachen Prompt nicht mehr erkennbar,
    welches Ergebnis zu welchem Aufruf gehoert (Issue #1423).
    """
    parts: List[str] = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        call_id = message.get("tool_call_id")
        marker = f"[{role} tool_call_id={call_id}]" if call_id else f"[{role}]"
        # Ein Assistant-Turn, der Werkzeuge aufgerufen hat, traegt diesen Teil
        # seines Inhalts in ``tool_calls`` statt in ``content``. Ohne die
        # Rekonstruktion sieht das Modell im naechsten Durchgang nur den
        # ``tool``-Turn mit einer synthetischen ID, aber weder Werkzeugnamen
        # noch Argumente — und ruft dasselbe Werkzeug erneut auf.
        #
        # Angehaengt statt nur bei leerem ``content``: eine CLI-Antwort darf
        # Prosa UND einen Aufruf enthalten, und ``build_shim_message`` behaelt
        # die Prosa als ``content``. Die frueher gewaehlte Bedingung
        # ``if not content`` hat den Aufruf in genau diesem — dem haeufigen —
        # Fall verschluckt.
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            rendered = _render_prior_tool_calls(tool_calls)
            content = f"{content}\n{rendered}" if content else rendered
        parts.append(f"{marker}\n{content}")
    return "\n\n".join(parts)


def _render_prior_tool_calls(tool_calls: List[Any]) -> str:
    """Frueher abgesetzte Tool-Calls zurueck ins ``<tool_call>``-Textformat."""
    rendered: List[str] = []
    for call in tool_calls:
        function = _call_attr(call, "function") or {}
        name = _call_attr(function, "name") or ""
        raw_args = _call_attr(function, "arguments") or "{}"
        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except ValueError:
            arguments = {}
        rendered.append(
            "<tool_call>\n"
            + json.dumps({"name": name, "parameters": arguments}, ensure_ascii=False)
            + "\n</tool_call>"
        )
    return "\n".join(rendered)


def _call_attr(obj: Any, key: str) -> Any:
    """Liest ``key`` aus dict ODER Objekt — Tool-Calls kommen in beiden Formen."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
"""Dasselbe Muster wie ``scripts/agent_tools.py::parse_tool_calls``.

Bewusst identisch statt eines zweiten Protokolls: die OASIS-Agenten sind
bereits darauf trainiert, in diesem Format zu antworten, und ein abweichendes
Format haette bedeutet, denselben Parser zweimal zu pflegen (Issue #1423).
"""


def build_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    """Beschreibt OpenAI-Function-Schemas als Prompt-Abschnitt.

    ``codex exec`` kennt kein natives Function-Calling — der Parameter ``tools``
    des OpenAI-SDK hat an der CLI kein Gegenstueck. Statt Werkzeuge stillschweigend
    fallen zu lassen (Verhalten vor Issue #1423, das OASIS-Agenten handlungsunfaehig
    machte) werden die Schemas in den Prompt geschrieben und die Antwort danach
    wieder in ``tool_calls`` uebersetzt.

    Liefert einen leeren String, wenn keine brauchbaren Schemas anliegen — der
    Aufrufer haengt dann nichts an den Prompt.
    """
    lines: List[str] = []
    for tool in tools or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not name:
            continue
        description = function.get("description") or ""
        parameters = function.get("parameters") or {}
        lines.append(
            f"- {name}: {description}\n"
            f"  parameters: {json.dumps(parameters, ensure_ascii=False)}"
        )
    if not lines:
        return ""
    return (
        "\n\n[VERFUEGBARE WERKZEUGE]\n"
        + "\n".join(lines)
        + "\n\nWillst du ein Werkzeug benutzen, antworte AUSSCHLIESSLICH mit einem\n"
        "oder mehreren Bloecken in genau dieser Form — ohne weiteren Text:\n"
        '<tool_call>\n{"name": "<werkzeugname>", "parameters": {<argumente>}}\n</tool_call>\n'
        "Brauchst du kein Werkzeug, antworte normal in Prosa."
    )


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Extrahiert ``<tool_call>``-Bloecke aus einer CLI-Antwort.

    Akzeptiert nur Bloecke mit ``name``; ``parameters`` darf fehlen (dann leer),
    weil parameterlose Werkzeuge wie ``refresh`` sonst verloren gingen.
    Unparsbare Bloecke werden uebersprungen statt den ganzen Turn zu kippen —
    die Antwort enthaelt dann eben Prosa statt eines Aufrufs.
    """
    calls: List[Dict[str, Any]] = []
    for match in TOOL_CALL_RE.finditer(text or ""):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name:
            continue
        parameters = data.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        calls.append({"name": name, "parameters": parameters})
    return calls


def strip_tool_calls(text: str) -> str:
    """Antworttext ohne die ``<tool_call>``-Bloecke."""
    return TOOL_CALL_RE.sub("", text or "").strip()


def build_codex_cli_command(*, model: Optional[str]) -> list[str]:
    """Argumentliste fuer einen ``codex exec``-Aufruf.

    Der Prompt steht bewusst NICHT in der Argumentliste, sondern geht ueber
    stdin — das abschliessende ``-`` sagt ``codex exec``, dass es die
    Instruktionen von dort liest.

    Als Argument riss ein Runden-Prompt Linux' ``MAX_ARG_STRLEN``: ein
    *einzelnes* argv-Element darf 128 KiB (32 Seiten) nicht ueberschreiten,
    unabhaengig vom deutlich hoeheren ``ARG_MAX`` fuer die Summe. Ein
    Runden-Prompt traegt Persona, Historie und Werkzeugschemata und liegt
    darueber; auf armserver starben dadurch 12 Agenten-Turns einer Runde mit
    ``OSError: [Errno 7] Argument list too long``. stdin kennt diese Grenze
    nicht.

    Ausgelagert, damit der synchrone Pfad hier und der abbrechbare
    async-Pfad im OASIS-Subprozess (``scripts/sim_runtime/codex_cli_model.py``,
    Issue #1423) dieselbe Kommandozeile bauen — inklusive der
    Sandbox-Flags, die nicht auseinanderlaufen duerfen.

    Raises:
        CodexCliUnavailableError: wenn das Binary nicht im PATH liegt.
    """
    if not is_codex_cli_available():
        raise CodexCliUnavailableError(
            f"codex-CLI nicht gefunden (PATH, Binary={codex_cli_binary()!r}). "
            "Installation + `codex login` pruefen."
        )
    cmd = [codex_cli_binary(), "exec", "--skip-git-repo-check", "--sandbox", "read-only"]
    # Sentinel weglassen statt als (nicht existentes) --model an die CLI zu
    # reichen — dann entscheidet die lokale codex-Konfiguration/-Session
    # selbst, welches Modell sie faehrt.
    if model and model != CODEX_CLI_DEFAULT_MODEL_ID:
        cmd += ["--model", model]
    cmd.append("-")
    return cmd


def codex_cli_scratch_dir_prefix() -> str:
    """Prefix des isolierten Arbeitsverzeichnisses — von beiden Pfaden genutzt."""
    return "agora-codex-cli-"


def _run_codex_cli(prompt: str, *, model: Optional[str]) -> str:
    cmd = build_codex_cli_command(model=model)
    timeout = codex_cli_timeout_seconds()
    # Isoliertes CWD: `codex exec` liest/interpretiert Repo-Kontext aus dem
    # Arbeitsverzeichnis. Das Backend-Prozess-CWD ist das Agora-Repo selbst —
    # ein Sandbox-Fehlgriff darf dort nichts anfassen koennen.
    with tempfile.TemporaryDirectory(prefix="agora-codex-cli-") as scratch_dir:
        try:
            result = subprocess.run(  # noqa: S603 — Binary kommt aus Config, Argumente sind kein Shell-String
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=scratch_dir,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CodexCliUnavailableError(
                f"codex exec Timeout nach {timeout:.0f}s"
            ) from exc
        except OSError as exc:
            raise CodexCliUnavailableError(f"codex exec konnte nicht gestartet werden: {exc}") from exc
    return interpret_codex_cli_result(result.returncode, result.stdout, result.stderr)


def interpret_codex_cli_result(
    returncode: int, stdout: Optional[str], stderr: Optional[str]
) -> str:
    """Exit-Code und Streams eines ``codex exec``-Laufs auswerten.

    Ausgelagert wie ``build_codex_cli_command``, damit der abbrechbare
    async-Pfad im OASIS-Subprozess (Issue #1423) exakt dieselbe
    Fehlerbehandlung nutzt statt einer nachgebauten.
    """
    if returncode != 0:
        stderr_tail = (stderr or "").strip()[-500:]
        raise CodexCliUnavailableError(
            f"codex exec fehlgeschlagen (exit={returncode}): {stderr_tail}"
        )
    text = (stdout or "").strip()
    if not text:
        raise CodexCliUnavailableError("codex exec lieferte leere Ausgabe")
    return text


# ---------------------------------------------------------------------------
# Minimaler Duck-Type-Shim der OpenAI-SDK-Oberflaeche
# (``client.chat.completions.create(**kwargs) -> .choices[0].message.content``)
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


class _CodexCliCompletions:
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
        ``extra_body``/``stream`` ab — die Codex-CLI kennt keinen dieser
        Parameter. ``stream=True`` wird bewusst NICHT unterstuetzt (kein
        Token-Streaming in diesem Slice); der Aufrufer bekommt hier immer die
        vollstaendige Antwort in einem Zug, ``LLMClient`` erzwingt ueber
        ``_codex_cli_active`` einen nicht-streamenden Call-Pfad.

        ``tools`` wird seit Issue #1423 NICHT mehr verschluckt: die CLI kennt
        zwar kein natives Function-Calling, die Schemas gehen aber als
        Prompt-Abschnitt mit und die Antwort wird wieder in ``tool_calls``
        uebersetzt. Ohne das bleiben OASIS-Agenten handlungsunfaehig — sie
        waehlen ihre Aktionen ausschliesslich ueber Werkzeugaufrufe.
        """
        prompt = _flatten_messages(messages or [])
        if tools:
            prompt += build_tool_prompt(tools)
        try:
            text = _run_codex_cli(prompt, model=model)
        except CodexCliUnavailableError as exc:
            raise LlmProviderError(
                NormalizedLlmError(
                    provider="codex_cli",
                    code="provider_unavailable",
                    message=str(exc),
                    retryable=False,
                )
            ) from exc
        return _ShimChatCompletion(choices=[_ShimChoice(message=build_shim_message(text))])


def build_shim_message(text: str) -> _ShimMessage:
    """CLI-Rohtext -> Assistant-Nachricht, ggf. mit ``tool_calls``.

    Enthaelt die Antwort ``<tool_call>``-Bloecke, werden sie in die
    OpenAI-Form uebersetzt und aus dem ``content`` entfernt; der Rest bleibt
    als Prosa stehen. Ohne Bloecke ist das Ergebnis eine gewoehnliche
    Textantwort — der Pfad vor Issue #1423.

    Die Call-IDs sind synthetisch (``call_codex_<n>``), weil die CLI keine
    vergibt. Sie muessen nur innerhalb einer Antwort eindeutig sein: die
    ReACT-Schleife referenziert damit das passende ``tool``-Ergebnis.
    """
    calls = parse_tool_calls(text)
    if not calls:
        return _ShimMessage(content=text)
    tool_calls = [
        _ShimToolCall(
            id=f"call_codex_{index}",
            function=_ShimFunction(
                name=call["name"],
                arguments=json.dumps(call["parameters"], ensure_ascii=False),
            ),
        )
        for index, call in enumerate(calls)
    ]
    return _ShimMessage(content=strip_tool_calls(text), tool_calls=tool_calls)


class _CodexCliChatNamespace:
    def __init__(self) -> None:
        self.completions = _CodexCliCompletions()


class CodexCliClient:
    """Duck-Type-Ersatz fuer ``openai.OpenAI`` — nur die genutzte Teiloberflaeche."""

    def __init__(self) -> None:
        self.chat = _CodexCliChatNamespace()
