from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv


def _is_ollama_route(model: str, base_url: str) -> bool:
    """True wenn das Modell über Ollama (lokal oder Cloud) läuft.

    Heuristik analog zu :class:`app.utils.llm_client.LLMClient._detect_provider`:
    - Modellname endet auf ``:cloud`` → Ollama Cloud
    - Base-URL enthält Port ``11434`` → lokale Ollama-Instanz
    """
    if model.endswith(":cloud"):
        return True
    if "11434" in (base_url or ""):
        return True
    return False


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
    """Baut den ``extra_body``-Block für ``ModelFactory.create()``.

    Ollama-spezifische Parameter (``think``, ``options.num_ctx``) werden
    NUR für Ollama-Routen gesetzt. OpenAI/Anthropic/Mistral kennen den
    ``think``-Parameter nicht und antworten 400 ``Unknown parameter``,
    sobald er in ``extra_body`` landet.
    """
    if not _is_ollama_route(model, base_url):
        return {}

    body: dict[str, Any] = {"think": think}
    if num_ctx is not None:
        body["options"] = {"num_ctx": num_ctx}
    return body


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
