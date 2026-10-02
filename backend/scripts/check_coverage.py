"""Coverage-Gate gegen den gemessenen Istwert (Issue #1495, Befund N).

Warum nicht ``--cov-fail-under``
--------------------------------
``--cov-fail-under`` kennt genau eine Zahl. Mit eingeschalteter
Branch-Messung vergleicht es die *kombinierte* Quote und verdeckt damit
gerade den Wert, der hier interessiert: Line- und Branch-Coverage laufen in
diesem Projekt weit auseinander (83.8 % gegen 71.9 %), und eine
Zusammenfassung beider laesst nicht erkennen, welche von beiden gefallen ist.

Dieses Skript liest den JSON-Report und prueft beide Quoten einzeln gegen
``coverage-baseline.json``. Unterschreitet eine davon ihre Schwelle, faellt das
Gate mit der konkreten Zahl. Liegt eine deutlich darueber, gibt es einen
Hinweis (kein Fail) — dieselbe Mechanik wie beim Radon- und beim
Typ-Schuld-Gate.

Ratchet und Schönungs-Check (Issue #1671, Entscheidung #1667)
-------------------------------------------------------------
Eine Quote laesst sich auch heben, indem man weniger misst. ``--integrity``
vergleicht deshalb den Iststand mit dem Referenz-Tag ``v0.9.6``, ohne einen
Coverage-Lauf zu brauchen:

* ``line_min``/``branch_min`` in ``coverage-baseline.json`` sinken nicht.
  Eine Absenkung braucht ``lowering_approval`` mit ``approved_by`` und
  ``reason`` (Freigabe des Maintainers).
* Die Coverage-Konfiguration (``[tool.coverage.*]`` in ``pyproject.toml``)
  bekommt keine neuen ``omit``-/``exclude``-Eintraege, ``source``/``include``
  werden nicht enger, und es kommt keine ``.coveragerc`` hinzu.
* Die Zahl der No-Cover-Pragmas und der Test-Skips (Skip-/xfail-Marken,
  Skip-Aufrufe im Testkoerper, unittest-Skips) unter ``backend/`` waechst
  nicht, ausser mit Eintrag in ``scope_allowlist`` (Datei, Art, Anzahl, Grund).

Aufruf:
    uv run pytest --cov=app --cov-branch --cov-report=json:coverage.json
    uv run python scripts/check_coverage.py [--report coverage.json]
    uv run python scripts/check_coverage.py --integrity
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import tomllib
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "coverage-baseline.json"
DEFAULT_REPORT = REPO_ROOT / "coverage.json"

#: Ab wie vielen Punkten ueber der Schwelle ein Nachziehen faellig ist.
_SLACK_HINT = 2.0

#: Referenzstand der Entscheidung #1667. Bewusst im Skript statt in der
#: Baseline-Datei: wer ihn verschiebt, aendert sichtbar das Gate selbst.
REFERENCE_TAG = "v0.9.6"

#: Dieselbe Erkennung wie coverage.py' Default-Ausschluss.
_PRAGMA = re.compile(r"#\s*(?:pragma|PRAGMA)[:\s]?\s*(?:no|NO)\s*(?:cover|COVER)")
_SKIP = re.compile(
    r"\bpytest\.mark\.(?:skip|skipif|xfail)\b"
    r"|\bpytest\.(?:skip|xfail|importorskip)\("
    r"|\bunittest\.(?:skip|skipIf|skipUnless|expectedFailure)\b"
)
_KINDS = {"pragma": _PRAGMA, "skip": _SKIP}

_SKIP_DIRS = {"node_modules", "__pycache__", "uploads", "logs", "log", "instance"}

#: Listen, deren neue Eintraege Code aus der Messung nehmen.
_GROWTH_FORBIDDEN = (
    ("run", "omit"),
    ("report", "omit"),
    ("report", "exclude_lines"),
    ("report", "exclude_also"),
)
#: Listen, die den gemessenen Bereich eingrenzen: kein Eintrag darf
#: wegfallen, und wo bisher keine Grenze war, kommt keine hinzu.
_NARROWING_FORBIDDEN = (
    ("run", "source"),
    ("run", "include"),
    ("report", "include"),
)
_FOREIGN_CONFIGS = (".coveragerc", "setup.cfg", "tox.ini")


def _percent(covered: int, total: int) -> float:
    return 100.0 * covered / total if total else 100.0


def _coverage_config(root: Path) -> dict[str, Any]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    coverage: dict[str, Any] = pyproject.get("tool", {}).get("coverage", {})
    return coverage


def _config_values(config: dict[str, Any], section: str, key: str) -> list[str]:
    value = config.get(section, {}).get(key, [])
    return [value] if isinstance(value, str) else list(value)


def _has_foreign_config(root: Path, name: str) -> bool:
    path = root / name
    if not path.is_file():
        return False
    return name == ".coveragerc" or "[coverage:" in path.read_text(encoding="utf-8")


def _check_config(reference: Path, current: Path) -> list[str]:
    ref_config, cur_config = _coverage_config(reference), _coverage_config(current)
    failures: list[str] = []
    for section, key in _GROWTH_FORBIDDEN:
        added = set(_config_values(cur_config, section, key)) - set(
            _config_values(ref_config, section, key)
        )
        for entry in sorted(added):
            failures.append(f"  - [tool.coverage.{section}] {key}: neuer Eintrag {entry!r}")
    for section, key in _NARROWING_FORBIDDEN:
        ref_values = _config_values(ref_config, section, key)
        cur_values = _config_values(cur_config, section, key)
        if not ref_values and cur_values:
            failures.append(
                f"  - [tool.coverage.{section}] {key}: neue Eingrenzung {cur_values!r}"
            )
        for entry in sorted(set(ref_values) - set(cur_values)):
            failures.append(f"  - [tool.coverage.{section}] {key}: {entry!r} entfernt")
    for name in _FOREIGN_CONFIGS:
        if _has_foreign_config(current, name) and not _has_foreign_config(reference, name):
            failures.append(f"  - {name}: neue Coverage-Konfiguration neben pyproject.toml")
    return failures


def _python_files(root: Path) -> Iterator[Path]:
    # os.walk statt rglob: .venv und node_modules werden gar nicht erst betreten.
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def _count_exclusions(root: Path) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = {kind: Counter() for kind in _KINDS}
    for path in _python_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        for kind, pattern in _KINDS.items():
            hits = len(pattern.findall(text))
            if hits:
                counts[kind][rel] = hits
    return counts


def _check_exclusions(reference: Path, current: Path, allowlist: list[Any]) -> list[str]:
    ref_counts, cur_counts = _count_exclusions(reference), _count_exclusions(current)
    failures: list[str] = []
    allowed: Counter[str] = Counter()
    for entry in allowlist:
        if not isinstance(entry, dict):
            failures.append(f"  - scope_allowlist: ungueltiger Eintrag {entry!r}")
            continue
        file, kind, count = entry.get("file"), entry.get("kind"), entry.get("count")
        reason = str(entry.get("reason") or "").strip()
        if kind not in _KINDS or not isinstance(count, int) or count < 1 or not file or not reason:
            failures.append(
                f"  - scope_allowlist: Eintrag {entry!r} braucht file, kind "
                f"({'/'.join(_KINDS)}), count >= 1 und einen Grund"
            )
            continue
        if cur_counts[kind][file] < count:
            failures.append(
                f"  - scope_allowlist: {file} hat nur {cur_counts[kind][file]} {kind}, "
                f"der Eintrag erlaubt {count} — veralteten Eintrag kuerzen oder entfernen"
            )
            continue
        allowed[kind] += count

    for kind in _KINDS:
        ref_total = sum(ref_counts[kind].values())
        cur_total = sum(cur_counts[kind].values())
        if cur_total <= ref_total + allowed[kind]:
            continue
        failures.append(
            f"  - {kind}: {cur_total} statt hoechstens {ref_total} ({REFERENCE_TAG}) "
            f"+ {allowed[kind]} (Allowlist)"
        )
        for file in sorted(cur_counts[kind]):
            grown = cur_counts[kind][file] - ref_counts[kind][file]
            if grown > 0:
                failures.append(f"      {file}: +{grown}")
    return failures


def _check_ratchet(ref_baseline: dict[str, Any], cur_baseline: dict[str, Any]) -> list[str]:
    approval = cur_baseline.get("lowering_approval") or {}
    approved = isinstance(approval, dict) and all(
        str(approval.get(field) or "").strip() for field in ("approved_by", "reason")
    )
    failures: list[str] = []
    for key in ("line_min", "branch_min"):
        ref_value, cur_value = float(ref_baseline[key]), float(cur_baseline[key])
        if cur_value >= ref_value:
            continue
        if approved:
            print(
                f"Hinweis: {key} {cur_value:.2f} < {ref_value:.2f} ({REFERENCE_TAG}), "
                f"freigegeben von {approval['approved_by']}: {approval['reason']}"
            )
            continue
        failures.append(
            f"  - {key} {cur_value:.2f} < {ref_value:.2f} ({REFERENCE_TAG}) ohne "
            "lowering_approval (approved_by + reason)"
        )
    return failures


def _check_integrity(reference: Path, current: Path) -> int:
    def baseline_of(root: Path) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(
            (root / "coverage-baseline.json").read_text(encoding="utf-8")
        )
        return data

    cur_baseline = baseline_of(current)
    failures = [
        *_check_ratchet(baseline_of(reference), cur_baseline),
        *_check_config(reference, current),
        *_check_exclusions(reference, current, cur_baseline.get("scope_allowlist", [])),
    ]
    if failures:
        print(f"FEHLER: Coverage-Scope oder Schwellen gegenueber {REFERENCE_TAG} geschoent.")
        print("\n".join(failures))
        print(
            "\nTests nachziehen statt Messung verkleinern. Begruendete Ausnahmen gehoeren "
            "mit Datei und Grund in coverage-baseline.json (scope_allowlist)."
        )
        return 1
    print(f"OK: Coverage-Schwellen und -Scope nicht schlechter als {REFERENCE_TAG}.")
    return 0


def _export_reference(target: Path) -> Path:
    """Schreibt ``backend/`` des Referenz-Tags nach ``target``."""
    result = subprocess.run(
        ["git", "archive", "--format=tar", REFERENCE_TAG, "backend"],
        cwd=REPO_ROOT.parent,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Referenz-Tag {REFERENCE_TAG} nicht lesbar ({result.stderr.decode().strip()}). "
            f"Holen mit: git fetch --no-tags --depth=1 origin "
            f"+refs/tags/{REFERENCE_TAG}:refs/tags/{REFERENCE_TAG}"
        )
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        archive.extractall(target, filter="data")
    return target / "backend"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--integrity",
        action="store_true",
        help=f"Ratchet und Schönungs-Check gegen {REFERENCE_TAG} statt Report-Pruefung",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Backend-Iststand")
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=None,
        help=f"Backend-Referenzstand als Verzeichnis (Default: git archive {REFERENCE_TAG})",
    )
    args = parser.parse_args(argv)

    if args.integrity:
        if args.reference_dir is not None:
            return _check_integrity(args.reference_dir, args.root)
        with tempfile.TemporaryDirectory() as tmp:
            return _check_integrity(_export_reference(Path(tmp)), args.root)

    if not args.report.exists():
        raise SystemExit(
            f"Coverage-Report fehlt: {args.report}. Erst pytest mit "
            "--cov-report=json:coverage.json laufen lassen."
        )
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    totals = json.loads(args.report.read_text(encoding="utf-8"))["totals"]

    line = _percent(totals["covered_lines"], totals["num_statements"])
    branch = _percent(totals["covered_branches"], totals["num_branches"])

    if not totals["num_branches"]:
        raise SystemExit(
            "Der Report enthaelt keine Branch-Daten — pytest ohne --cov-branch "
            "gelaufen? Ohne sie prueft dieses Gate nur die Haelfte."
        )

    failures: list[str] = []
    hints: list[str] = []
    for label, value, key in (
        ("Line", line, "line_min"),
        ("Branch", branch, "branch_min"),
    ):
        threshold = float(baseline[key])
        if value < threshold:
            failures.append(f"  - {label}-Coverage {value:.2f} % < {threshold:.2f} %")
        elif value - threshold >= _SLACK_HINT:
            hints.append(
                f"  - {label}-Coverage {value:.2f} % liegt {value - threshold:.2f} Punkte "
                f"ueber der Schwelle {threshold:.2f} % — Schwelle kann nachgezogen werden."
            )

    if failures:
        print("FEHLER: Coverage ist unter die Baseline gefallen.")
        print("\n".join(failures))
        print(
            f"\nGemessen: Line {line:.2f} % ({totals['covered_lines']}/"
            f"{totals['num_statements']}), Branch {branch:.2f} % "
            f"({totals['covered_branches']}/{totals['num_branches']})."
        )
        print("Fehlende Tests nachziehen — nicht die Schwelle senken.")
        return 1

    for hint in hints:
        print(hint)
    print(f"OK: Line {line:.2f} %, Branch {branch:.2f} % (Baseline {baseline['line_min']} / {baseline['branch_min']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
