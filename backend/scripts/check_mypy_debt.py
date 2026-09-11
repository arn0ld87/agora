"""Typ-Schuld-Gate: macht die von ``ignore_errors`` verdeckte mypy-Schuld sichtbar.

Warum es dieses Gate gibt (Issue #1495)
---------------------------------------
``pyproject.toml`` schaltet mypy fuer ``app``, ``app.config``, ``app.container``,
``app.models.*``, ``app.services.*``, ``app.storage.*``, ``app.utils.*`` und
``app.llm.*`` per ``ignore_errors = true`` ab. Das reguläre ``mypy app`` ist
damit gruen, obwohl in genau diesen Bereichen die eigentliche Arbeit liegt — die
Schuld ist nicht getilgt, sondern unsichtbar. Ein unsichtbarer Wert kann weder
sinken noch als gewachsen auffallen.

Dieses Gate repariert die Typfehler NICHT. Es misst sie mit ``mypy-debt.ini``
(derselben Konfiguration ohne den ``ignore_errors``-Block), vergleicht sie je
Datei gegen eine eingecheckte Baseline und schlaegt an, wenn

  * eine Datei mehr Fehler hat als in der Baseline,
  * eine Datei neu Fehler bekommt, die vorher keine hatte, oder
  * die ``ignore_errors``-Modulliste in ``pyproject.toml`` waechst.

Der letzte Punkt schliesst den offensichtlichen Umgehungsweg: ein neues Modul in
die Liste zu schreiben, statt es zu typisieren.

Sinkt die Schuld, meldet das Gate einen Hinweis (kein Fail) — die Baseline
gehoert dann abgesenkt. Das Muster ist bewusst dasselbe wie beim
Radon-Komplexitaets-Gate (``scripts/check_complexity.py``).

Aufruf:
    uv run python scripts/check_mypy_debt.py            # pruefen (exit 1 bei Wachstum)
    uv run python scripts/check_mypy_debt.py --write    # Baseline neu schreiben
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "mypy-debt.ini"
BASELINE = REPO_ROOT / "mypy-debt-baseline.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Nur echte Fehlerzeilen zaehlen — "note:"-Zeilen sind Erlaeuterungen zu einem
# bereits gezaehlten Fehler und wuerden die Schuld sonst doppelt buchen.
_ERROR_RE = re.compile(r"^(?P<file>[^:]+):\d+:(?:\d+:)?\s*error:")


def measure() -> Counter[str]:
    """Zaehlt mypy-Fehler je Datei mit abgeschaltetem ``ignore_errors``."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "app", "--config-file", str(CONFIG), "--no-incremental"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"mypy konnte nicht ausgefuehrt werden (exit {result.returncode})")
    counts: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        match = _ERROR_RE.match(line)
        if match:
            counts[match.group("file")] += 1
    return counts


def ignored_modules() -> list[str]:
    """Module, die in ``pyproject.toml`` per ``ignore_errors`` abgeschaltet sind."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    overrides = data.get("tool", {}).get("mypy", {}).get("overrides", [])
    modules: list[str] = []
    for override in overrides:
        if override.get("ignore_errors"):
            raw = override.get("module", [])
            modules.extend([raw] if isinstance(raw, str) else raw)
    return sorted(modules)


def render(counts: Counter[str], modules: list[str]) -> str:
    lines = [
        "# mypy-Schuld-Baseline — erzeugt mit `python scripts/check_mypy_debt.py --write`.",
        "#",
        "# Gemessen mit mypy-debt.ini: derselben Konfiguration wie das regulaere Gate,",
        "# aber OHNE den ignore_errors-Block. Jede Zeile: <fehler> <datei>.",
        "#",
        "# Diese Zahlen duerfen nur sinken. Waechst eine, ist die Aenderung schuld —",
        "# nicht die Baseline. Nach einem Cleanup: neu schreiben und mitcommitten.",
        "",
        "[ignore-errors-module]",
        "# Diese Module sind im regulaeren Gate abgeschaltet. Die Liste darf nicht",
        "# wachsen: ein neues Modul hier hinein zu schreiben, statt es zu typisieren,",
        "# waere der offensichtliche Umgehungsweg um die Zahlen unten.",
    ]
    lines.extend(modules)
    lines.append("")
    lines.append("[errors-per-file]")
    for path, count in sorted(counts.items()):
        lines.append(f"{count} {path}")
    lines.append("")
    lines.append(f"# Summe: {sum(counts.values())} Fehler in {len(counts)} Dateien.")
    lines.append("")
    return "\n".join(lines)


def parse_baseline() -> tuple[Counter[str], list[str]]:
    counts: Counter[str] = Counter()
    modules: list[str] = []
    section = ""
    for raw in BASELINE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line
            continue
        if section == "[ignore-errors-module]":
            modules.append(line)
        elif section == "[errors-per-file]":
            count, _, path = line.partition(" ")
            counts[path.strip()] = int(count)
    return counts, modules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Baseline neu schreiben")
    args = parser.parse_args()

    counts = measure()
    modules = ignored_modules()

    if args.write:
        BASELINE.write_text(render(counts, modules), encoding="utf-8")
        print(f"Baseline geschrieben: {sum(counts.values())} Fehler in {len(counts)} Dateien.")
        return 0

    if not BASELINE.exists():
        raise SystemExit(f"Baseline fehlt: {BASELINE}. Einmalig mit --write erzeugen.")

    baseline_counts, baseline_modules = parse_baseline()
    failures: list[str] = []
    hints: list[str] = []

    for path, count in sorted(counts.items()):
        allowed = baseline_counts.get(path, 0)
        if count > allowed:
            failures.append(
                f"  - {path}: {count} Typfehler, Baseline erlaubt {allowed}"
            )
        elif count < allowed:
            hints.append(f"  - {path}: {count} statt {allowed} — Baseline kann sinken.")
    for path, allowed in sorted(baseline_counts.items()):
        if path not in counts and allowed:
            hints.append(f"  - {path}: fehlerfrei — Eintrag kann entfallen.")

    new_modules = sorted(set(modules) - set(baseline_modules))
    if new_modules:
        failures.append(
            "  - pyproject.toml: neue ignore_errors-Module "
            + ", ".join(new_modules)
            + " — Typfehler gehoeren behoben, nicht abgeschaltet."
        )

    total, baseline_total = sum(counts.values()), sum(baseline_counts.values())
    if failures:
        print("FEHLER: mypy-Schuld ist gewachsen.")
        print("\n".join(failures))
        print(f"\nSumme: {total} Fehler (Baseline {baseline_total}).")
        print("Beheben statt Baseline anheben. Nach einem echten Cleanup:")
        print("  uv run python scripts/check_mypy_debt.py --write")
        return 1

    for hint in hints:
        print(hint)
    print(
        f"OK: keine neue Typ-Schuld ({total} Fehler in {len(counts)} Dateien, "
        f"Baseline {baseline_total})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
