from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    from camel.types import ModelPlatformType  # type: ignore[import]

from dotenv import load_dotenv
from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


# ---------------------------------------------------------------------------
# Issue #1160 F — reproduzierbare Zufallsentscheidungen im Simulationslauf
# ---------------------------------------------------------------------------

SIMULATION_SEED_CONFIG_KEY = "random_seed"
"""Feld in ``simulation_config.json``, mit dem ein Seed vorgegeben wird."""

_SEED_MODULUS = 2**32
"""Obergrenze des abgeleiteten Seeds — ``random.seed`` nimmt beliebige ints,
aber ein begrenzter Wertebereich bleibt les- und protokollierbar."""


def derive_simulation_seed(config: dict[str, Any], *, fallback: str = "") -> int:
    """Bestimmt den Seed eines Laufs — vorgegeben oder aus der Lauf-ID abgeleitet.

    Issue #1160 F: Der Simulationslauf traf seine Zufallsentscheidungen
    (welche Agenten in einer Runde aktiv werden, wie viele es sind) aus dem
    globalen, ungeseedeten ``random``-Zustand. Zwei Laeufe derselben
    Konfiguration waren damit nicht vergleichbar — und ohne Vergleichbarkeit
    ist jeder Re-Run und jede Baseline-Messung methodisch angreifbar.

    Reihenfolge:

    1. ``config["random_seed"]``, wenn gesetzt und als ganze Zahl lesbar —
       der Weg, um einen Lauf gezielt zu wiederholen.
    2. sonst deterministisch aus ``config["simulation_id"]`` (ersatzweise
       ``fallback``): derselbe Lauf ergibt beim Neustart denselben Seed,
       verschiedene Laeufe verschiedene.

    Abgeleitet wird ueber SHA-256, **nicht** ueber ``hash()``: Pythons
    String-Hash ist pro Prozess zufaellig gesalzen (``PYTHONHASHSEED``), ein
    darauf gebauter Seed waere also genau das Gegenteil von reproduzierbar.
    """
    raw = config.get(SIMULATION_SEED_CONFIG_KEY)
    if raw is not None and not isinstance(raw, bool):
        try:
            return int(raw) % _SEED_MODULUS
        except (TypeError, ValueError):
            pass

    identity = str(config.get("simulation_id") or fallback or "agora-simulation")
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def seed_simulation_rng(config: dict[str, Any], *, fallback: str = "") -> int:
    """Seedet den globalen ``random``-Zustand des Subprozesses und gibt den Seed zurueck.

    Bewusst der **globale** Zustand und keine eigene ``random.Random``-Instanz:
    die Zufallsentscheidungen stecken nicht nur in Agora-Code, sondern auch in
    OASIS und CAMEL. Eine eigene Instanz haette nur die Aufrufstellen erfasst,
    die wir kennen, und den Rest weiter unkontrolliert gelassen.

    Grenze, die dieser Aufruf **nicht** aufhebt: die Antworten der Sprachmodelle
    bleiben nichtdeterministisch. Reproduzierbar wird damit der stochastische
    Anteil des Laufs (Agentenauswahl, Aktivitaetswuerfe), nicht der Report.
    Wer identische Berichte braucht, braucht zusaetzlich die Aufzeichnung der
    LLM-Antworten — eigener Slice (#763).
    """
    seed = derive_simulation_seed(config, fallback=fallback)
    random.seed(seed)
    return seed


def detect_oasis_platform(model: str, base_url: str) -> ModelPlatformType:
    """Map model-name + base-url to the correct CAMEL ModelPlatformType.

    Delegiert die Detection an ``app.llm.providers.registry.detect_provider``
    (``mode="oasis"``, Single Source of Truth seit #591) und mappt das
    Vokabular ``google|ollama|openai`` auf ``ModelPlatformType``. Die
    Heuristik-Logik lebt jetzt in der Registry, damit HTTP-Client
    (``app/llm/providers/base.py``) und OASIS-Subprozess dieselbe Quelle
    nutzen; die bewussten Divergenzen zwischen beiden Modi sind in
    ``registry.py`` tabellarisch dokumentiert.

    Bedeutung der Zweige (first match wins, siehe ``registry._detect_oasis``):

    1. GEMINI — base_url enthält ``generativelanguage.googleapis.com`` ODER
       Modell beginnt mit ``gemini-``.  Gemini-3 braucht ein
       ``thought_signature``-Echo in Multi-Turn-Tool-Calls; der
       OpenAI-Compat-Wire-Pfad strippt das Feld → HTTP 400 pro Tool-Turn.
    2. OLLAMA — base_url enthält ``ollama.com`` oder ``:11434`` ODER Modell
       endet auf ``:cloud`` / ``:latest``.  CAMELs ``OllamaModel`` erbt von
       ``OpenAICompatibleModel`` und spricht ``POST {base_url}/chat/
       completions`` — die Base-URL muss deshalb auf ``/v1`` enden, siehe
       ``resolve_camel_ollama_url``.
    3. OPENAI — Default / Compat-Gateway.
    """
    from camel.types import ModelPlatformType  # type: ignore[import]

    from app.llm.providers.registry import detect_provider as _detect

    detected = _detect(base_url, model, mode="oasis")
    if detected == "google":
        return ModelPlatformType.GEMINI
    if detected == "ollama":
        return ModelPlatformType.OLLAMA
    return ModelPlatformType.OPENAI


def _is_ollama_route(model: str, base_url: str) -> bool:
    """True wenn das Modell über Ollama (lokal oder Cloud) läuft.

    Duenner Wrapper um die Provider-Single-Source-of-Truth
    (``app.llm.providers.registry.detect_provider``, ``mode="oasis"``, seit
    #591). Ollama genau dann, wenn die SSoT ``"ollama"`` liefert — d. h.
    Base-URL enthält ``ollama.com`` oder Port ``:11434`` ODER Modellname endet
    auf ``:cloud`` / ``:latest`` (siehe ``registry._detect_oasis``).

    Fix #670: Die vormalige lokale Heuristik (``:cloud``-Suffix ODER Substring
    ``11434``) verfehlte ``ollama.com/v1``-URLs ohne ``:cloud``-Suffix sowie
    ``:latest``-Modelle → das think/num_ctx-Gate in ``build_camel_extra_body``
    fiel faelschlich aus. Die Delegation an die SSoT schliesst diese Luecke,
    ohne das Prod-Verhalten zu aendern (``gpt-oss:20b-cloud`` @ ``:11435``
    traegt weder ``:cloud`` noch ``:11434`` → weiterhin ``"openai"``).
    """
    from app.llm.providers.registry import detect_provider

    return detect_provider(base_url, model, mode="oasis") == "ollama"


def resolve_camel_ollama_url(base_url: str | None) -> str | None:
    """Base-URL fuer CAMELs ``OllamaModel`` — mit erzwungenem ``/v1``.

    Duenner Wrapper um die Provider-SSoT
    (``app.llm.providers.registry.ensure_v1_suffix``), analog zu
    ``detect_oasis_platform``: keine zweite URL-Heuristik neben der Registry.

    Hintergrund: CAMELs ``OllamaModel`` ist ein ``OpenAICompatibleModel`` und
    ruft ``POST {base_url}/chat/completions``. Der Registry-Default fuer Ollama
    Cloud (``https://ollama.com``) und die lokale Default-URL
    (``http://localhost:11434``) tragen kein ``/v1`` — beide sind fuer Agoras
    eigenen HTTP-Pfad korrekt, der nativ ``/api/chat`` spricht, fuer CAMEL aber
    falsch. Ohne diese Normalisierung geht der Preflight-Probe auf
    ``https://ollama.com/chat/completions`` und faengt sich Ollamas
    HTML-404-Seite als ``openai.NotFoundError``.
    """
    from app.llm.providers.registry import ensure_v1_suffix

    return ensure_v1_suffix(base_url)


def uses_max_completion_tokens(model: str) -> bool:
    """True wenn das Modell ``max_completion_tokens`` statt ``max_tokens`` verlangt.

    Hintergrund: Die OpenAI GPT-5-Familie und die Reasoning-Modelle
    ``o1`` / ``o3`` / ``o4`` haben ``max_tokens`` deprecated und
    antworten 400 ``Unsupported parameter: 'max_tokens' is not supported
    with this model. Use 'max_completion_tokens' instead.``, sobald der
    Parameter im Request-Body landet. Ältere OpenAI-Modelle (``gpt-4o``,
    ``gpt-4-turbo``, ``gpt-3.5-turbo``) sowie alle nicht-OpenAI-Backends
    (Qwen, Llama, Claude, DeepSeek, Mistral, Ollama-Modelle) nutzen
    weiterhin ``max_tokens``.

    Heuristik: Modellname (case-insensitiv, getrimmt) beginnt mit
    ``gpt-5`` oder einem ``o<n>``-Prefix gefolgt von ``-`` oder Ende.
    """
    lowered = model.strip().lower()
    if lowered.startswith("gpt-5"):
        return True
    for prefix in ("o1", "o3", "o4"):
        if lowered == prefix or lowered.startswith(f"{prefix}-"):
            return True
    return False


_GPT5_MODEL_RE = re.compile(r"^gpt-5(?:\.(\d+))?(?:-|$)")


def supports_reasoning_effort_none(model: str) -> bool:
    """True wenn das Modell ``reasoning_effort: "none"`` akzeptiert.

    Hintergrund: GPT-5.x verlangt bei Function-Tools auf
    ``/v1/chat/completions`` ein explizites ``reasoning_effort: "none"`` —
    ohne den Parameter greift serverseitig ein Reasoning-Default und
    Tools + Reasoning gibt es nur auf ``/v1/responses`` (400
    ``Function tools with reasoning_effort are not supported ...``).

    **Wichtig:** Das ursprüngliche ``gpt-5`` (5.0, ohne Minor-Version)
    kennt ``"none"`` NICHT — dort sind nur ``minimal``…``high`` gültig.
    Erst ab Minor-Version 5.1 (``gpt-5.1``, ``gpt-5.6-luna`` etc.) ist
    ``"none"`` ein gültiger Wert. Modelle ohne erkennbare Minor-Version
    (``gpt-5``, ``gpt-5-mini``, ``gpt-5-turbo``) gelten als 5.0 und
    bekommen den Parameter NICHT gesetzt.

    Heuristik: Modellname (case-insensitiv, getrimmt) matched
    ``gpt-5``, optional gefolgt von ``.<minor>``, danach ``-`` oder Ende.
    Minor-Version muss vorhanden und ``>= 1`` sein.
    """
    lowered = model.strip().lower()
    match = _GPT5_MODEL_RE.match(lowered)
    if match is None:
        return False
    minor = match.group(1)
    if minor is None:
        return False
    return int(minor) >= 1


def build_camel_completion_params(
    *,
    model: str,
    completion_max_tokens: int,
) -> dict[str, Any]:
    """Baut den Token-Limit-Block für ``ModelFactory.create()``.

    Liefert ``{"max_completion_tokens": N}`` für GPT-5/o1/o3/o4 und
    ``{"max_tokens": N}`` für alle anderen Modelle. Für GPT-5.1+
    (nicht das ursprüngliche GPT-5.0) wird zusätzlich
    ``reasoning_effort: "none"`` gesetzt, sonst schlagen Function-Tool-
    Calls mit 400 fehl (siehe ``supports_reasoning_effort_none``).
    """
    key = "max_completion_tokens" if uses_max_completion_tokens(model) else "max_tokens"
    params: dict[str, Any] = {key: completion_max_tokens}
    if supports_reasoning_effort_none(model):
        params["reasoning_effort"] = "none"
    return params


def build_camel_extra_body(
    *,
    model: str,
    base_url: str,
    num_ctx: int | None,
    think: bool,
) -> dict[str, Any]:
    """
    Builds Ollama-specific request parameters for the model factory.
    
    Parameters:
        model (str): Model name used to identify the provider route.
        base_url (str): Base URL used to identify the provider route.
        num_ctx (int | None): Optional Ollama context size.
        think (bool): Whether Ollama should enable thinking.
    
    Returns:
        dict[str, Any]: An Ollama parameter mapping, or an empty dictionary for other provider routes.
    """
    if not _is_ollama_route(model, base_url):
        return {}

    body: dict[str, Any] = {"think": think}
    if num_ctx is not None:
        body["options"] = {"num_ctx": num_ctx}
    return body


def _is_minimax_route(model: str, base_url: str) -> bool:
    """Determine whether the request targets the MiniMax provider.
    
    Returns:
        bool: `True` for MiniMax routes, `False` otherwise.
    """
    from app.llm.providers.registry import detect_provider

    return detect_provider(base_url, model, mode="http") == "minimax"


def build_minimax_extra_body(*, model: str, base_url: str, think: bool) -> dict[str, Any]:
    """
    Builds the MiniMax-specific thinking configuration for a request.
    
    Parameters:
        model (str): Model name used for provider detection.
        base_url (str): Provider endpoint used for route detection.
        think (bool): Whether adaptive reasoning should be enabled.
    
    Returns:
        dict[str, Any]: A MiniMax thinking configuration, or an empty dictionary for other routes.
    """
    if not _is_minimax_route(model, base_url):
        return {}

    return {"thinking": {"type": "adaptive" if think else "disabled"}}


@dataclass(frozen=True)
class RuntimePaths:
    scripts_dir: Path
    backend_dir: Path
    project_root: Path


def resolve_runtime_paths(script_file: str | Path) -> RuntimePaths:
    script_path = Path(script_file).resolve()
    scripts_dir = script_path.parent
    backend_dir = scripts_dir.parent
    project_root = backend_dir.parent
    return RuntimePaths(
        scripts_dir=scripts_dir,
        backend_dir=backend_dir,
        project_root=project_root,
    )


def install_script_paths(paths: RuntimePaths) -> None:
    for path in (str(paths.scripts_dir), str(paths.backend_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)


def load_project_env(script_file: str | Path, *, verbose: bool = False) -> Path | None:
    paths = resolve_runtime_paths(script_file)
    candidates: Iterable[Path] = (
        paths.project_root / ".env",
        paths.backend_dir / ".env",
    )
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate)
            if verbose:
                print(f"Loaded environment configuration: {candidate}")
            return candidate
    return None


def init_runner_tracing(service_name: str) -> None:
    """Setup TracerProvider im OASIS-Runner und übernimm Parent-Context aus ENV.

    Wird von ``run_*_simulation.py`` direkt nach den Imports gerufen.
    Schlägt lautlos fehl, wenn ``app.observability`` nicht importierbar ist
    (z.B. wenn OTEL-Deps nicht installiert sind oder ``OTEL_ENABLED=false``).
    """
    try:
        from app.observability import init_tracing  # type: ignore[import]
    except ImportError:
        return
    init_tracing(service_name)

    traceparent = os.environ.get("TRACEPARENT")
    if traceparent:
        ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
        otel_context.attach(ctx)


def init_runner_logging(service_name: str) -> None:
    """Setup LoggerProvider im OASIS-Runner.

    Wird von ``run_*_simulation.py`` direkt nach ``init_runner_tracing`` gerufen.
    Schlägt lautlos fehl, wenn ``app.observability`` nicht importierbar ist
    oder ``OTEL_LOGS_ENABLED=false`` (Default-Off).
    """
    try:
        from app.observability import init_logging  # type: ignore[import]
    except ImportError:
        return
    init_logging(service_name)


def should_filter_max_tokens_warning(message: str) -> bool:
    return "max_tokens" in message and "Invalid or missing" in message


class MaxTokensWarningFilter(logging.Filter):
    """Filter out camel-ai max_tokens warnings."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not should_filter_max_tokens_warning(record.getMessage())


def install_max_tokens_warning_filter() -> None:
    root_logger = logging.getLogger()
    if not any(isinstance(f, MaxTokensWarningFilter) for f in root_logger.filters):
        root_logger.addFilter(MaxTokensWarningFilter())


_DEFAULT_CONTEXT_FLOOR = 262_144


def apply_camel_context_floor(default_floor: int = _DEFAULT_CONTEXT_FLOOR) -> int:
    """Hebe CAMELs ScoreBasedContextCreator-Default-Token-Limit auf
    LLM_CONTEXT_LIMIT (oder ``default_floor``) an.

    Hintergrund: ``camel.memories.context_creators.score_based.ScoreBasedContextCreator``
    initialisiert ``token_limit`` per Default auf 8192. Sobald CAMEL einen
    Agent ohne explizit hochgesetztes Limit anlegt, kappt die Memory-Truncation
    bei 8 k Tokens — unabhaengig davon, ob das Modell 256 k oder 1 M kann.
    Diese Funktion patcht ``__init__`` so, dass der Floor als Mindestwert wirkt
    (groessere Werte aus dem Aufrufer werden respektiert).

    Idempotent: mehrfache Aufrufe sind ein No-op. Gibt den effektiven Floor
    zurueck, damit der Aufrufer ihn loggen kann.
    """
    try:
        floor = int(os.environ.get("LLM_CONTEXT_LIMIT", str(default_floor)))
    except ValueError:
        floor = default_floor

    try:
        from camel.memories.context_creators.score_based import (
            ScoreBasedContextCreator,
        )
    except ImportError:
        return floor

    if getattr(ScoreBasedContextCreator, "_agora_context_floor_applied", False):
        return floor

    original_init = ScoreBasedContextCreator.__init__

    def _patched_init(self, token_counter, token_limit=None, *args, **kwargs):
        effective = floor if (token_limit is None or token_limit < floor) else token_limit
        return original_init(self, token_counter, effective, *args, **kwargs)

    ScoreBasedContextCreator.__init__ = _patched_init
    ScoreBasedContextCreator._agora_context_floor_applied = True
    return floor


class UnicodeFormatter(logging.Formatter):
    """Convert unicode escape sequences to readable characters."""

    UNICODE_ESCAPE_PATTERN = re.compile(r"\\u([0-9a-fA-F]{4})")

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)

        def replace_unicode(match: re.Match[str]) -> str:
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)

        return self.UNICODE_ESCAPE_PATTERN.sub(replace_unicode, result)


def setup_oasis_logging(log_dir: str | Path) -> None:
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    formatter = UnicodeFormatter("%(levelname)s - %(asctime)s - %(name)s - %(message)s")
    loggers_config = {
        "social.agent": log_dir_path / "social.agent.log",
        "social.twitter": log_dir_path / "social.twitter.log",
        "social.rec": log_dir_path / "social.rec.log",
        "oasis.env": log_dir_path / "oasis.env.log",
        "table": log_dir_path / "table.log",
    }

    for logger_name, log_file in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="w")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.propagate = False


def _add_shared_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Configuration file path (simulation_config.json)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Maximum simulation rounds (optional, used to truncate long simulations)",
    )
    parser.add_argument(
        "--num-agents",
        type=int,
        default=30,
        help="Minimum number of agents for the simulation. Default 30 (Slice 4 Floor).",
    )
    parser.add_argument(
        "--num-rounds",
        type=int,
        default=10,
        help="Number of simulation rounds. Default 10 (Slice 4 Floor).",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        default=False,
        help="Close environment immediately after simulation completes, do not enter wait mode",
    )
    return parser


def build_single_platform_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    return _add_shared_arguments(parser)


def build_parallel_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OASIS Dual-Platform Parallel Simulation")
    parser.add_argument("--twitter-only", action="store_true", help="Only run Twitter simulation")
    parser.add_argument("--reddit-only", action="store_true", help="Only run Reddit simulation")
    return _add_shared_arguments(parser)


def compute_start_hour_offset(
    config: dict[str, Any],
    total_rounds: int,
    minutes_per_round: int,
) -> int:
    """Pick a simulated-clock offset so short runs don't sit entirely in the
    agents' inactive hours.

    Why: ``simulated_hour`` rolls from 0..23 starting at midnight. With
    ``minutes_per_round=60`` and ``--max-rounds 3`` the loop only visits hours
    0/1/2, while typical ``active_hours`` start at 9. Result: every round
    short-circuits via ``if not active_agents: continue`` and the platform
    reports "0 actions, 0.0s".

    Respect ``time_config.start_hour`` if explicitly set. Otherwise, when the
    truncated run can't naturally cycle through 24h, shift to the most
    populated active hour from ``agent_configs``.
    """
    time_config = config.get("time_config", {}) or {}
    explicit = time_config.get("start_hour")
    if explicit is not None:
        return int(explicit) % 24

    simulated_hours = (total_rounds * minutes_per_round) / 60.0
    if simulated_hours >= 24:
        return 0

    from collections import Counter
    hour_counts: Counter[int] = Counter()
    for ac in config.get("agent_configs", []) or []:
        for h in ac.get("active_hours", []) or []:
            hour_counts[int(h) % 24] += 1
    if not hour_counts:
        return 9
    return int(hour_counts.most_common(1)[0][0])


def compute_post_sim_time(
    anchor: datetime,
    start_hour_offset: int,
    simulated_minutes: int,
    minutes_per_round: int,
    action_index: int,
    action_count: int,
) -> datetime:
    """Spread a round's actions across that round's simulated minute budget.

    Why: the simulated clock only advances once per round, so every
    CREATE_POST frame of a round used to carry the identical ``sim_time``.
    The live-feed clock then jumps at round boundaries and stands still in
    between — for short runs it looks frozen outright (#1018).

    The intra-round offset stays strictly below ``minutes_per_round``, so the
    last frame of a round is still strictly earlier than the first frame of
    the next one. That ordering is load-bearing: ``useSimClock`` in the
    frontend enforces monotonicity and silently drops any frame that would
    move the clock backwards.

    ``action_index`` counts every action of the round, not just the emitted
    CREATE_POST ones — it is the round's time axis, not a post counter.
    """
    round_start = anchor + timedelta(
        minutes=start_hour_offset * 60 + simulated_minutes
    )
    if action_count <= 1 or action_index <= 0:
        return round_start
    index = min(action_index, action_count - 1)
    return round_start + timedelta(
        minutes=minutes_per_round * index / action_count
    )


# ---------------------------------------------------------------------------
# Preflight-Probe: ein einzelner Chat-Completion-Call vor dem Agenten-Fan-out
# ---------------------------------------------------------------------------

# Status-Codes, die auf einen permanenten Konfigurationsfehler hinweisen —
# Auth (401/403) oder Routing/Modell (404). Ein Retry wäre hier verschwendete
# Zeit; der Run muss mit einer klaren Root-Cause-Meldung abgelehnt werden,
# bevor N Agenten denselben Fehler produzieren (Akzeptanzkriterium #6).
_PERMANENT_STATUS = {401, 403, 404}
# Transiente/Server-Fehler, die ein Backoff-Retry rechtfertigen. 408/599
# ergänzen die typische openai-Retry-Menge; 429 ist Rate-Limit.
_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 599}


def _should_skip_preflight() -> bool:
    """True, wenn der Preflight-Probe per ``AGORA_SKIP_PREFLIGHT=1`` deaktiviert ist.

    Opt-out-Schalter (Default: ``0``/unset → Probe läuft). Entkoppelt den
    Sim-Start von der Ollama-/Provider-Verfügbarkeit — nützlich für Tests,
    Mock-Backends und Offline-Entwicklung. Produktive Container bleiben
    unberührt (kein Default-Verhaltenswechsel). Siehe Issue #871.
    """
    return os.environ.get("AGORA_SKIP_PREFLIGHT", "0") == "1"


def preflight_model_probe(
    model: Any,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.2,
) -> None:
    """
    Führt vor der Simulation eine kleine Chat-Completion-Probe für das Modell aus.
    
    Sendet eine einzelne „ping“-Nachricht und wiederholt bestimmte vorübergehende
    Provider-Fehler mit exponentiellem Backoff. Authentifizierungs- und Routingfehler
    sowie nicht behebbare oder nach den Wiederholungen weiterhin bestehende Fehler
    werden als `ValueError` gemeldet. Ausnahmen anderer Plattformen werden unverändert
    weitergegeben.

    Skip: Per ``AGORA_SKIP_PREFLIGHT=1`` (Opt-out, Default off) wird der Probe
    vollständig übersprungen — die Simulation kann dann ohne erreichbares Ollama
    starten (Tests, Mock-Backends, Offline-Entwicklung). Eine Warnung wird geloggt.
    
    Parameters:
        model (Any): Das zu prüfende Modell.
        max_retries (int): Maximale Anzahl zusätzlicher Versuche bei vorübergehenden Fehlern.
        backoff_base (float): Anfangsverzögerung in Sekunden für den exponentiellen Backoff.

    Raises:
        ValueError: Wenn ein permanenter oder nicht behebbarer Provider-Fehler auftritt.
    """
    if _should_skip_preflight():
        logging.getLogger("agora._sim_common").warning(
            "preflight probe skipped via AGORA_SKIP_PREFLIGHT",
            extra={"event": "preflight_skipped", "env": "AGORA_SKIP_PREFLIGHT"},
        )
        return

    import openai

    probe_messages = [{"role": "user", "content": "ping"}]
    for attempt in range(max_retries + 1):
        try:
            model.run(probe_messages)
            return
        except openai.APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            if status in _PERMANENT_STATUS:
                raise ValueError(
                    f"OASIS-Preflight: permanenter Provider-Fehler "
                    f"(HTTP {status}) für die aufgelöste Route — Simulation "
                    f"vor dem Fan-out abgelehnt. Ursache: {exc}"
                ) from exc
            if status in _TRANSIENT_STATUS and attempt < max_retries:
                time.sleep(backoff_base * (2 ** attempt))
                continue
            # Unbekannter Status oder Retries erschöpft → als permanent gelten.
            raise ValueError(
                f"OASIS-Preflight: Provider-Fehler (HTTP {status}) ließ sich "
                f"nach {attempt + 1} Versuch(en) nicht beheben — Simulation "
                f"vor dem Fan-out abgelehnt. Ursache: {exc}"
            ) from exc
        # Nicht-openai-Plattformen (Gemini/Ollama) werfen ihre nativen
        # Exceptions — ungefiltert weiterreichen, damit der Run sauber
        # scheitert, statt hier eine lückenhafte Heuristik zu pflegen.


# ---------------------------------------------------------------------------
# Slice fix/oom-bert-lowmem-fp16: BERT-Memory-Profile + RSS-Sampler
# ---------------------------------------------------------------------------
# Hintergrund: Auf 2.8-GiB-Container-Hosts kippt der OASIS-Subprozess mit
# ``Process exit code: -9`` (Linux-OOM-Killer, ``cgroup memory.events: oom_kill=1``),
# sobald ``Twitter/twhin-bert-base`` (1.06 GB safetensors, fp32) im ersten
# ``update_rec_table()``-Tick lazy geladen wird — plus den 250-350 MB
# ``torch``/``transformers``/``sentence_transformers``-Import-Overhead aus
# ``oasis.social_platform.recsys`` und ``process_recsys_posts``.
#
# Diese Helper werden in ``run_parallel_simulation.py`` UND
# ``run_reddit_simulation.py`` VOR dem ersten ``oasis``-Import aufgerufen.
# Da Python Modul-Level-Caching nutzt, sieht der spaetere
# ``from transformers import AutoModel``-Aufruf in
# ``oasis.social_platform.process_recsys_posts`` die gepatchte Methode
# auf demselben Klassen-Objekt.

_TWHIN_BERT_MODEL_NAMES: frozenset[str] = frozenset(
    {
        "Twitter/twhin-bert-base",
    }
)

_BERT_PROFILE_DEFAULT = "auto"

# Ab dieser verfuegbaren Container-RAM (MB) laden wir TWHIN-BERT in fp32.
# fp32 besitzt native CPU-Kernel und laeuft 16-threaded (~14 s/Forward);
# fp16 hat auf CPU keine nativen Kernel und fallt auf eine langsame
# single-threaded Emulation zurueck (~12 min/Forward — blockiert den
# asyncio-Event-Loop der OASIS-Plattform). Darunter bleibt fp16 aktiv als
# OOM-Schutz fuer Kleincontainer der 2.8-GiB-Klasse (Originalanforderung
# dieses Profils). 4 GB Deckt die ~1.2 GB fp32-Modellgewichte + 250-350 MB
# torch/transformers-Import-Overhead + Working-Set des Forward sicher ab.
_BERT_FP32_MIN_AVAIL_MB = 4096


def install_bert_memory_profile(profile: str | None = None) -> str:
    """
    Aktiviert ein speicherschonendes Ladeprofil für TWHIN-BERT.

    Das Profil wird über den Parameter oder ``AGORA_BERT_MEMORY_PROFILE`` bestimmt
    und standardmäßig auf ``"auto"`` gesetzt. Für TWHIN-BERT werden geeignete
    Speicheroptionen gesetzt; andere Modelle bleiben unverändert. Bei
    deaktiviertem Profil oder fehlender Transformers-Bibliothek erfolgt keine
    Anpassung.

    Profil-Level:

    - ``"off"``  — kein Patch (Bypass).
    - ``"low"``  — immer ``low_cpu_mem_usage=True`` UND ``torch_dtype=fp16``
      (OOM-Schutz fuer 2.8-GiB-Kleincontainer; historisches Verhalten).
    - ``"auto"`` — ``low_cpu_mem_usage=True`` immer; ``fp16`` NUR bei knappem
      Container-RAM (``< _BERT_FP32_MIN_AVAIL_MB``), sonst fp32 (schnelle
      native CPU-Kernel). Kann der verfuegbare RAM nicht ermittelt werden,
      bleibt es konservativ bei fp16. Default seit dem Fix des
      Round-0-Hangs (fp16-Forward blockierte den Event-Loop ~12 min).

    Args:
        profile: Zu verwendendes Speicherprofil (``"off"``, ``"low"`` oder
            ``"auto"``). Ohne Angabe greift ``AGORA_BERT_MEMORY_PROFILE`` bzw.
            der Default.

    Returns:
        Der effektive Profilname.
    """
    effective = (profile or os.environ.get("AGORA_BERT_MEMORY_PROFILE") or _BERT_PROFILE_DEFAULT).lower()
    if effective == "off":
        return "off"

    # fp16-Injektion entscheiden (einmalig, zur Patch-Zeit):
    #  - "low":  immer fp16 (OOM-Schutz, historisches Verhalten).
    #  - "auto": fp16 nur bei knappem Container-RAM (< Schwellenwert),
    #            sonst fp32 (16-Thread-CPU-Kernel, ~14 s/Forward). Laesst sich
    #            der RAM nicht ermitteln, konservativ fp16 (OOM-Schutz bleibt).
    #  - sonst:  fp16 (backward-kompatibel zu unbekannten Profilnamen).
    if effective == "auto":
        avail_mb = _read_available_mb_linux()
        inject_fp16 = not (avail_mb is not None and avail_mb >= _BERT_FP32_MIN_AVAIL_MB)
    else:
        inject_fp16 = True

    try:
        import transformers  # type: ignore[import-not-found]
    except ImportError:
        # Wenn transformers gar nicht da ist, ist der Patch sinnlos — kein
        # BERT wird geladen. Kein Hard-Fail, der Subprozess kann ohne
        # Recsys trotzdem weiterlaufen.
        return effective

    auto_model = getattr(transformers, "AutoModel", None)
    if auto_model is None:
        return effective

    original = auto_model.from_pretrained
    if getattr(original, "_agora_bert_memory_profile_applied", False):
        return effective

    # Lazy-Resolve torch dtype; fallback wenn torch fehlt.
    torch_float16: Any = None
    try:
        import torch  # type: ignore[import-not-found]
        torch_float16 = torch.float16
    except ImportError:
        pass

    def _patched_from_pretrained(*args: Any, **kwargs: Any):
        # Modellname ist typischerweise das erste positional arg oder
        # ``pretrained_model_name_or_path`` als kwarg.
        """
        Lädt TWHIN-BERT-Modelle mit speichersparenden Standardeinstellungen.

        Returns:
            Das von der ursprünglichen Ladefunktion erzeugte Modell.
        """
        model_name = args[0] if args else kwargs.get("pretrained_model_name_or_path")
        if isinstance(model_name, str) and model_name in _TWHIN_BERT_MODEL_NAMES:
            # User-Override hat Vorrang.
            if "low_cpu_mem_usage" not in kwargs:
                kwargs["low_cpu_mem_usage"] = True
            if torch_float16 is not None and inject_fp16 and "torch_dtype" not in kwargs:
                kwargs["torch_dtype"] = torch_float16
        return original(*args, **kwargs)

    _patched_from_pretrained._agora_bert_memory_profile_applied = True  # type: ignore[attr-defined]
    auto_model.from_pretrained = _patched_from_pretrained
    return effective


def _read_rss_mb_linux() -> float | None:
    """Liest ``VmRSS`` aus ``/proc/self/status`` (Linux-Container).

    Liefert ``None``, wenn die Datei nicht vorhanden ist (z.B. macOS-Dev).
    """
    status_path = Path(f"/proc/{os.getpid()}/status")
    try:
        with status_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _read_available_mb_linux() -> float | None:
    """Verfuegbaren RAM in MB — cgroup-Limit bevorzugt, Fallback /proc/meminfo.

    In einem Docker-Container zeigt ``/proc/meminfo`` (ohne lxcfs) den
    Host-Speicher, nicht das tatsaechliche Container-Limit. Daher wird
    zunaechst das cgroup-Speicherlimit (v2, dann v1) minus aktueller
    Belegung gelesen; erst wenn kein endliches cgroup-Limit ermittelt werden
    kann, greift der ``MemAvailable``-Fallback (Bare-Metal-/Dev-Host).

    Liefert ``None``, wenn keine Quelle lesbar ist (z.B. macOS-Dev oder
    nicht-Linux). Fuer ``"auto"``-Profil bedeutet das: konservativ fp16
    verwenden (OOM-Schutz bleibt erhalten).
    """
    # cgroup v2: /sys/fs/cgroup/memory.max + memory.current.
    try:
        limit_text = Path("/sys/fs/cgroup/memory.max").read_text(encoding="utf-8").strip()
        if limit_text != "max":
            limit_bytes = int(limit_text)
            usage_bytes = int(
                Path("/sys/fs/cgroup/memory.current").read_text(encoding="utf-8").strip()
            )
            return max(0.0, (limit_bytes - usage_bytes) / 1024.0 / 1024.0)
    except (OSError, ValueError):
        pass
    # cgroup v1: memory.limit_in_bytes / memory.usage_in_bytes.
    try:
        limit_bytes = int(
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            .read_text(encoding="utf-8")
            .strip()
        )
        # v1 kodiert "kein Limit" als sehr grossen Wert (~2^63-1).
        if limit_bytes < (1 << 62):
            usage_bytes = int(
                Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
                .read_text(encoding="utf-8")
                .strip()
            )
            return max(0.0, (limit_bytes - usage_bytes) / 1024.0 / 1024.0)
    except (OSError, ValueError):
        pass
    # Fallback: /proc/meminfo MemAvailable (kB -> MB).
    try:
        with Path("/proc/meminfo").open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None


def make_default_memory_sink(project_root: Path) -> Path:
    """Baut den Default-NDJSON-Sink-Pfad fuer den Memory-Sampler.

    Die PID wird in den Dateinamen eingebettet, damit parallele Sim-Runs
    (z.B. ``run_parallel_simulation.py`` startet Twitter+Reddit in einem
    Prozess, mehrere ``run_reddit_simulation.py``-Prozesse koennen
    gleichzeitig auf demselben Host laufen) sich nicht gegenseitig die
    NDJSON-Datei zerschreiben.

    Vor dem Fix fuehrten alle 3 Run-Scripts auf
    ``<project_root>/.runtime/mem_profile.ndjson`` ohne PID — POSIX
    "append"-Mode ist zwischen Prozessen NICHT byteweise atomar
    (Schreibbuffer > ``PIPE_BUF`` wird verschachtelt), was bei
    parallelen Runs zerhacktes NDJSON erzeugte (CodeRabbit-Finding
    #859, 3x).
    """
    return project_root / ".runtime" / f"mem_profile.{os.getpid()}.ndjson"


def install_memory_sampler(
    sink: Path,
    *,
    interval_s: float = 0.5,
    rss_reader: Callable[[], float | None] | None = None,
) -> Callable[[], None]:
    """
    Startet bei aktivierter Debug-Konfiguration einen Hintergrund-Thread zur RSS-Speicherüberwachung.
    
    Der Sampler schreibt regelmäßig NDJSON-Snapshots mit den Feldern `label`, `rss_mb` und
    `time_s` in die Zieldatei. Bei deaktivierter Überwachung wird eine No-op-Funktion
    zurückgegeben.
    
    Args:
        sink: Zieldatei für die NDJSON-Snapshots.
        interval_s: Zeitabstand zwischen den Messungen in Sekunden.
        rss_reader: Optionaler RSS-Reader für die Messwerte.
    
    Returns:
        Eine idempotente Funktion zum Beenden des Samplers.
    """
    enabled = os.environ.get("AGORA_DEBUG_MEMORY", "").lower() in {"1", "true", "yes"}
    if not enabled:
        return _noop_stop

    if rss_reader is None:
        # Late-binding Lookup: ``_read_rss_mb_linux`` muss zur *Laufzeit* im
        # Modul-Namespace nachgeschlagen werden, sonst greifen Monkey-Patches
        # im Test (oder alternative Reader-Funktionen) nicht.
        module = sys.modules[__name__]
        default_reader = module.__dict__.get("_read_rss_mb_linux")

        def rss_reader() -> float | None:  # type: ignore[no-redef]
            """
            Liest den aktuellen Speicherverbrauch über den zur Laufzeit aufgelösten RSS-Reader.
            
            Returns:
                float | None: RSS-Speicherverbrauch in MB oder `None`, wenn kein Messwert verfügbar ist.
            """
            reader = module.__dict__.get("_read_rss_mb_linux", default_reader)
            if reader is None:
                return None
            return reader()

        user_supplied_reader = False
    else:
        user_supplied_reader = True

    if (
        not user_supplied_reader
        and rss_reader() is None
        and not Path(f"/proc/{os.getpid()}/status").exists()
    ):
        # macOS / kein /proc → Sampler einschalten, aber jede Samplezeile
        # bekommt ``rss_mb=None`` und einen WARNING-Hinweis. Wird NUR
        # aktiv, wenn der Caller keinen eigenen Reader geliefert hat —
        # sonst wuerde der macOS-Fallback den expliziten Reader (z.B.
        # einen Test-Reader, der bewusst ``None`` zurueckgibt) ueber-
        # schreiben. Fix fuer CodeRabbit-Finding #859.
        def rss_reader() -> float | None:  # type: ignore[no-redef]
            """
            Liefert keinen RSS-Messwert.
            
            Returns:
                float | None: Immer `None`.
            """
            return None

    stop_event = threading.Event()
    start = time.monotonic()
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink_handle = sink.open("a", encoding="utf-8")

    def _sampler_loop() -> None:
        """
        Schreibt während der Laufzeit regelmäßig RSS-Speicherschnappschüsse als NDJSON.
        
        Schreibfehler auf dem Zieldatenträger werden ignoriert, damit der Sampler den
        ausführenden Prozess nicht beendet.
        """
        while not stop_event.is_set():
            snap = {
                "label": "tick",
                "rss_mb": rss_reader(),
                "time_s": time.monotonic() - start,
            }
            try:
                sink_handle.write(json.dumps(snap) + "\n")
                sink_handle.flush()
            except (OSError, ValueError):
                # Disk voll, etc. — silently drop, Sampler darf den
                # Subprozess nicht zum Absturz bringen. ``ValueError``
                # faengt ``"I/O operation on closed file"`` ab, falls
                # ``_stop()`` das Handle schliesst, waehrend der Thread
                # noch mitten in einer Write-Call-Sequenz haengt
                # (Race-Window zwischen ``thread.join(timeout=...)``
                # und close()). Defensive Härtung fuer
                # CodeRabbit-Finding #859.
                pass
            stop_event.wait(interval_s)

    thread = threading.Thread(
        target=_sampler_loop,
        name="agora-memory-sampler",
        daemon=True,
    )
    thread.start()

    def _stop() -> None:
        """Beendet die laufende Speicheraufzeichnung und schließt die Zieldatei.
        
        Die Funktion kann wiederholt aufgerufen werden.
        """
        stop_event.set()
        thread.join(timeout=interval_s * 2)
        try:
            sink_handle.close()
        except OSError:
            pass

    return _stop


def _noop_stop() -> None:
    """Führt beim Beenden des Speichersamplers keine Aktion aus."""
    return None
