"""
Voice-Lint-Gate.

Scannt Prompts und Report-Services auf verbotene Forecast- und
US-Marketing-Phrasen (DACH-Voice-Register, Layer 2).

Anti-Pattern-Klassen:
  forecast  — Autoritäts-Vokabular / Zukunftsprognosen
  marketing — US-Korporatismus-Phrasen

Aufruf (aus backend/):
    uv run python scripts/check_voice.py --soft
    uv run python scripts/check_voice.py --paths app/services/report_prompts.py

Exit-Codes:
    0 — keine Hits (oder --soft)
    1 — Hits gefunden
    2 — IO/CLI-Fehler
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Pattern-Definitionen
# ---------------------------------------------------------------------------

_FORECAST_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("future prediction", re.compile(r"\bfuture\s+prediction\b", re.IGNORECASE)),
    ("rehearsal of the future", re.compile(r"\brehearsal\s+of\s+the\s+future\b", re.IGNORECASE)),
    ("god's eye view", re.compile(r"\bgod['']s\s+eye\s+view\b", re.IGNORECASE)),
    ("predicts that", re.compile(r"\bpredicts\s+that\b", re.IGNORECASE)),
    ("we will surely", re.compile(r"\bwe\s+will\s+surely\b", re.IGNORECASE)),
    ("we will definitely", re.compile(r"\bwe\s+will\s+definitely\b", re.IGNORECASE)),
    ("seamless future", re.compile(r"\bseamless\s+future\b", re.IGNORECASE)),
]

_MARKETING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("revolutionary", re.compile(r"\brevolutionary\b", re.IGNORECASE)),
    ("seamless", re.compile(r"\bseamless\b", re.IGNORECASE)),
    ("groundbreaking", re.compile(r"\bgroundbreaking\b", re.IGNORECASE)),
    ("cutting-edge", re.compile(r"\bcutting[- ]edge\b", re.IGNORECASE)),
    ("next-generation", re.compile(r"\bnext[- ]generation\b", re.IGNORECASE)),
    ("best-in-class", re.compile(r"\bbest[- ]in[- ]class\b", re.IGNORECASE)),
    ("synergy", re.compile(r"\bsynerg(?:y|ies)\b", re.IGNORECASE)),
    ("unparalleled", re.compile(r"\bunparalleled\b", re.IGNORECASE)),
    ("leverage", re.compile(r"\bleverage\b", re.IGNORECASE)),
]

ALL_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (category, phrase, pattern)
    for category, pairs in (
        ("forecast", _FORECAST_PATTERNS),
        ("marketing", _MARKETING_PATTERNS),
    )
    for phrase, pattern in pairs
]

# ---------------------------------------------------------------------------
# Eingebaute Allowlist (Dateien, die Anti-Patterns ZITIEREN dürfen)
# ---------------------------------------------------------------------------

_BUILTIN_ALLOWLIST_SUFFIXES: frozenset[str] = frozenset(
    [
        "prompts/2026-05-02-voice-register-katalog.md",
        "docs/archive/worklogs/2026-05-02-task-10-voice-register-arbeitsprotokoll.md",
    ]
)


def _is_allowlisted(path: Path, repo_root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    rel_posix = rel.as_posix()
    return any(rel_posix.endswith(suffix) for suffix in _BUILTIN_ALLOWLIST_SUFFIXES)


# ---------------------------------------------------------------------------
# Scan-Logik
# ---------------------------------------------------------------------------


def scan_file(
    path: Path,
    repo_root: Path,
    extra_allowlist: set[str],
) -> list[tuple[str, int, int, str, str, str]]:
    """
    Gibt eine Liste von Treffern zurück:
    (rel_path, line_nr, col_nr, category, phrase, context_line)
    """
    if _is_allowlisted(path, repo_root):
        return []

    try:
        rel_path = str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        rel_path = str(path)

    if rel_path in extra_allowlist:
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"::warning::Kann {path} nicht lesen: {exc}", file=sys.stderr)
        return []

    hits: list[tuple[str, int, int, str, str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for category, phrase, pattern in ALL_PATTERNS:
            for m in pattern.finditer(line):
                col = m.start() + 1
                hits.append((rel_path, i, col, category, phrase, line.strip()))

    return hits


def collect_paths(
    raw_paths: list[str],
    repo_root: Path,
) -> list[Path]:
    """Expandiert Glob-Ausdrücke und gibt existierende Dateien zurück."""
    result: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = repo_root / p
        if "*" in raw or "?" in raw:
            result.extend(sorted(p.parent.glob(p.name)))
        elif p.is_file():
            result.append(p)
        elif p.is_dir():
            result.extend(sorted(p.rglob("*.py")))
        else:
            print(f"::warning::Pfad nicht gefunden / kein File: {raw}", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Default-Scope
# ---------------------------------------------------------------------------

# report_agent wurde in ein Package umgewandelt (Sub-Slice M11.13, Issue #202).
# Die Package-Verzeichnis-Expansion findet in expand_paths() statt (is_dir-Zweig).
_DEFAULT_PATHS = [
    "backend/app/services/report_prompts.py",
    "backend/app/services/report_agent",
    "prompts/*.md",
]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: PLR0912
    ap = argparse.ArgumentParser(
        description="Voice-Lint: scannt auf verbotene Forecast- und Marketing-Phrasen."
    )
    ap.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        default=None,
        help="Pfade/Globs relativ zu --repo-root. Default: report_prompts.py, report_agent.py, prompts/*.md",
    )
    ap.add_argument(
        "--soft",
        action="store_true",
        help="Immer Exit 0, auch bei Hits (für Bootstrap-Phase).",
    )
    ap.add_argument(
        "--allowlist",
        metavar="FILE",
        type=Path,
        default=None,
        help="Optionale Text-Datei mit zusätzlichen erlaubten Pfaden (eine Zeile pro Pfad).",
    )
    ap.add_argument(
        "--repo-root",
        metavar="PATH",
        type=Path,
        default=None,
        help="Repo-Root. Default: 2 Ebenen über dem Skript.",
    )
    args = ap.parse_args()

    # --- Repo-Root bestimmen ---
    if args.repo_root is not None:
        repo_root = args.repo_root.resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent

    if not repo_root.is_dir():
        print(f"::error::repo-root nicht gefunden: {repo_root}", file=sys.stderr)
        return 2

    # --- Extra-Allowlist laden ---
    extra_allowlist: set[str] = set()
    if args.allowlist is not None:
        try:
            for line in args.allowlist.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    extra_allowlist.add(stripped)
        except OSError as exc:
            print(f"::error::Allowlist-Datei nicht lesbar: {exc}", file=sys.stderr)
            return 2

    # --- Pfade auflösen ---
    raw_paths = args.paths if args.paths is not None else _DEFAULT_PATHS
    files = collect_paths(raw_paths, repo_root)

    if not files:
        print("::warning::Keine Dateien zum Scannen gefunden.")
        return 0

    # --- Scan ---
    all_hits: list[tuple[str, int, int, str, str, str]] = []
    for f in files:
        all_hits.extend(scan_file(f, repo_root, extra_allowlist))

    # --- Output ---
    for rel_path, line_nr, col, category, phrase, context in all_hits:
        print(f"{rel_path}:{line_nr}:{col}: {category}: {phrase} | {context}")

    if all_hits:
        count = len(all_hits)
        if args.soft:
            print(f"::warning::Voice-Lint-Soft: {count} Treffer gefunden (--soft, kein Hard-Fail).")
            return 0
        print(f"::error::Voice-Lint: {count} Treffer — bitte Phrasen entfernen.", file=sys.stderr)
        return 1

    print("Voice-Lint: OK — keine verbotenen Phrasen gefunden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
