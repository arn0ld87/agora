from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


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

    for entry in log_dir_path.iterdir():
        if entry.is_file() and entry.suffix == ".log":
            try:
                entry.unlink()
            except OSError:
                pass

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
