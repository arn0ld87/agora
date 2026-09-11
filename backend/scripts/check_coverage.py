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

Aufruf:
    uv run pytest --cov=app --cov-branch --cov-report=json:coverage.json
    uv run python scripts/check_coverage.py [--report coverage.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "coverage-baseline.json"
DEFAULT_REPORT = REPO_ROOT / "coverage.json"

#: Ab wie vielen Punkten ueber der Schwelle ein Nachziehen faellig ist.
_SLACK_HINT = 2.0


def _percent(covered: int, total: int) -> float:
    return 100.0 * covered / total if total else 100.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

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
