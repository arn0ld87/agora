#!/usr/bin/env python3
"""check_legacy_model_picker.py — Grep-CI-Check für v3-Model-Picker.

Sub-Slice 5.5 der Epic ``onboarding-provider-unification`` deprecated die
alten v3-Model-Picker-Komponenten und -Stores. Damit sie nicht versehentlich
wieder in den Code wandern, blockiert dieser Check PRs, die folgende
Importe neu einführen:

* ``frontend/src/components/ui/ModelPicker.vue``            (Legacy v3)
* ``frontend/src/components/llm/LlmProfilePicker.vue``     (Legacy v3)
* ``frontend/src/components/ActiveModelBadge.vue``         (Legacy v3)
* ``@/store/llmProviders`` (genau diese Specifier, nicht ``…/llmProviders/…``)
* ``@/store/llmProfiles``
* ``@/store/llmRoutingDefaults``
* ``@/composables/useRuntimeLlmOptions``

Wird ein v3-Picker für den Migrations-Wrapper in 5.5 selbst gebraucht,
kann die Datei über den Magic-Comment ``legacy-model-picker-allow: <reason>``
(TS: ``// …``, Vue: ``<!-- … -->``) freigeschaltet werden. Begründung
im Comment, damit das nächste Audit nachvollziehen kann, warum der
v3-Pfad noch leben darf.

Verwendung
==========

    python3 .github/scripts/check_legacy_model_picker.py [TARGET_DIR]

Default ``TARGET_DIR``: ``frontend/src`` (relativ zum Repo-Root).

GH-Actions-Ausgabe
-------------------

Treffer werden als ``::error file=…,line=…,col=…::MSG`` emittiert, damit
GitHub sie als Inline-Annotation in der PR-Diff anzeigt. Mit ``--github``
(oder automatisch, wenn ``GITHUB_ACTIONS=true``) wird der Modus
explizit aktiviert; ``--no-github`` unterdrückt das Präfix für lokale
Läufe.

Exit-Codes
----------

* ``0`` — keine Treffer (alles sauber)
* ``1`` — verbotene v3-Importe gefunden
* ``2`` — Usage-Fehler (z. B. Zielpfad fehlt)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Regeln
# ---------------------------------------------------------------------------

# Jeder Eintrag: (substring, Migrations-Hinweis).
# Ein Import-Specifier ist verboten, wenn er mit dem Substring endet.
# Damit ist ``@/store/llmProviders`` (Treffer) verboten, aber ein
# zukünftiges ``@/store/llmProviders/index`` (Subpfad) bleibt erlaubt —
# ``endswith`` matcht den Subpfad nicht.
FORBIDDEN_SUBSTRINGS: list[tuple[str, str]] = [
    (
        "/components/ui/ModelPicker.vue",
        "v3 ModelPicker.vue → v4 AiModelPicker.vue (Slice 5.1)",
    ),
    (
        "/components/llm/LlmProfilePicker.vue",
        "v3 LlmProfilePicker.vue → v4 AiModelPicker.vue (Slice 5.1)",
    ),
    (
        "/components/ActiveModelBadge.vue",
        "v3 ActiveModelBadge.vue → v4 AiModelPicker.vue (Slice 5.1)",
    ),
    (
        "/store/llmProviders",
        "v3 store llmProviders → aiModels.ts / useActiveModelStore (Slice 5.5)",
    ),
    (
        "/store/llmProfiles",
        "v3 store llmProfiles → aiModels.ts / useActiveModelStore (Slice 5.5)",
    ),
    (
        "/store/llmRoutingDefaults",
        "v3 store llmRoutingDefaults → aiModels.ts / useActiveModelStore (Slice 5.5)",
    ),
    (
        "/composables/useRuntimeLlmOptions",
        "v3 composable useRuntimeLlmOptions → useActiveModelStore (Slice 5.5)",
    ),
]

# Magic-Comment, mit dem eine einzelne Datei sich freischalten darf.
# Form: ``legacy-model-picker-allow: <reason>`` — Reason ist Pflicht,
# damit die Opt-in-Spur im Audit sichtbar bleibt.
OPT_IN_MARKER = "legacy-model-picker-allow:"

# Datei-Endungen, die der Scanner berücksichtigt.
SCAN_EXTENSIONS = {".vue", ".ts"}

# Verzeichnisse, die der Scanner überspringt (typische Build-Artefakte).
SKIP_DIRS = {"__pycache__", "node_modules", ".nuxt", "dist", "coverage"}

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Holt jeden Import-Specifier aus einer Zeile. Erkennt:
#   import { x } from 'spec'
#   import x from 'spec'
#   import 'spec'                  (Side-Effect)
#   import type { x } from 'spec'
#   import('@/spec')               (Dynamic)
#   require('@/spec')              (CommonJS — wider Erwarten in .ts möglich)
# Specifiers können Anführungszeichen ' oder " haben.
IMPORT_RE = re.compile(
    r"""
    (?: ^ | \b )
    (?:
        from \s+
      | import \s+ (?: [^'"\n]+? \s+ from \s+ )?
      | require \s* \( \s*
      | import \s* \( \s*
    )
    ['"](?P<spec>[^'"\n]+?)['"]
    """,
    re.VERBOSE,
)


def _offset_to_linecol(text: str, offset: int) -> tuple[int, int]:
    """Mappt einen Zeichen-Offset auf (1-basierte Zeile, 1-basierte Spalte)."""
    prefix = text[:offset]
    line = prefix.count("\n") + 1
    last_nl = prefix.rfind("\n")
    col = offset - last_nl if last_nl >= 0 else offset + 1
    return line, col


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _is_forbidden(specifier: str) -> str | None:
    """Gibt die Migrations-Begründung zurück, wenn der Specifier verboten ist."""
    for substring, message in FORBIDDEN_SUBSTRINGS:
        if specifier.endswith(substring):
            return f"{message} (verboten: `{specifier}`)"
    return None


def _has_opt_in(text: str) -> bool:
    """True, wenn die Datei den Magic-Comment mit Begründung trägt."""
    if OPT_IN_MARKER not in text:
        return False
    # Mindestens ein nicht-leeres Zeichen nach dem Doppelpunkt verlangen,
    # damit leere Marker (``legacy-model-picker-allow:``) nicht durchgehen.
    for line in text.splitlines():
        if OPT_IN_MARKER in line:
            tail = line.split(OPT_IN_MARKER, 1)[1].strip()
            # Kommentar-Close tolerieren (Vue/HTML: -->, TS/JS: \n)
            tail = tail.rstrip("/>").rstrip("-").strip()
            if tail:
                return True
    return False


def _scan_file(path: Path) -> list[tuple[int, int, str]]:
    """Liest ``path`` und gibt alle verbotenen Treffer als (line, col, msg)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        # Binärdateien oder Permissions-Probleme: ignorieren, sind keine
        # Vue/TS-Quellen.
        print(f"::warning file={path}::skip: {exc}", file=sys.stderr)
        return []

    if _has_opt_in(text):
        return []

    violations: list[tuple[int, int, str]] = []
    for m in IMPORT_RE.finditer(text):
        spec = m.group("spec")
        msg = _is_forbidden(spec)
        if msg is None:
            continue
        offset = m.start("spec")
        line, col = _offset_to_linecol(text, offset)
        violations.append((line, col, msg))
    return violations


def scan(root: Path) -> list[tuple[Path, int, int, str]]:
    """Scannt ``root`` rekursiv und gibt alle Treffer zurück."""
    if not root.exists():
        raise FileNotFoundError(f"target directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"target is not a directory: {root}")

    results: list[tuple[Path, int, int, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        for line, col, msg in _scan_file(path):
            results.append((path, line, col, msg))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_github(file: Path, line: int, col: int, message: str) -> str:
    rel = file.resolve()
    return f"::error file={rel},line={line},col={col}::{message}"


def _format_plain(file: Path, line: int, col: int, message: str) -> str:
    return f"{file}:{line}:{col}: error: {message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grep-CI-Check: keine v3-Model-Picker-Stellen erlauben.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="frontend/src",
        help="Zielverzeichnis (default: frontend/src).",
    )
    parser.add_argument(
        "--github",
        dest="github",
        action="store_true",
        default=None,
        help="GH-Actions-Annotations erzwingen (sonst Auto via GITHUB_ACTIONS).",
    )
    parser.add_argument(
        "--no-github",
        dest="github",
        action="store_false",
        help="GH-Actions-Annotations unterdrücken (für lokale Läufe).",
    )
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        results = scan(target)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2

    github_mode = args.github
    if github_mode is None:
        github_mode = bool(__import__("os").environ.get("GITHUB_ACTIONS"))

    if not results:
        print(
            f"check_legacy_model_picker: clean ({target}) — "
            f"no v3 picker imports found.",
            file=sys.stderr,
        )
        return 0

    fmt = _format_github if github_mode else _format_plain
    for file, line, col, msg in results:
        print(fmt(file, line, col, msg))

    print(
        f"\ncheck_legacy_model_picker: {len(results)} violation(s) in {target}.",
        file=sys.stderr,
    )
    print(
        "  Hint: Use the magic comment `legacy-model-picker-allow: <reason>` "
        "to opt in a file for 5.5 wrappers.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
