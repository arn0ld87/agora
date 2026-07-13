#!/usr/bin/env python3
"""check_legacy_model_picker.py — Grep-CI-Check für v3-Model-Picker.

Sub-Slice 5.5 der Epic ``onboarding-provider-unification`` hat die alten
v3-Model-Picker-Komponenten und -Stores deprecatet. Damit sie nicht
versehentlich in *neuen* Code wandern, blockiert dieser Check PRs, die
folgende Importe einführen:

* ``frontend/src/components/ui/ModelPicker.vue``          (Legacy v3)
* ``frontend/src/components/llm/LlmProfilePicker.vue``    (Legacy v3)
* ``frontend/src/components/ActiveModelBadge.vue``        (Legacy v3)
* ``@/store/llmProviders`` (genau diese Specifier, nicht ``…/llmProviders/…``)
* ``@/store/llmProfiles``
* ``@/store/llmRoutingDefaults``
* ``@/composables/useRuntimeLlmOptions``

Read-Adapter-Freigabe via ``@deprecated``
=========================================

Nach 5.5 gibt es keinen Opt-in-Marker mehr. Stattdessen erkennt der Check das
``@deprecated``-JSDoc-Tag am **Ziel** des Imports: Trägt die importierte Datei
selbst ein ``@deprecated``-Tag, gilt sie als sanktionierter Read-Adapter im
Deprecation-/Read-only-Fenster und der Import ist erlaubt. So dürfen die
bestehenden v3-Consumer (Step-Views, WorkspaceHeader, …) die deprecateten
Picker/Composables weiter lesen, ohne pro-Datei-Marker zu tragen — während
jeder *neu* eingeführte, nicht-deprecatete v3-Pfad hart blockiert wird.

Die alten Stores (``llmProviders``/``llmProfiles``/``llmRoutingDefaults``)
existieren nach 5.5 nicht mehr als Datei (konsolidiert in
``@/store/aiModels``). Ein Import dieser Specifier resolved damit auf kein
Ziel → keine ``@deprecated``-Freigabe möglich → Verstoß.

Verwendung
==========

    python3 .github/scripts/check_legacy_model_picker.py [TARGET_DIR]

Default ``TARGET_DIR``: ``frontend/src`` (relativ zum Repo-Root). ``@/`` wird
auf ``TARGET_DIR`` aufgelöst (Vite-Alias ``@`` == ``frontend/src``).

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
import os
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
        "v3 store llmProviders → aiModels.ts (Slice 5.5)",
    ),
    (
        "/store/llmProfiles",
        "v3 store llmProfiles → aiModels.ts (Slice 5.5)",
    ),
    (
        "/store/llmRoutingDefaults",
        "v3 store llmRoutingDefaults → aiModels.ts (Slice 5.5)",
    ),
    (
        "/composables/useRuntimeLlmOptions",
        "v3 composable useRuntimeLlmOptions → aiModels.ts / AiModelPicker (Slice 5.5)",
    ),
]

# JSDoc-Tag, das ein Import-Ziel als sanktionierten Read-Adapter markiert.
# Trägt das *Ziel* eines verbotenen Imports dieses Tag, ist der Import im
# Deprecation-/Read-only-Fenster erlaubt (ersetzt den 5.4-Opt-in-Marker).
DEPRECATED_TAG = "@deprecated"

# Datei-Endungen, die der Scanner berücksichtigt.
SCAN_EXTENSIONS = {".vue", ".ts"}

# Endungen/Index-Kandidaten für die Ziel-Auflösung extensionsloser Specifier.
RESOLVE_SUFFIXES = (".ts", ".vue")
RESOLVE_INDEX = ("index.ts", "index.vue")

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


def _resolve_target(specifier: str, importing_file: Path, root: Path) -> Path | None:
    """Löst einen Import-Specifier auf eine Ziel-Datei im Scan-Baum auf.

    - ``@/x`` → ``root/x`` (Vite-Alias ``@`` == Scan-Root == ``frontend/src``).
    - ``./x`` / ``../x`` → relativ zum Verzeichnis der importierenden Datei.
    - Bare-Specifier (npm-Paket) → ``None`` (nie ein lokales Ziel).

    Probiert die Datei direkt sowie mit ``.ts``/``.vue``-Endung und als
    ``index.*``. Gibt die erste existierende Datei zurück, sonst ``None``.
    """
    if specifier.startswith("@/"):
        base = root / specifier[2:]
    elif specifier.startswith("."):
        base = importing_file.parent / specifier
    else:
        return None

    base = Path(os.path.normpath(base))
    candidates = [base]
    candidates += [base.with_name(base.name + suffix) for suffix in RESOLVE_SUFFIXES]
    candidates += [base / index for index in RESOLVE_INDEX]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _target_is_deprecated(specifier: str, importing_file: Path, root: Path) -> bool:
    """True, wenn das Import-Ziel ein ``@deprecated``-JSDoc-Tag trägt."""
    target = _resolve_target(specifier, importing_file, root)
    if target is None:
        return False
    try:
        return DEPRECATED_TAG in target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False


def _scan_file(path: Path, root: Path) -> list[tuple[int, int, str]]:
    """Liest ``path`` und gibt alle verbotenen Treffer als (line, col, msg)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        # Binärdateien oder Permissions-Probleme: ignorieren, sind keine
        # Vue/TS-Quellen.
        print(f"::warning file={path}::skip: {exc}", file=sys.stderr)
        return []

    violations: list[tuple[int, int, str]] = []
    for m in IMPORT_RE.finditer(text):
        spec = m.group("spec")
        msg = _is_forbidden(spec)
        if msg is None:
            continue
        # Read-Adapter-Freigabe: importiertes Ziel ist selbst @deprecated.
        if _target_is_deprecated(spec, path, root):
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
        for line, col, msg in _scan_file(path, root):
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
        github_mode = bool(os.environ.get("GITHUB_ACTIONS"))

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
        "  Hint: A v3 read-adapter is only allowed if its target file carries "
        "an `@deprecated` JSDoc tag; new v3 imports are blocked.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
