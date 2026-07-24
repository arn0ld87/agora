from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    from camel.types import ModelPlatformType  # type: ignore[import]

from dotenv import load_dotenv
from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


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
       endet auf ``:cloud`` / ``:latest``.  Ollama Cloud hat keinen
       OpenAI-Compat-``/v1``-Endpoint mehr; nur nativ ``/api/chat``.
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


def build_camel_completion_params(
    *,
    model: str,
    completion_max_tokens: int,
) -> dict[str, Any]:
    """Baut den Token-Limit-Block für ``ModelFactory.create()``.

    Liefert ``{"max_completion_tokens": N}`` für GPT-5/o1/o3/o4 und
    ``{"max_tokens": N}`` für alle anderen Modelle. Genau ein Schlüssel
    pro Aufruf — OpenAI lehnt unbekannte Parameter strikt ab.
    """
    key = "max_completion_tokens" if uses_max_completion_tokens(model) else "max_tokens"
    return {key: completion_max_tokens}


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


def preflight_model_probe(
    model: Any,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.2,
) -> None:
    """Einmaliger kleiner Chat-Completion-Probe vor dem Agenten-Fan-out.

    Sendet einen winzigen ``"ping"``-User-Call an das aufgebaute Modell und
    fängt permanente Auth-/Routing-Fehler (401/403/404) früh mit einer klaren
    ``ValueError``-Root-Cause ab — ein einzelner Fehler statt N identischer
    während der Simulation (Root Cause des ``404 model MiniMax-M3 not found``).
    Transiente Fehler (429/500/502/503) werden mit exponentiellem Backoff
    retried; erst nach Erschöpfung der Retries schlägt der Probe fehl.

    Der Probe läuft genau einmal pro Aufruf (bzw. einmal pro Retry-Versuch) —
    er führt keine eigene Fan-out-Logik. Aufrufer (``run_*_simulation``) rufen
    ihn direkt nach ``create_model`` auf, bevor Agenten erzeugt werden.

    Nur der OpenAI-kompatible Pfad (MiniMax, OpenAI, Qwen Cloud, …) wirft
    ``openai.APIStatusError`` mit brauchbarem ``status_code``; andere
    Plattformen (Gemini/Ollama) lassen ihre nativen Exceptions ungefiltert
    durch — die noch vor dem Fan-out auftreten und damit denselben
    Ein-Fehler-vor-Fan-out-Effekt erfüllen.
    """
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

_BERT_PROFILE_DEFAULT = "low"


def install_bert_memory_profile(profile: str | None = None) -> str:
    """Patches ``transformers.AutoModel.from_pretrained`` für TWHIN-BERT-Lazy-Loads.

    ENV-getrieben: ``AGORA_BERT_MEMORY_PROFILE=off|low|lowest``.

    - ``off`` (Default wenn Variable fehlt) — No-Op.
    - ``low`` (Default) — injiziert ``low_cpu_mem_usage=True`` und
      ``torch_dtype=torch.float16`` für ``Twitter/twhin-bert-base``. Laedt
      das Modell in fp16 statt fp32 und vermeidet den transienten
      Materialisierungs-Peak.
    - Andere Modellnamen bleiben unveraendert.

    Idempotent: ein zweiter Aufruf ersetzt fruehere Patches ohne Doppel-
    Wrapping (Detection via ``_agora_bert_memory_profile_applied``).

    Returns:
        Der effektive Profilname (für Diagnose-Logs).
    """
    effective = (profile or os.environ.get("AGORA_BERT_MEMORY_PROFILE") or _BERT_PROFILE_DEFAULT).lower()
    if effective == "off":
        return "off"

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
        model_name = args[0] if args else kwargs.get("pretrained_model_name_or_path")
        if isinstance(model_name, str) and model_name in _TWHIN_BERT_MODEL_NAMES:
            # User-Override hat Vorrang.
            if "low_cpu_mem_usage" not in kwargs:
                kwargs["low_cpu_mem_usage"] = True
            if torch_float16 is not None and "torch_dtype" not in kwargs:
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


def install_memory_sampler(
    sink: Path,
    *,
    interval_s: float = 0.5,
    rss_reader: Callable[[], float | None] | None = None,
) -> Callable[[], None]:
    """Startet einen RSS-Sampler-Thread, schreibt NDJSON-Snapshots nach ``sink``.

    ENV-getrieben: ``AGORA_DEBUG_MEMORY=1`` (oder ``true``) — alle anderen
    Werte oder fehlende Variable deaktivieren den Sampler (No-Op).

    Jeder Snapshot ist eine Zeile JSON mit ``label``, ``rss_mb`` und
    ``time_s`` (Sekunden seit Thread-Start). Hauptzweck: beim naechsten
    OOM-Run eine echte Boot-Kurve zu sehen, statt auf Vermutungen
    angewiesen zu sein.

    Args:
        sink: NDJSON-Zieldatei (typischerweise ``sim_dir/mem_profile.ndjson``).
        interval_s: Polling-Intervall in Sekunden (Default 0.5 s).
        rss_reader: Optionale Override für den RSS-Reader. Default laedt
            ``_read_rss_mb_linux`` beim Sample (late binding via Modul-
            Lookup); ein test-spezifischer Callable erlaubt deterministische
            Werte unabhängig von der echten /proc-Implementierung.

    Returns:
        ``stop()``-Callable zum sauberen Beenden; idempotent.
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
            reader = module.__dict__.get("_read_rss_mb_linux", default_reader)
            if reader is None:
                return None
            return reader()

    if rss_reader() is None and not Path(f"/proc/{os.getpid()}/status").exists():
        # macOS / kein /proc → Sampler einschalten, aber jede Samplezeile
        # bekommt ``rss_mb=None`` und einen WARNING-Hinweis.
        def rss_reader() -> float | None:  # type: ignore[no-redef]
            return None

    stop_event = threading.Event()
    start = time.monotonic()
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink_handle = sink.open("a", encoding="utf-8")

    def _sampler_loop() -> None:
        while not stop_event.is_set():
            snap = {
                "label": "tick",
                "rss_mb": rss_reader(),
                "time_s": time.monotonic() - start,
            }
            try:
                sink_handle.write(json.dumps(snap) + "\n")
                sink_handle.flush()
            except OSError:
                # Disk voll, etc. — silently drop, Sampler darf den
                # Subprozess nicht zum Absturz bringen.
                pass
            stop_event.wait(interval_s)

    thread = threading.Thread(
        target=_sampler_loop,
        name="agora-memory-sampler",
        daemon=True,
    )
    thread.start()

    def _stop() -> None:
        stop_event.set()
        thread.join(timeout=interval_s * 2)
        try:
            sink_handle.close()
        except OSError:
            pass

    return _stop


def _noop_stop() -> None:
    """No-Op-Stop fuer den inaktiven Pfad — immer idempotent."""
    return None
